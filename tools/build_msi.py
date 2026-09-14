"""把打包目录做成一个 Windows 安装包（MSI）。

为什么是 MSI 而不是"再发一个 zip"：用户双击就装、在"应用和功能"里能看到、
能干净卸载；公司/学校机器上 MSI 也通常比 exe 安装器更容易被允许。

为什么不用 WiX：WiX 要单独装工具链（`dotnet tool install --global wix`），而
**Python 自带的 `msilib`** 就能建出合法的 MSI——本来 `distutils` 的 `bdist_msi`
也是这么干的。少一个构建依赖，谁克隆下来都能出包。

⚠️ `msilib` 在 **Python 3.13 被移除**了。本仓库的构建环境是 3.11；将来换解释器时，
要么用 3.12 及以下打包，要么改走 WiX（那时把这一层换掉即可，产物形态不变）。

安装形态（几个刻意的决定）：

* **按用户安装**（`ALLUSERS=2` + `MSIINSTALLPERUSER=1`）：装到
  `%LOCALAPPDATA%\\Programs\\LittleTilesReader`，**不弹 UAC、不要管理员**；
* 装在那儿正好可写，于是应用自己的"数据目录 = 应用所在文件夹"（便携模式）成立，
  config/logs/outputs 就在安装目录里（`docs/packaging.md` §2.1）；
* 开始菜单 + 桌面各一个快捷方式；
* **固定 UpgradeCode + 每版本一个 ProductCode**：以后发新版时，装新版会自动
  卸掉旧版（大版本升级），而不是在"应用和功能"里堆两个。

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


def _clean(text: str) -> str:
    return "".join(ch for ch in text.upper() if ch.isalnum() or ch == "_")


def short_dir_name(name: str, taken: set) -> str:
    """目录的 8.3 短名（MSI 的 DefaultDir 要求 `短名|长名`）。"""

    cleaned = _clean(name) or "D"
    if cleaned[0].isdigit():
        cleaned = "D" + cleaned
    base = cleaned[:8]
    candidate = base
    index = 1
    while candidate.upper() in taken:
        suffix = "~%d" % index
        candidate = cleaned[: max(1, 8 - len(suffix))] + suffix
        index += 1
    taken.add(candidate.upper())
    return candidate


def short_file_name(name: str, taken: set) -> str:
    """文件的 8.3 短名：`名字~n.扩展名`（扩展名最多留 3 位）。"""

    stem, dot, extension = name.rpartition(".")
    if not dot:
        stem, extension = name, ""
    stem = _clean(stem) or "F"
    extension = _clean(extension)[:3]
    room = 8 - (len(extension) + 1 if extension else 0)
    base = stem[: max(1, room)]
    candidate = base + (("." + extension) if extension else "")
    index = 1
    while candidate.upper() in taken:
        suffix = "~%d" % index
        base = stem[: max(1, room - len(suffix))] + suffix
        candidate = base + (("." + extension) if extension else "")
        index += 1
    taken.add(candidate.upper())
    return candidate


def dir_default(name: str, taken: set | None = None) -> str:
    """DefaultDir 的写法：不是合法 8.3 名字时用 `短名|长名`。

    只写长名在多数机器上也能装上，但那是"安装器自己编短名"，属于运气；
    显式给出两个名字才是规矩里写清楚的写法（ICE 也不会报警告）。
    """

    taken = taken if taken is not None else set()
    # 8.3 兼容（≤8 个字符、没有空格/特殊字符）时，长短名本来就是同一个
    if len(name) <= 8 and all(ch.isalnum() or ch in "_-" for ch in name):
        taken.add(name.upper())
        return name
    return "%s|%s" % (short_dir_name(name, taken), name)


def file_default(name: str, taken: set) -> str:
    """File 表的 FileName 列：8.3 兼容就直接写，否则 `短名|长名`。"""

    stem, dot, extension = name.rpartition(".")
    short_ok = (
        len(name) <= 12
        and len(stem) <= 8
        and (not dot or len(extension) <= 3)
        and all(ch.isalnum() or ch in "_-$" for ch in name)
    )
    if short_ok:
        taken.add(name.upper())
        return name
    return "%s|%s" % (short_file_name(name, taken), name)


def product_code(version: str) -> str:
    """每个版本一个 ProductCode：升级时靠 UpgradeCode 认出旧版并卸掉它。"""

    return "{%s}" % uuid.uuid5(uuid.NAMESPACE_URL, "%s/%s" % (_SEED, version))


def msi_version(version: str) -> str:
    """MSI 的 ProductVersion 只能是 `主.次.修订`（最多三段数字，不能带后缀）。

    应用版本带 `-beta` 这类后缀时，取数字前缀（`0.1.0-beta` → `0.1.0`）；
    后缀本身照旧出现在包名与 README 里。
    """

    numbers = []
    for chunk in version.split("-")[0].split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        numbers.append(digits or "0")
    while len(numbers) < 3:
        numbers.append("0")
    return ".".join(numbers[:3])


def _require_msilib():
    try:
        import msilib  # noqa: PLC0415 (只在需要时导入：非 Windows 上没有)
        import msilib.schema  # noqa: PLC0415,F401 (表结构：schema 表 + sequence 序列)
        import msilib.sequence  # noqa: PLC0415,F401
    except ImportError:      # pragma: no cover - 取决于解释器版本
        raise SystemExit(
            "这台 Python 里没有 msilib（Python 3.13 起被移除）。\n"
            "用 Python 3.11/3.12 打包，或改用 WiX 生成 MSI。"
        )
    return msilib


class _TreeBuilder:
    """把打包目录登记进 MSI 的 Directory / Component / File 表，并把文件塞进 cabinet。

    为什么不用 `msilib.Directory`：那个类把"安装到哪"和"从哪读文件"绑成一件事
    （`绝对路径 = 父目录的绝对路径 + physical`），于是源目录必须长得跟安装目录一样。
    我们的包是"一个平铺目录"，装到 `%LOCALAPPDATA%\\Programs\\…` 下，两者对不上——
    照那样写会把源路径算成 `<包目录>\\Programs\\LittleTilesReader\\…`（不存在）。
    所以这里只手写表行：目录是纯元数据，文件走 `CAB.append()`。
    """

    #: msidbComponentAttributes64bit：64 位 MSI 的组件要带这一位
    COMPONENT_64BIT = 256
    #: msidbFileAttributesVital：装不上就算失败，而不是跳过
    FILE_VITAL = 512

    def __init__(self, msilib, db, cab, feature_id: str) -> None:
        self.msilib = msilib
        self.db = db
        self.cab = cab
        self.feature_id = feature_id
        self._dir_ids = {"TARGETDIR", "LocalAppDataFolder", "ProgramsFolder",
                         "INSTALLDIR", "ProgramMenuFolder", "LTRStartMenuFolder",
                         "DesktopFolder"}
        self._component_ids = set()

    # ---- 唯一命名 --------------------------------------------------------

    def _directory_id(self, base: str) -> str:
        candidate = self.msilib.make_id(base)
        index = 1
        while candidate in self._dir_ids:
            candidate = "%s_%d" % (self.msilib.make_id(base), index)
            index += 1
        self._dir_ids.add(candidate)
        return candidate

    def _component_id(self, base: str) -> str:
        candidate = base
        index = 1
        while candidate in self._component_ids:
            candidate = "%s_%d" % (base, index)
            index += 1
        self._component_ids.add(candidate)
        return candidate

    # ---- 递归 ------------------------------------------------------------

    def add(self, folder: Path, directory_id: str) -> str:
        """把 `folder` 里的文件登记进 `directory_id`，返回这个目录的组件名。"""

        component = self._component_id(self.msilib.make_id(directory_id))
        self.msilib.add_data(self.db, "Component", [
            (component, self.msilib.gen_uuid(), directory_id,
             self.COMPONENT_64BIT, None, None),
        ])
        self.msilib.add_data(self.db, "FeatureComponents", [(self.feature_id, component)])

        file_short_names: set = set()
        for item in sorted(folder.iterdir(), key=lambda p: (p.is_dir(), p.name.lower())):
            if item.is_file():
                sequence, logical = self.cab.append(str(item), item.name, None)
                self.msilib.add_data(self.db, "File", [
                    (logical, component, file_default(item.name, file_short_names),
                     item.stat().st_size, None, None, self.FILE_VITAL, sequence),
                ])
            elif item.is_dir():
                sub_id = self._directory_id(item.name)
                self.msilib.add_data(self.db, "Directory", [
                    (sub_id, directory_id, dir_default(item.name)),
                ])
                self.add(item, sub_id)
        return component


def make_msi(
    package_dir: Path,
    output: Path,
    *,
    version: str,
    icon: Path | None = None,
    product_name: str = PRODUCT_NAME,
    manufacturer: str = MANUFACTURER,
    quiet: bool = False,
) -> Path:
    """把 `package_dir` 里的东西打成一个按用户安装的 MSI。"""

    if sys.platform != "win32":
        raise SystemExit("MSI 只能在 Windows 上生成")
    msilib = _require_msilib()

    package_dir = Path(package_dir).resolve()
    if not (package_dir / APP_EXE_RELATIVE).is_file():
        raise SystemExit(
            "包目录不对：找不到 %s\n（期望的是 PyInstaller onedir + 库 CLI 的目录）"
            % (package_dir / APP_EXE_RELATIVE)
        )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    numeric = msi_version(version)
    db = msilib.init_database(
        str(output), msilib.schema, product_name, product_code(version), numeric,
        manufacturer,
    )
    # 大版本升级：让 RemoveExistingProducts 排在 InstallValidate(1400) 与
    # InstallInitialize(1500) 之间 —— 先卸掉旧版，再装新版。它本来就在标准序列里
    # （只是排在很后面），所以这里改顺序号而不是插一行（插会撞主键）。
    msilib.change_sequence(
        msilib.sequence.InstallExecuteSequence, "RemoveExistingProducts", 1450
    )
    msilib.add_tables(db, msilib.sequence)

    props = [
        # **每机器安装**（ALLUSERS=1，装进 Program Files）—— MSI 的常规形态：
        # 双击会弹一次 UAC，装完在"应用和功能"里能看到、能卸载。
        #
        # 为什么不用"按用户安装"（装到 %LOCALAPPDATA%）：实测过三种写法，
        # 只要这台机器上的用户属于管理员组，Windows Installer 都会选**每机器**
        # 形态（注册进 HKLM），而按用户目录链把文件放进 %LOCALAPPDATA% ——
        # 注册形态与文件位置对不上，卸载时会留下孤儿。真正"强制按用户"
        # （ALLUSERS 空值）在 msilib 里连写进 Property 表都不允许。
        #
        # 装到 Program Files 正好落在应用已经照顾过的情形：安装目录不可写时，
        # `app/config.py:data_dir()` 会把数据放 %LOCALAPPDATA%\LittleTilesReader
        # 并在首次启动提示一句。不想装、或没有管理员权限的人用便携 zip。
        ("ALLUSERS", "1"),
        ("ARPINSTALLLOCATION", "INSTALLDIR"),
        ("UpgradeCode", UPGRADE_CODE),
        # "应用和功能"里显示什么、能不能点"修改"
        ("ARPCOMMENTS", "LittleTiles 存档 / 结构导出工具（OBJ + 贴图）"),
        ("ARPCONTACT", manufacturer),
        ("ARPURLINFOABOUT", "https://github.com/Gaksy/Minecraft-Littletiles-Reader-App"),
        ("ARPNOMODIFY", "1"),
        ("ARPNOREPAIR", "1"),
        ("DiskPrompt", product_name),
    ]
    if icon is not None and Path(icon).is_file():
        # 图标直接进 Icon 表（Data 列是流）：ARP（应用和功能）里显示的就是它
        stream = "LTR_PRODUCT_ICON.ICO"
        msilib.add_data(db, "Icon", [(stream, msilib.Binary(str(icon)))])
        props.append(("ARPPRODUCTICON", stream))
    msilib.add_data(db, "Property", props)

    # 目录树：TARGETDIR → Program Files\LittleTilesReader（= INSTALLDIR）。
    # 这些只是表里的"安装到哪"，跟源目录无关（源文件由 CAB 直接收）。
    start_menu_taken: set = set()
    msilib.add_data(db, "Directory", [
        ("TARGETDIR", None, "SourceDir"),
        ("ProgramFiles64Folder", "TARGETDIR", "."),
        ("INSTALLDIR", "ProgramFiles64Folder", dir_default(INSTALL_DIR_NAME)),
        ("ProgramMenuFolder", "TARGETDIR", "."),
        ("LTRStartMenuFolder", "ProgramMenuFolder",
         dir_default(product_name, start_menu_taken)),
        ("DesktopFolder", "TARGETDIR", "."),
    ])
    # 功能（用户视角的一整块）：默认全部安装
    msilib.add_data(db, "Feature", [
        ("DefaultFeature", None, product_name, "应用与本地导出引擎", 1, 1,
         "INSTALLDIR", 0),
    ])

    cab = msilib.CAB("LittleTilesReader")
    install_component = _TreeBuilder(
        msilib, db, cab, "DefaultFeature"
    ).add(package_dir, "INSTALLDIR")
    cab.commit(db)

    # 快捷方式：非广告式（Target 直接写展开后的路径）
    if install_component:
        target_exe = "[INSTALLDIR]%s" % str(APP_EXE_RELATIVE)
        working = "[INSTALLDIR]%s" % APP_EXE_RELATIVE.parent
        rows = [
            ("LTRStartMenuShortcut", "LTRStartMenuFolder",
             "LittleTilesReader|LittleTiles Reader", install_component,
             target_exe, None, "LittleTiles Reader", None, None, None, 1, working),
            ("LTRDesktopShortcut", "DesktopFolder",
             "LittleTilesReader|LittleTiles Reader", install_component,
             target_exe, None, "LittleTiles Reader", None, None, None, 1, working),
        ]
        msilib.add_data(db, "Shortcut", rows)

    # 大版本升级：装新版时先卸掉旧版（UpgradeCode 相同、版本更低者）。
    # Attributes=1 = VersionMinInclusive；VersionMax 不含（默认）→ 只命中更低的版本。
    # 动作本身已经在标准序列里了，顺序号在上面用 change_sequence 改过。
    msilib.add_data(db, "Upgrade", [
        (UPGRADE_CODE, None, numeric, None, 1, None, "LTR_UPGRADE_DETECTED"),
    ])
    db.Commit()
    db.Close()

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
