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

产物：`dist/app/LittleTilesReader-<版本>-<平台>/`
      + 同名 `.zip`（通用/备用）
      + macOS 上再出 `.dmg`、Windows 上再出 `.msi`——这两个才是用户双击安装的那个。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import __version__                                    # noqa: E402

DIST = ROOT / "dist" / "app"
BUILD = ROOT / "build" / "app"
#: PyInstaller 自己的输出目录（**不直接发**）。macOS 上它会同时产出两份内容：
#: `LittleTilesReader.app`（自包含，用户双击的就是它）和 `LittleTilesReader/`
#: （裸 onedir，`.app` 就是从这份内容拼出来的）。两份一起发 = Qt 打两遍、体积翻倍，
#: 所以先落到这里，下面只挑一份搬进最终目录。
SCRATCH = BUILD / "dist"

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

#: MSVC 运行时 DLL。conda 环境里会有**两份**（`<env>\Library\bin` 一份、
#: `site-packages\PySide6\` 一份），版本还不一样；PyInstaller 各收各的，于是包里
#: 出现两个不同版本的 `MSVCP140.dll`。Windows 加载器先命中 `_internal\` 那份旧的，
#: 而按新版编译的 Qt6Widgets 要的导出符它没有 —— 实测报
#: `ImportError: DLL load failed while importing QtWidgets: The specified procedure
#: could not be found.`（冻包能构建、双击起不来）。所以打完包必须统一成同一份。
MSVC_RUNTIME_NAMES = (
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    "vcruntime140.dll", "vcruntime140_1.dll", "concrt140.dll",
)

#: PATH 里这些目录带着**别的版本**的同名 DLL（实测：Codex 运行时自带 poppler/libheif，
#: 里面是 ICU 78，而 conda 的 PySide6 是照 ICU 73 编的）。PyInstaller 顺着 PATH 分析
#: 依赖时会把 78 收进包 —— Qt6Core 加载时报
#: `The specified procedure could not be found`（ICU 的符号名带版本后缀，换了大版本就对不上）。
#: 所以打包时把这类目录从 PATH 里剔掉，并且**打完包用干净环境真跑一次自检**兜底。
PATH_TOXIC_MARKERS = (
    r".cache\codex-runtimes\\",
    r".codex\tmp\arg0\\",
)

#: 这些运行时依赖一律以**构建环境（conda 环境）里的那份**为准：PyInstaller 有可能从
#: PATH 里收到同名但版本不同的文件（见上）。
ENV_AUTHORITATIVE_DEPS = ("zlib", "zstd", "libssl", "libcrypto", "pcre2")

#: **绝不随包带的依赖：ICU。**
#:
#: 这台机器上能拿到的 ICU（conda 的 73、代理运行时的 78）导出的符号是**带版本后缀**的
#: （`ucnv_open_73` / `ucnv_open_78`），而 Windows 自带的 ICU（Win10 1903+ 的 `icu.dll`，
#: 由 System32 的 `icuuc.dll` 转发）导出的是**无后缀**的 `ucnv_open` —— conda 的
#: PySide6/Qt6Core 恰好按后者编译（实测：pefile 逐个比对导入/导出表）。
#:
#: 所以 PyInstaller 顺手把 73/78 打进包，反而**盖住系统那份正确的**，Qt6Core 加载时报
#: `The specified procedure could not be found`（构建成功、双击起不来）。
#: 结论：这类 DLL 一份都不许进包，交给系统。代价是要求 Windows 10 1903+ / 11。
NEVER_BUNDLE_STEMS = ("icuuc", "icuin", "icuio", "icutu", "icudt", "icutest")


