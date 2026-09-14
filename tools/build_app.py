"""把应用打成可分发目录/压缩包（M5 打包）。

**一条命令**：写构建信息 → 调 PyInstaller → 裁剪多余的 Qt → 打 zip → 打印 SHA-256。

用法（在仓库根跑）：

```sh
python tools/build_app.py                 # 当前平台，形态 A（不含 reader）
python tools/build_app.py --with-reader   # 形态 B：把 LittleTilesReader 也打进去（整包 GPL）
python tools/build_app.py --no-zip        # 只出目录，不压缩（调试用）
```

几个刻意的决定（对应 `docs/packaging.md`）：

* **onedir 而不是 onefile**：onefile 每次运行要解包到临时目录，配置与日志会跟着跑丢
  （应用按"可写数据目录"设计，见 `app/config.py` 的 `data_dir()`）；
* **显式排除**大件 Qt 模块（QtWebEngine 就有 598 MB）——应用只 import QtCore/QtGui/QtWidgets；
* **不给 reader 授权结论**：`--with-reader` 只是把文件拷进去，**分发包整体按
  GPL-3.0-or-later**（`docs/licenses.md`）；形态 A 不带 reader 时应用自身是 MIT；
* 图标：`packaging/app.ico` / `app.icns` 存在就用，不存在就跳过（不阻塞构建）。

产物：`dist/app/LittleTilesReader-<版本>-<平台>/`（+ 同名 `.zip`）。
"""

from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import __version__                                    # noqa: E402

DIST = ROOT / "dist" / "app"
BUILD = ROOT / "build" / "app"

#: 这些 Qt 模块用不到，但体积巨大（QtWebEngine 一个就 598 MB；QtMultimedia 还带 ffmpeg）。
#: 应用只 import QtCore / QtGui / QtWidgets（全仓 grep 确认过）。
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtQml", "PySide6.QtQmlModels", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtUiTools", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtSerialPort", "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors",
    "PySide6.QtSpatialAudio", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech",
    "PySide6.QtLocation", "PySide6.QtNetworkAuth", "PySide6.QtOpenGL",
    # 标准库里用不到的重件
    "tkinter", "unittest", "pydoc", "doctest",
]

#: 需要随包带上的数据（相对仓库根 → 包内相对路径）
DATA = [
    ("app/resources", "app/resources"),      # 像素字体 + 图标（OFL.txt 也在里面）
    ("app/data", "app/data"),                # block_ids.tsv（普通方块贴图要用）
    ("tools", "tools"),                      # 生成端脚本：进程内调用，必须随包
]


def platform_tag() -> str:
    """与服务器 `lt_read_download` 的平台键对齐：windows / macos-arm。"""

    if sys.platform.startswith("win"):
        return "windows-x64"
    machine = platform.machine().lower()
    return "macos-arm64" if machine in ("arm64", "aarch64") else "macos-x64"


def git_commit() -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return (done.stdout or "").strip()
    except Exception:
        return ""


def write_buildinfo() -> None:
    """写 `app/_buildinfo.py`（已 gitignore）——冻结后"哪一版"就靠它。"""

    target = ROOT / "app" / "_buildinfo.py"
    target.write_text(
        '"""构建信息，由 tools/build_app.py 生成（不要手改，已 gitignore）。"""\n\n'
        'COMMIT = "%s"\n'
        'BUILT_AT = "%s"\n'
        'PLATFORM = "%s"\n'
        % (
            git_commit(),
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            platform_tag(),
        ),
        encoding="utf-8",
    )
    print("构建信息：%s" % target.relative_to(ROOT))


def pyinstaller_command(name: str, with_reader: bool) -> list[str]:
    """拼 PyInstaller 参数（用命令行而不是 .spec：参数一眼能看全，便于复查）。"""

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", name,
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(BUILD),
    ]
    for relative, target in DATA:
        command += ["--add-data", "%s%s%s" % (relative, ";" if sys.platform.startswith("win") else ":", target)]
    for module in EXCLUDES:
        command += ["--exclude-module", module]
    icon = ROOT / "packaging" / ("app.ico" if sys.platform.startswith("win") else "app.icns")
    if icon.is_file():
        command += ["--icon", str(icon)]
    else:
        print("提示：没有 %s，这次不带图标（见 packaging/README.md）" % icon.relative_to(ROOT))
    command += [str(ROOT / "app" / "__main__.py")]
    if with_reader:
        print("形态 B：会把 LittleTilesReader 一起打进包 —— **整包按 GPL-3.0-or-later**（docs/licenses.md）")
    return command


