"""把打包目录做成一个 Windows 安装包（MSI，走 WiX）。

为什么是 MSI 而不是"再发一个 zip"：用户双击就装、在"应用和功能"里能看到、
能干净卸载；公司/学校机器上 MSI 也通常比 exe 安装器更容易被允许。

为什么用 WiX（`dotnet tool install --global wix`，一次性）：

最初这里是用 Python 自带的 `msilib` 直接往 MSI 表里写行的（distutils 的 `bdist_msi`
就是这么干的）。结果是**装完没有快捷方式、双击没有任何界面、没有卸载入口**——
表结构错一处就是这种症状，而这种错误在**没有管理员权限的机器上没法先试**。
WiX 在构建时就把表校验掉，而且自带"欢迎 → 许可协议 → 选安装目录 → 进度 → 完成"
这套久经考验的对话框（`WixUI_InstallDir`），我们只在它前面插一页语言选择。

安装形态（几个刻意的决定）：

* **每机器安装**（`Scope="perMachine"`）：装到 `C:\Program Files\LittleTilesReader`，
  双击会弹一次 UAC（MSI 的常规形态）；用户可以在向导里改安装位置；
* 装到 Program Files 正好落在应用已经照顾过的情形：安装目录不可写时
  `app/config.py` 会把数据放 `%LOCALAPPDATA%\\LittleTilesReader`；
* 开始菜单（含**卸载**快捷方式）+ 桌面各一个快捷方式；
* **固定 UpgradeCode**：发新版时自动卸旧版（`MajorUpgrade`）。

自检（见 `tools/check_msi.py`）：管理员安装（`msiexec /a`）能解出全部文件、
真机按用户安装 → 能跑 `--self-check` → 卸载后目录与注册项都清掉。
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

#: 产品身份的种子。**一旦发过版本就别改**：UpgradeCode 变了 = 新版认不出旧版，
#: 用户机器上会同时留下两份。ProductCode 则按版本号派生（每次发版都不同）。
_SEED = "gaksy/minecraft-littletiles-reader/windows"
UPGRADE_CODE = "{%s}" % uuid.uuid5(uuid.NAMESPACE_URL, _SEED)

PRODUCT_NAME = "LittleTiles Reader"
MANUFACTURER = "Gaksy"
APP_EXE_RELATIVE = Path("LittleTilesReader") / "LittleTilesReader.exe"

#: 目录表里的固定名字（Property/Id 都一样，安装时可覆盖 INSTALLDIR）
INSTALL_DIR_NAME = "LittleTilesReader"


def stable_guid(name: str) -> str:
    """组件 GUID：按名字派生，**同一个名字永远是同一个 GUID**（升级才能正确换文件）。"""

    return "{%s}" % uuid.uuid5(uuid.NAMESPACE_URL, "%s/%s" % (_SEED, name))


def wix_executable() -> Path:
    """找 wix.exe（dotnet 全局工具装到 ~/.dotnet/tools）。"""

    candidates = [
        Path.home() / ".dotnet" / "tools" / "wix.exe",
        Path(r"C:\Program Files\dotnet\tools\wix.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    found = shutil.which("wix")
    if found:
        return Path(found)
    raise SystemExit(
        "找不到 WiX。装一次即可：\n"
        "  dotnet tool install --global wix\n"
        "（之后 tools/build_msi.py 会自动找到它）"
    )


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _component_id(relative: str) -> str:
    return "c_%s" % hashlib.sha1(relative.encode("utf-8")).hexdigest()[:16]


def _directory_id(relative: str) -> str:
    return "d_%s" % hashlib.sha1(relative.encode("utf-8")).hexdigest()[:16]


def render_payload(package_dir: Path) -> tuple[str, list[str]]:
    """把打包目录渲染成 WiX 的 `<Directory>` / `<Component>` 片段。

    * 组件 Id 与 GUID 都由**相对路径**派生：同一个文件永远是同一个 GUID，
      发新版时 MSI 才会"就地换文件"而不是又装一份；
    * 一个文件一个组件：KeyPath 天然就是这个文件，不用再操心哪个文件当关键路径。
    """

    tree: dict = {}
    for item in sorted(Path(package_dir).rglob("*")):
        if item.is_file():
            parts = item.relative_to(package_dir).parts
            node = tree
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node.setdefault("__files__", []).append("\\".join(parts))

    components: list[str] = []

    def render(node: dict, prefix: str, indent: str) -> str:
        lines: list[str] = []
        for name in sorted(k for k in node if k != "__files__"):
            relative = "%s/%s" % (prefix, name) if prefix else name
            child = node[name]
            lines.append(
                '%s<Directory Id="%s" Name="%s">' % (indent, _directory_id(relative), _xml_escape(name))
            )
            lines.append(render(child, relative, indent + "  "))
            lines.append("%s</Directory>" % indent)
        for relative in node.get("__files__", []):
            component = _component_id(relative)
            components.append(component)
            lines.append(
                '%s<Component Id="%s" Guid="%s">' % (indent, component, stable_guid(relative))
            )
            lines.append(
                '%s  <File Id="f_%s" Source="%s" KeyPath="yes" />'
                % (indent, component[2:], _xml_escape(str(Path(package_dir) / relative)))
            )
            lines.append("%s</Component>" % indent)
        return "\n".join(lines)

    return render(tree, "", "        "), components


def msi_version(version: str) -> str:
    """MSI 的 ProductVersion 只能是 `主.次.修订`（最多三段数字，不能带后缀）。

    应用版本带 `-beta` 这类后缀时，取数字前缀（`0.1.0-beta` → `0.1.0`）；
    后缀本身照旧出现在包名与自述文本里。
    """

    numbers = []
    for chunk in version.split("-")[0].split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        numbers.append(digits or "0")
    while len(numbers) < 3:
        numbers.append("0")
    return ".".join(numbers[:3])


def make_msi(
    package_dir: Path,
    output: Path,
    *,
    version: str,
    icon: Path | None = None,
    license_rtf: Path | None = None,
    product_name: str = PRODUCT_NAME,
    manufacturer: str = MANUFACTURER,
    quiet: bool = False,
) -> Path:
    """把 `package_dir` 里的东西打成一个带安装界面的 MSI（WiX）。"""

    if sys.platform != "win32":
        raise SystemExit("MSI 只能在 Windows 上生成")

    root = Path(__file__).resolve().parents[1]
    package_dir = Path(package_dir).resolve()
    if not (package_dir / APP_EXE_RELATIVE).is_file():
        raise SystemExit(
            "包目录不对：找不到 %s\n（期望的是 PyInstaller onedir + 库 CLI 的目录）"
            % (package_dir / APP_EXE_RELATIVE)
        )
    wxs = root / "packaging" / "windows" / "app.wxs"
    if not wxs.is_file():
        raise SystemExit("缺少 WiX 定义：%s" % wxs)
    license_rtf = Path(license_rtf or (root / "packaging" / "windows" / "license.rtf"))
    if not license_rtf.is_file():
        raise SystemExit("缺少协议页 RTF：%s" % license_rtf)
    icon = Path(icon or (root / "packaging" / "app.ico"))

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    # 生成"填好文件清单"的 .wxs（WiX 4 没有自动收集目录的 <Files>，自己生成更可控）
    payload_xml, components = render_payload(package_dir)
    template = wxs.read_text(encoding="utf-8")
    rendered = template.replace("<!-- @@PAYLOAD@@ -->", payload_xml).replace(
        "<!-- @@FEATURE_COMPONENTS@@ -->",
        "\n".join(
            '      <ComponentRef Id="%s" />' % name for name in components
        ),
    )
    build_dir = output.parent / "wix"
    build_dir.mkdir(parents=True, exist_ok=True)
    generated = build_dir / "app.generated.wxs"
    generated.write_text(rendered, encoding="utf-8")

    command = [
        str(wix_executable()),
        "build",
        str(generated),
        "-arch", "x64",
        "-ext", "WixToolset.UI.wixext",
        "-o", str(output),
        "-d", "Version=%s" % msi_version(version),
        "-d", "UpgradeCode=%s" % UPGRADE_CODE,
        "-d", "PayloadDir=%s" % package_dir,
        "-d", "IconFile=%s" % icon,
        "-d", "LicenseRtf=%s" % license_rtf,
        "-d", "GuidShortcuts=%s" % stable_guid("start-menu-shortcuts"),
        "-d", "GuidDesktop=%s" % stable_guid("desktop-shortcut"),
        "-d", "GuidLanguage=%s" % stable_guid("language-registry"),
    ]
    if not quiet:
        print("开始构建 MSI：\n  " + " ".join(command))
    done = subprocess.run(command, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0 or not output.is_file():
        raise SystemExit("wix build 失败（退出码 %d）" % done.returncode)

    if not quiet:
        print("安装包（MSI）：%s（%s）" % (output, human(output.stat().st_size)))
    return output


def install_msi(msi: Path, *, target: Path | None = None, quiet: bool = True) -> int:
    """按用户安装（自检用）：`msiexec /i` + 可选 INSTALLDIR。"""

    command = ["msiexec", "/i", str(msi)]
    if quiet:
        command += ["/qn", "/norestart"]
    if target is not None:
        command.append("INSTALLDIR=%s" % target)
    return subprocess.call(command)


def uninstall_msi(msi: Path, *, quiet: bool = True) -> int:
    command = ["msiexec", "/x", str(msi), "/norestart"]
    if quiet:
        command.append("/qn")
    return subprocess.call(command)


def admin_extract(msi: Path, target: Path) -> int:
    """管理员安装 = 只解包不注册（验证 cab 与文件表用，不需要管理员权限）。"""

    target.mkdir(parents=True, exist_ok=True)
    return subprocess.call(
        ["msiexec", "/a", str(msi), "/qn", "TARGETDIR=%s" % target]
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return ("%d %s" if unit == "B" else "%.1f %s") % (value, unit)
        value /= 1024
    return "%d B" % size


def payload_files(package_dir: Path) -> list[Path]:
    """包里应当被安装的全部文件（用来跟解出来的结果对账）。"""

    return sorted(p for p in Path(package_dir).rglob("*") if p.is_file())


def verify_msi(msi: Path, package_dir: Path, work_dir: Path) -> tuple[bool, str]:
    """自检：管理员安装（只解包）→ 文件数对不对 → 关键文件在不在。

    管理员安装不需要管理员权限，也不会写注册表，适合在打包机上自动跑。
    （它会在解包根目录额外放一份 MSI 自己，所以对账时按"包里应有的文件"
    逐个查，而不是数总数。）
    """

    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    code = admin_extract(msi, work_dir)
    if code != 0:
        return False, "msiexec /a 退出码 %d（安装包解不开）" % code

    expected = payload_files(package_dir)
    # 解包出来的安装根：从"应用本体"反推（免得把目录链写死在这里）
    app_exe = [
        p for p in work_dir.rglob("LittleTilesReader.exe")
        if p.parent.name == "LittleTilesReader"
    ]
    if not app_exe:
        return False, "没有解出应用本体（LittleTilesReader\\LittleTilesReader.exe）"
    install_root = app_exe[0].parent

    missing: list[str] = []
    size_mismatch: list[str] = []
    for source in expected:
        relative = source.relative_to(package_dir)
        target = install_root / relative
        if not target.is_file():
            missing.append(relative.as_posix())
        elif target.stat().st_size != source.stat().st_size:
            size_mismatch.append(relative.as_posix())
    if missing:
        return False, "少了 %d 个文件，例如：%s" % (
            len(missing), "、".join(missing[:3])
        )
    if size_mismatch:
        return False, "有 %d 个文件大小不对，例如：%s" % (
            len(size_mismatch), "、".join(size_mismatch[:3])
        )
    # 库 CLI 与它的 dll 必须在同一层（reader.py 就是按这个找的）
    if not (install_root / "nbt++.dll").is_file():
        return False, "库 CLI 的依赖 nbt++.dll 不在安装根"
    return True, "%d 个文件全部就位、大小一致（安装根：%s）" % (
        len(expected), install_root.name
    )


def main() -> int:
    import argparse
    import tempfile

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from app import __version__          # noqa: PLC0415

    parser = argparse.ArgumentParser(description="把打包目录做成 Windows 安装包（MSI）")
    parser.add_argument("package", help="打包目录（dist/app/LittleTilesReader-<版本>-windows-x64）")
    parser.add_argument("--out", help="MSI 输出路径（默认放在打包目录旁）")
    parser.add_argument("--version", default=__version__, help="版本号（默认取 app.__version__）")
    parser.add_argument("--icon", default=str(root / "packaging" / "app.ico"))
    parser.add_argument("--check", action="store_true",
                        help="出包后立刻管理员安装解包一遍，核对文件数")
    parser.add_argument("--install", action="store_true", help="（自检用）真机按用户安装")
    parser.add_argument("--uninstall", action="store_true", help="（自检用）按 ProductCode 卸载")
    args = parser.parse_args()

    package_dir = Path(args.package).resolve()
    # 注意别用 with_suffix：目录名里的 "-0.1.0-windows-x64" 会被当成后缀切掉
    out = Path(args.out) if args.out else package_dir.parent / (package_dir.name + ".msi")
    msi = make_msi(package_dir, out, version=args.version, icon=Path(args.icon))
    print("SHA-256：%s" % sha256(msi))

    if args.check:
        with tempfile.TemporaryDirectory(prefix="ltr-msi-check-") as tmp:
            ok, note = verify_msi(msi, package_dir, Path(tmp) / "extract")
        print("%s 解包自检：%s" % ("[OK]" if ok else "[FAIL]", note))
        return 0 if ok else 1

    if args.install:
        code = install_msi(msi)
        print("msiexec /i 退出码：%d" % code)
        return code
    if args.uninstall:
        code = uninstall_msi(msi)
        print("msiexec /x 退出码：%d" % code)
        return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