def _local_dll_dirs() -> list[Path]:
    """当前 Python 环境里放 DLL 的几个目录（PySide6 在最前，它才是 Qt 的家）。

    conda 的 **env 常常不自带 ICU**（实测：`envs/<名字>` 里没有 icu*.dll，真正那份在
    base 安装的 `Library\\bin`），所以要把 base 的目录也带上 —— 否则"对齐"会把包里的
    ICU 删掉却没有替换，冻包直接起不来。
    """

    env_root = Path(sys.executable).resolve().parent
    roots = [env_root]
    for parent in env_root.parents:
        if (parent / "conda-meta").is_dir() or (parent / "Library" / "bin").is_dir():
            roots.append(parent)
        if len(roots) >= 3:
            break
    candidates: list[Path] = []
    for root in roots:
        candidates += [
            root / "Lib" / "site-packages" / "PySide6",
            root / "Lib" / "site-packages" / "shiboken6",
            root / "Library" / "bin",
            root / "DLLs",
            root,
        ]
    seen: set[Path] = set()
    result: list[Path] = []
    for path in candidates:
        if path.is_dir() and path not in seen:
            seen.add(path)
            result.append(path)
    return result


def clean_build_env() -> dict:
    """给 PyInstaller 用的环境：PATH 里剔掉会带错版本 DLL 的目录。"""

    env = dict(os.environ)
    entries = []
    for entry in env.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        lowered = entry.lower()
        if any(marker.lower() in lowered for marker in PATH_TOXIC_MARKERS):
            continue
        entries.append(entry)
    # 本环境的 DLL 目录放最前面，依赖解析先看它们
    env["PATH"] = os.pathsep.join([str(p) for p in _local_dll_dirs()] + entries)
    return env


def align_runtime_dependencies(package_dir: Path) -> list[str]:
    """收拾包里那几个"运行时会找错"的依赖。

    两件事：
    1. `NEVER_BUNDLE_STEMS`（ICU 一族）**全部删掉** —— 它们会盖住 Windows 自带那份，
       而 Qt 要的正是系统那份无版本后缀的 ABI（详见常量上的注释）；
    2. 其余同名依赖（zlib / openssl / pcre2…）以构建环境里的那份为准：环境里是什么
       版本，包里就是什么版本；环境里没有同名文件、包里却有的，删掉。
    """

    dirs = _local_dll_dirs()
    aligned: list[str] = []

    if NEVER_BUNDLE_STEMS:
        for path in sorted(package_dir.rglob("*.dll")):
            name = path.name.lower()
            if any(name.startswith(stem) for stem in NEVER_BUNDLE_STEMS):
                path.unlink()
                aligned.append("-%s" % path.name)

    for stem in ENV_AUTHORITATIVE_DEPS:
        env_files = {
            path.name.lower(): path
            for directory in dirs
            for path in directory.glob("%s*.dll" % stem)
        }
        packaged = [
            path
            for path in package_dir.rglob("*")
            if path.is_file() and path.name.lower().startswith(stem)
            and path.name.lower().endswith(".dll")
        ]
        if not packaged:
            continue
        for path in packaged:
            wanted = env_files.get(path.name.lower())
            if wanted is not None:
                if path.read_bytes() != wanted.read_bytes():
                    shutil.copyfile(wanted, path)
                    aligned.append(path.name)
            else:
                # 环境里没有这个文件名（例如 icudt78 对 icudt73）：留着只会被优先加载
                path.unlink()
                aligned.append("-%s" % path.name)
    return aligned