def copy_reader(target_dir: Path, explicit: str | None = None) -> None:
    """把库编出来的 CLI 拷到包根（形态 B）。

    `--reader` 给了就用它（Windows 上常见 Release 目录），否则按 `ltgen.paths` 找。
    """

    if explicit:
        executable = Path(explicit).expanduser().resolve()
    else:
        from ltgen import paths

        executable = paths.reader_executable()
    if not executable.is_file():
        raise SystemExit(
            "找不到 LittleTilesReader：%s\n"
            "先在库仓库构建一次（见 docs/packaging-howto.md 的第 2 步），"
            "或显式指定 --reader <路径>" % executable
        )
    shutil.copy2(executable, target_dir / executable.name)
    # macOS 上动态库要跟着走（Windows 那边 CMake 会把 nbt++.dll 放到 exe 旁边）
    for lib in executable.parent.glob("*.dylib"):
        shutil.copy2(lib, target_dir / lib.name)
    print("已放入 reader：%s" % executable.name)


def copy_docs(target_dir: Path, with_reader: bool = False) -> None:
    """许可与说明随包发（LGPL/OFL/GPL 都要求带上文本，别漏）。"""

    for name in ("LICENSE", "THIRD-PARTY.md", "README-unsigned.md"):
        source = ROOT / "packaging" / name if name == "README-unsigned.md" else ROOT / name
        if source.is_file():
            shutil.copy2(source, target_dir / name)
    fonts_license = ROOT / "app" / "resources" / "fonts" / "OFL.txt"
    if fonts_license.is_file():
        shutil.copy2(fonts_license, target_dir / "OFL.txt")
    if with_reader:
        # 形态 B：分发包含 CGAL 的 GPL 代码，必须带上 GPL 全文（docs/licenses.md）
        licenses = ROOT / "packaging" / "licenses"
        for text in sorted(licenses.glob("*.txt")):
            shutil.copy2(text, target_dir / text.name)


def zip_dir(folder: Path) -> Path:
    archive = folder.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for item in sorted(folder.rglob("*")):
            if item.is_file():
                bundle.write(item, item.relative_to(folder.parent))
    return archive


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def human(size: int) -> str:
    return "%.1f MB" % (size / 1024 / 1024)


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 LittleTiles Reader 桌面应用")
    parser.add_argument("--with-reader", action="store_true",
                        help="把 LittleTilesReader 一起打进包（整包 GPL-3.0-or-later）")
    parser.add_argument("--reader", metavar="PATH",
                        help="LittleTilesReader 的位置（默认按 ltgen.paths 自动找）")
    parser.add_argument("--no-zip", action="store_true", help="只出目录，不压缩")
    parser.add_argument("--keep-buildinfo", action="store_true",
                        help="保留生成的 app/_buildinfo.py（默认保留；此开关只为显式表达）")
    args = parser.parse_args()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("缺 PyInstaller。先装：pip install pyinstaller")
        return 2

    write_buildinfo()
    name = "LittleTilesReader"
    command = pyinstaller_command(name, args.with_reader)
    print("开始构建：\n  " + " ".join(command))
    code = subprocess.call(command)
    if code != 0:
        return code

    # 产物目录：<dist>/<name>；再包一层"带版本与平台"的名字，方便上传到发布页
    built = DIST / name
    if not built.is_dir():
        print("构建结束但没找到产物目录：%s" % built)
        return 1
    target = DIST / ("%s-%s-%s" % (name, __version__, platform_tag()))
    if target.exists():
        shutil.rmtree(target)
    built.rename(target)

    if args.with_reader:
        copy_reader(target, args.reader)
    copy_docs(target, args.with_reader)

    total = sum(item.stat().st_size for item in target.rglob("*") if item.is_file())
    print("产物目录：%s（%s）" % (target, human(total)))
    if not args.no_zip:
        archive = zip_dir(target)
        print("压缩包：%s（%s）" % (archive, human(archive.stat().st_size)))
        print("SHA-256：%s" % sha256(archive))
        print("把上面这行 SHA-256 与下载地址填进后台「LT 读取器 → 客户端下载」即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