def verify_frozen_app(package_dir: Path, *, timeout: int = 120) -> tuple[bool, str]:
    """在**干净环境**里跑一次冻包自检 —— 这是唯一能挡住"构建成功但双击起不来"的检查。

    清掉 PATH（只留 System32）是刻意的：本机的 conda / 代理运行时会带一堆同名 DLL，
    不清干净就会"在我这儿能跑、用户那儿报 DLL load failed"。
    """

    exe = package_dir / "LittleTilesReader" / "LittleTilesReader.exe"
    if not exe.is_file():
        return False, "找不到应用本体：%s" % exe
    env = {
        "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
        "windir": os.environ.get("windir", r"C:\Windows"),
        "TEMP": os.environ.get("TEMP", r"C:\Windows\Temp"),
        "TMP": os.environ.get("TMP", r"C:\Windows\Temp"),
        "PATH": os.pathsep.join([
            os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "system32"),
            os.environ.get("SystemRoot", r"C:\Windows"),
        ]),
    }
    with tempfile.TemporaryDirectory(prefix="ltr-frozen-check-") as home:
        env["LTR_HOME"] = home
        process = subprocess.Popen(
            [str(exe), "--self-check"],
            cwd=str(package_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            out, err = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            return False, "自检超时（多半弹了报错对话框卡住）"
    text = (out or "") + (err or "")
    if process.returncode == 0 and "全部通过" in text:
        return True, "冻包自检通过（干净环境）"
    tail = "\n".join(line for line in text.strip().splitlines()[-6:])
    return False, "自检没通过（退出码 %s）：\n%s" % (process.returncode, tail)


def unify_msvc_runtime(package_dir: Path) -> list[str]:
    """把包里重复的 MSVC 运行时统一成同一份（优先用系统的，它向后兼容且更新）。"""

    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    unified: list[str] = []
    for name in MSVC_RUNTIME_NAMES:
        copies = [p for p in package_dir.rglob("*") if p.name.lower() == name]
        if not copies:
            continue
        system_copy = system32 / name
        if system_copy.is_file():
            source = system_copy
        else:
            source = max(copies, key=lambda p: p.stat().st_size)
        for copy in copies:
            if copy.samefile(source):
                continue
            shutil.copyfile(source, copy)
        unified.append(name)
    return unified


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


#: `tools/*.py` 里的 import 语句（`from x import y` / `import x.y` 都算）。
_IMPORT_PATTERN = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", re.MULTILINE)

def tool_hidden_imports() -> list[str]:
    """扫运行时加载的工具用到哪些模块，转成 `--hidden-import`。

    这些脚本是**运行时按路径**加载的（`app/generators.py` 用 `importlib`），
    PyInstaller 的静态分析看不到它们依赖什么。真机上就踩过一次：
    打包版点「重新组合素材」直接
    `No module named ltgen.console`——因为只有被 app 自己 import 的
    `ltgen.paths` / `ltgen.lint` 进了包。

    标准库与 `tools/` 自己的兄弟模块（脚本会把 `tools/` 塞进 sys.path）不用管；
    `ltgen` 交给 `--collect-submodules`，`app` 是静态收集的，都不重复列。
    """

    # 只扫"应用运行时会加载"的那几个（单一事实来源在 app/generators.py）：
    # tools/ 下还有 build_app.py / make_app_icon.py 这种只在打包机器上跑的脚本，
    # 它们 import 的 PyInstaller 之类不能跟着进包。
    from app.generators import TOOL_NAMES

    local = {path.stem for path in (ROOT / "tools").glob("*.py")}
    found: set[str] = set()
    for name in TOOL_NAMES:
        path = ROOT / "tools" / ("%s.py" % name)
        if not path.is_file():
            continue
        for name in _IMPORT_PATTERN.findall(path.read_text(encoding="utf-8")):
            top = name.split(".")[0]
            if top in local or top in ("ltgen", "app") or top in sys.stdlib_module_names:
                continue
            found.add(name)
    return sorted(found)


def pyinstaller_command(name: str, with_reader: bool) -> list[str]:
    """拼 PyInstaller 参数（用命令行而不是 .spec：参数一眼能看全，便于复查）。"""

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", name,
        "--distpath", str(SCRATCH),
        "--workpath", str(BUILD),
        "--specpath", str(BUILD),
        # ltgen 整个包都要：tools/*.py 里 import 了 ltgen.console / manifest / tint，
        # 而那些脚本是运行时按路径加载的，静态分析看不到（见 tool_hidden_imports）。
        "--collect-submodules", "ltgen",
    ]
    for module in tool_hidden_imports():
        command += ["--hidden-import", module]
    if sys.platform == "darwin":
        command += ["--osx-bundle-identifier", "work.inception.littletiles-reader"]
    for relative, target in DATA:
        # 源路径必须写绝对路径：--specpath 指向 build/，相对路径会被当成
        # 相对 build/ 解析（`app/resources` → `build/app/app/resources`，直接报找不到）。
        source = ROOT / relative
        separator = ";" if sys.platform.startswith("win") else ":"
        command += ["--add-data", "%s%s%s" % (source, separator, target)]
    for module in EXCLUDES:
        command += ["--exclude-module", module]
    icon = ROOT / "packaging" / ("app.ico" if sys.platform.startswith("win") else "app.icns")
    if icon.is_file():
        command += ["--icon", str(icon)]
    else:
        print("提示：没有 %s，这次不带图标（见 packaging/README.md）" % icon.relative_to(ROOT))
    # 入口用 packaging/entry.py 而不是 app/__main__.py：后者是给 `python -m app`
    # 用的、通篇相对导入，被 PyInstaller 当脚本跑时会 ImportError（见该文件注释）。
    command += [str(ROOT / "packaging" / "entry.py")]
    if with_reader:
        print("形态 B：会把 LittleTilesReader 一起打进包 —— **整包按 GPL-3.0-or-later**（docs/licenses.md）")
    return command


def copy_reader(target_dir: Path, explicit: str | None = None,
                app_bundle: Path | None = None) -> None:
    """把库编出来的 CLI 拷到包根（形态 B）。

    `--reader` 给了就用它（Windows 上常见 Release 目录），否则按 `ltgen.paths` 找。

    macOS 上传了 `app_bundle` 就**塞进 .app 里面**
    （`Contents/Frameworks/reader/`）：这样 DMG 里只有一个 `.app`，用户拖一个就完事，
    不用理解"旁边还得跟着两个文件"。Windows 没有 .app 这层，仍然放在包根。
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
    lib_dir = target_dir
    if app_bundle is not None:
        lib_dir = app_bundle / "Contents" / "Frameworks" / "reader"
        lib_dir.mkdir(parents=True, exist_ok=True)
    destination = lib_dir / executable.name
    shutil.copy2(executable, destination)
    print("已放入 reader：%s" % destination.relative_to(target_dir))
    if sys.platform == "darwin":
        relocate_macos_libraries(destination, lib_dir)
    else:
        # Windows：CMake 会把 nbt++.dll 放在 exe 旁边（或 vcpkg 的 bin 里），一起拷走
        for lib in executable.parent.glob("*.dll"):
            shutil.copy2(lib, lib_dir / lib.name)


#: 系统自带的库不用跟着走（用户机器上一定有）。
SYSTEM_LIBRARY_PREFIXES = ("/usr/lib/", "/System/", "/Library/Apple/")


def otool_lines(executable: Path, flag: str) -> list[str]:
    """跑 `otool <flag>` 并把输出按行返回（没装 otool 时返回空表）。"""

    done = subprocess.run(
        ["otool", flag, str(executable)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return (done.stdout or "").splitlines()


def macho_dependencies(executable: Path) -> list[str]:
    """`otool -L` 里的非系统依赖（含 `@rpath/...` 这种相对写法）。"""

    found: list[str] = []
    for line in otool_lines(executable, "-L")[1:]:
        name = line.strip().split(" (compatibility version")[0].strip()
        if not name or name.startswith(SYSTEM_LIBRARY_PREFIXES):
            continue
        found.append(name)
    return found


def macho_rpaths(executable: Path) -> list[str]:
    """`otool -l` 里的 LC_RPATH 列表（库构建产物里通常写的是本机绝对路径）。"""

    paths: list[str] = []
    expect_path = False
    for line in otool_lines(executable, "-l"):
        stripped = line.strip()
        if stripped == "cmd LC_RPATH":
            expect_path = True
            continue
        if expect_path and stripped.startswith("path "):
            paths.append(stripped[5:].split(" (offset")[0].strip())
            expect_path = False
    return paths


def resolve_dependency(name: str, executable: Path) -> Path | None:
    """把 `otool -L` 里的名字解析成真实文件。

    `@rpath/libnbt++.dylib` 这种要拿 LC_RPATH 去凑（本机构建时那是源码树里的
    `_deps/libnbtplusplus-build`，别人机器上不存在——所以必须重写成
    `@executable_path/...` 才能随包分发）。
    """

    bases: list[Path] = []
    if name.startswith(("@rpath/", "@loader_path/", "@executable_path/")):
        leaf = name.split("/", 1)[1]
        bases = [Path(base) / leaf for base in macho_rpaths(executable)]
        bases += [
            executable.parent / leaf,
            executable.parent / "lib" / leaf,
            executable.parent / "_deps" / "libnbtplusplus-build" / leaf,
            executable.parent.parent / "lib" / leaf,
        ]
    else:
        bases = [Path(name)]
    for candidate in bases:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def relocate_macos_libraries(executable: Path, target_dir: Path) -> None:
    """把 CLI 的动态库依赖搬到包根，并把安装名改写成 `@executable_path/...`。

    不改的话，那个绝对 rpath（指向本机的构建目录）在用户机器上不存在，
    一运行就是 `Library not loaded: @rpath/libnbt++.dylib`。
    """

    moved: list[str] = []
    for name in macho_dependencies(executable):
        source = resolve_dependency(name, executable)
        if source is None:
            print("警告：找不到这个依赖，先跳过：%s" % name)
            continue
        destination = target_dir / source.name
        if not destination.is_file():
            shutil.copy2(source, destination)
        relative = "@executable_path/%s" % source.name
        # 库自己要知道"我被谁引用"（install id），可执行文件要知道去哪找
        subprocess.run(["install_name_tool", "-id", relative, str(destination)], check=False)
        subprocess.run(["install_name_tool", "-change", name, relative, str(executable)], check=False)
        moved.append("%s → %s" % (name, relative))

    if moved:
        existing = macho_rpaths(executable)
        if not any(path.startswith("@executable_path") for path in existing):
            subprocess.run(["install_name_tool", "-add_rpath", "@executable_path", str(executable)],
                           check=False)
        # 依赖已经改成 @executable_path/...，那些指向本机构建目录的 rpath 留着只会碍事
        for path in existing:
            if not path.startswith("@executable_path"):
                subprocess.run(["install_name_tool", "-delete_rpath", path, str(executable)],
                               check=False)
        # arm64 上改过 Mach-O 会作废原来的签名，必须重新做一次 ad-hoc 签名，
        # 否则用户机器上直接 "code signature invalid" 被杀。
        sign_macos(target_dir)
        for line in moved:
            print("已随包：%s" % line)


def sign_macos(target_dir: Path) -> None:
    """对包里的可执行文件做 ad-hoc 签名（未签名发布版的前提，见 packaging/README-unsigned.md）。"""

    if sys.platform != "darwin":
        return
    for item in sorted(target_dir.rglob("*")):
        if not item.is_file():
            continue
        if item.suffix == ".dylib" or item.name.startswith("LittleTilesReader"):
            if item.name.endswith(".app"):
                continue
            subprocess.run(["codesign", "--force", "--sign", "-", str(item)], check=False,
                           capture_output=True)
    app = next(iter(target_dir.glob("*.app")), None)
    if app is not None:
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)],
                       check=False, capture_output=True)


def copy_docs(target_dir: Path, with_reader: bool = False,
              app_bundle: Path | None = None) -> None:
    """许可与说明随包发（LGPL/OFL/GPL 都要求带上文本，别漏）。

    macOS 上传了 `app_bundle` 就放进 `Contents/Resources/`——理由同 copy_reader：
    DMG 里只有一个 `.app`，文本跟着 app 一起走（`app/licenses.py` 会去那儿找全文
    给用户翻）。
    """

    if app_bundle is not None:
        target_dir = app_bundle / "Contents" / "Resources"
        target_dir.mkdir(parents=True, exist_ok=True)

    for name in ("LICENSE", "THIRD-PARTY.md", "README-unsigned.md"):
        source = ROOT / "packaging" / name if name == "README-unsigned.md" else ROOT / name
        if source.is_file():
            shutil.copy2(source, target_dir / name)
    fonts_license = ROOT / "app" / "resources" / "fonts" / "OFL.txt"
    if fonts_license.is_file():
        shutil.copy2(fonts_license, target_dir / "OFL.txt")
    # 许可全文：LGPL（Qt）与 OFL（字体）**任何形态都要带**；
    # GPL / BSL / zlib 是库那边的，只在"含库完整包"时需要（docs/licenses.md）
    licenses_dir = ROOT / "packaging" / "licenses"
    always = ["LGPL-3.0.txt"]
    if with_reader:
        always += ["GPL-3.0.txt", "BSL-1.0.txt", "zlib.txt"]
    (target_dir / "licenses").mkdir(exist_ok=True)
    for name in always:
        source = licenses_dir / name
        if source.is_file():
            shutil.copy2(source, target_dir / "licenses" / name)


def zip_dir(folder: Path) -> Path:
    # 注意别用 with_suffix：`LittleTilesReader-0.1.0-macos-arm64` 会被当成
    # "名字 .0-macos-arm64 后缀"，直接砍成 `LittleTilesReader-0.1.zip`。
    archive = folder.parent / (folder.name + ".zip")
    if archive.exists():
        archive.unlink()
    if sys.platform == "darwin":
        # 必须用 ditto：Python 的 zipfile 不认软链，会把 `.app` 里
        # Frameworks/Resources 之间的软链**展开成实体文件**——zip 体积翻倍，
        # 解压出来的 .app 签名也对不上（Gatekeeper 直接判损坏）。
        subprocess.run(
            ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(folder), str(archive)],
            check=True,
        )
        return archive
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for item in sorted(folder.rglob("*")):
            if item.is_file():
                bundle.write(item, item.relative_to(folder.parent))
    return archive


def payload_size(folder: Path) -> int:
    """算真实占盘（软链按软链算，别跟着软链把同一个文件重复计一遍）。"""

    total = 0
    for item in folder.rglob("*"):
        try:
            total += item.lstat().st_size
        except OSError:
            continue
    return total


def install_note() -> str:
    """DMG 里的安装说明：`packaging/install-note.txt`，`{version}` 会被替换。"""

    template = (ROOT / "packaging" / "install-note.txt").read_text(encoding="utf-8")
    return template.replace("{version}", __version__)


def make_dmg(folder: Path) -> Path | None:
    """把整个包做成 DMG（macOS 用户习惯的那个"安装包"）。

    卷里只有**一个可拖的 `.app`**，加一个「应用程序」软链和一份安装说明：
    库的 CLI 与动态库都塞在 app 内部（`Contents/Frameworks/reader/`），
    许可全文也在 app 里（`Contents/Resources/`），所以用户拖一个图标就装完了。
    """

    stage = BUILD / "dmg"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    # symlinks=True 必须带：.app 里 Frameworks ↔ Resources 之间全是软链，
    # 拷成实体文件签名就废了（和 zip 必须用 ditto 是同一个道理）。
    app = next(iter(folder.glob("*.app")), None)
    if app is None:
        print("没找到 .app，跳过 DMG")
        return None
    shutil.copytree(app, stage / app.name, symlinks=True)
    (stage / "Applications").symlink_to("/Applications")
    (stage / "安装说明.txt").write_text(install_note(), encoding="utf-8")

    image = folder.parent / (folder.name + ".dmg")
    if image.exists():
        image.unlink()
    done = subprocess.run(
        ["hdiutil", "create", "-volname", "LittleTiles Reader %s" % __version__,
         "-srcfolder", str(stage), "-ov", "-format", "UDZO", "-fs", "HFS+", str(image)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0:
        print("DMG 制作失败（zip 仍然可用）：%s" % (done.stderr or done.stdout or "").strip())
        return None
    return image


def write_bundle_version(app: Path) -> None:
    """把 Info.plist 里的版本号写成真实版本（PyInstaller 默认 0.0.0）。"""

    plist = app / "Contents" / "Info.plist"
    if not plist.is_file():
        return
    for key in ("CFBundleShortVersionString", "CFBundleVersion"):
        subprocess.run(["plutil", "-replace", key, "-string", __version__, str(plist)], check=False)
    print("Info.plist 版本号已写成 %s" % __version__)


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
    parser.add_argument("--no-dmg", action="store_true",
                        help="macOS 上不出 DMG（默认出；DMG 才是用户习惯的那个安装包）")
    parser.add_argument("--no-msi", action="store_true",
                        help="Windows 上不出 MSI（默认出；双击就装的那个安装包）")
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
    # PATH 必须清过：本机 PATH 里有代理/别的运行时带的同名 DLL（实测是 ICU 78），
    # PyInstaller 顺着 PATH 分析依赖会收错版本，包能构建、双击起不来
    code = subprocess.call(command, env=clean_build_env())
    if code != 0:
        return code

    # 挑一份发：macOS 上用 .app（自包含），其他平台用 onedir
    app_bundle = SCRATCH / ("%s.app" % name)
    built = app_bundle if (sys.platform == "darwin" and app_bundle.is_dir()) else SCRATCH / name
    if not built.exists():
        print("构建结束但没找到产物：%s" % built)
        return 1
    target = DIST / ("%s-%s-%s" % (name, __version__, platform_tag()))
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    shutil.move(str(built), str(target / built.name))
    if built is app_bundle:
        print("已放入应用：%s（裸 onedir 是同一份内容的中间产物，不随包发）" % app_bundle.name)
        write_bundle_version(target / app_bundle.name)

    packed_app = (target / app_bundle.name) if built is app_bundle else None
    if args.with_reader:
        copy_reader(target, args.reader, packed_app)
    copy_docs(target, args.with_reader, packed_app)
    if packed_app is not None:
        # 用户从 DMG 里只看到这一个图标，说明就放它旁边（卷根）
        (target / "安装说明.txt").write_text(install_note(), encoding="utf-8")
    if sys.platform == "darwin":
        # 未签名发布：至少给出 ad-hoc 签名，否则 arm64 上会被 Gatekeeper 直接杀掉
        sign_macos(target)
        print("已做 ad-hoc 签名（安装说明见 README-unsigned.md）")
    if sys.platform.startswith("win"):
        # 见 MSVC_RUNTIME_NAMES 的注释：两份不同版本的 MSVC 运行时会让人以为
        # "构建成功但双击起不来"，必须在这里统一掉（zip 与 MSI 都用这份目录）
        unified = unify_msvc_runtime(target)
        if unified:
            print("已统一 MSVC 运行时（%s），避免包里两份不同版本导致 Qt 加载失败"
                  % "、".join(unified))
        aligned = align_runtime_dependencies(target)
        if aligned:
            print("已把运行时依赖对齐到构建环境：%s" % "、".join(sorted(set(aligned))))
        # 最后一道：在干净环境里真跑一次冻包自检。不过就直接判构建失败——
        # "构建成功但双击报 DLL load failed" 这种事不能靠运气发现（真机上就是这么撞的）。
        ok, note = verify_frozen_app(target)
        print("%s 冻包自检：%s" % ("[OK]" if ok else "[FAIL]", note))
        if not ok:
            print("构建产物不可用，已中止（不出 zip / MSI）")
            return 1

    total = payload_size(target)
    print("产物目录：%s（%s）" % (target, human(total)))
    if sys.platform == "darwin" and not args.no_dmg:
        image = make_dmg(target)
        if image is not None and image.is_file():
            print("安装包（DMG）：%s（%s）" % (image, human(image.stat().st_size)))
            print("SHA-256：%s" % sha256(image))
    if sys.platform.startswith("win") and not args.no_msi:
        # MSI 只能在这台机器上生成（要 Windows + msilib），所以放在这里而不是别处
        from build_msi import make_msi, sha256 as msi_sha256, verify_msi  # noqa: PLC0415

        installer = target.parent / (target.name + ".msi")
        make_msi(
            target, installer, version=__version__,
            icon=ROOT / "packaging" / "app.ico",
        )
        print("SHA-256：%s" % msi_sha256(installer))
        # 出包后立刻解包核对一遍（不需要管理员权限，也不会写注册表）
        with tempfile.TemporaryDirectory(prefix="ltr-msi-") as tmp:
            ok, note = verify_msi(installer, target, Path(tmp) / "extract")
        print("%s MSI 解包自检：%s" % ("[OK]" if ok else "[FAIL]", note))
    if not args.no_zip:
        archive = zip_dir(target)
        print("压缩包：%s（%s）" % (archive, human(archive.stat().st_size)))
        print("SHA-256：%s" % sha256(archive))
    print("发布：macOS 传 DMG（用户双击挂载那个），Windows 传 MSI（双击就装），zip 作为通用/备用；")
    print("      把下载直链 + SHA-256 填进后台「LT 读取器 → 客户端下载」即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
