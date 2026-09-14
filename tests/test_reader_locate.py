"""CLI 定位：打包版里"库就在应用旁边"这条必须人人走对。

真机踩到的坑：项目界面自己写了一套
`ltgen.paths.reader_executable()`，而那个函数是拿 `__file__` 反推仓库根的。
冻结后 `ltgen` 在 `.app` 里，于是拼出
`…/LittleTilesReader.app/Contents/minecraft-littletiles-reader/cmake-build-debug/LittleTilesReader`
这种不存在的路径，项目导出直接卡住。本用例把"打包布局"造出来，钉住这个行为。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import reader  # noqa: E402
from app.config import AppConfig  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    print("== CLI 定位 ==")
    QApplication.instance() or QApplication([])

    from app.ui.project_window import _cli_path

    with tempfile.TemporaryDirectory(prefix="lt-frozen-") as tmp:
        # 一律比较 resolve() 之后的结果：macOS 上 /var 是指向 /private/var 的软链，
        # 定位逻辑内部会 resolve，不 resolve 就会"看着一样、比不相等"。
        bundle = Path(tmp).resolve()
        # 造一个"打包后的样子"：LittleTilesReader.app 旁边就是库的 CLI
        executable = bundle / "LittleTilesReader"
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
        app_exe = bundle / "LittleTilesReader.app" / "Contents" / "MacOS" / "LittleTilesReader"
        app_exe.parent.mkdir(parents=True)
        app_exe.write_text("", encoding="utf-8")
        unpacked = bundle / "LittleTilesReader.app" / "Contents" / "Frameworks"
        unpacked.mkdir(parents=True)

        saved = (getattr(sys, "frozen", None), sys.executable, getattr(sys, "_MEIPASS", None))
        sys.frozen = True          # type: ignore[attr-defined]
        sys.executable = str(app_exe)
        sys._MEIPASS = str(unpacked)  # type: ignore[attr-defined]
        try:
            found = reader.bundled_reader()
            check("应用旁边能找到 CLI", found is not None and found.resolve() == executable,
                  str(found))

            resolved = _cli_path(AppConfig())
            check("项目界面用的是它", resolved.resolve() == executable, str(resolved))
            check("项目界面不会拼进 .app 里",
                  unpacked not in resolved.parents and app_exe.parent != resolved.parent,
                  str(resolved))

            described = reader.describe()
            check("describe 也指向应用自带", "应用自带" in described, described)
        finally:
            if saved[0] is None:
                del sys.frozen      # type: ignore[attr-defined]
            else:
                sys.frozen = saved[0]  # type: ignore[attr-defined]
            sys.executable = saved[1]
            if saved[2] is None:
                del sys._MEIPASS    # type: ignore[attr-defined]
            else:
                sys._MEIPASS = saved[2]  # type: ignore[attr-defined]

    # 配置里手填了路径就以配置为准（高级用户想指别的构建）
    with tempfile.TemporaryDirectory(prefix="lt-config-") as tmp:
        custom = Path(tmp) / "LittleTilesReader"
        custom.write_text("", encoding="utf-8")
        config = AppConfig()
        config.library_cli = str(custom)
        check("配置优先", _cli_path(config).resolve() == custom.resolve(),
              str(_cli_path(config)))

    # Windows 的包结构：<包>/LittleTilesReader/LittleTilesReader.exe 是**应用自己**，
    # 库的 CLI 在上一层 <包>/LittleTilesReader.exe。这里必须挑后者，
    # 否则每次导出都会新开一个客户端窗口。
    with tempfile.TemporaryDirectory(prefix="lt-win-") as tmp:
        bundle = Path(tmp).resolve()
        cli = bundle / "LittleTilesReader.exe"          # 库的 CLI（上一层）
        cli.write_text("", encoding="utf-8")
        app_dir = bundle / "LittleTilesReader"
        app_dir.mkdir()
        app_exe = app_dir / "LittleTilesReader.exe"     # 应用自己
        app_exe.write_text("", encoding="utf-8")
        unpacked = app_dir / "_internal"
        unpacked.mkdir()

        saved = (sys.platform, getattr(sys, "frozen", None), sys.executable,
                 getattr(sys, "_MEIPASS", None))
        sys.platform = "win32"
        sys.frozen = True          # type: ignore[attr-defined]
        sys.executable = str(app_exe)
        sys._MEIPASS = str(unpacked)  # type: ignore[attr-defined]
        try:
            found = reader.bundled_reader()
            check("Windows：不会把应用自己当 CLI",
                  found is not None and found.resolve() == cli, str(found))
            check("Windows：项目界面同样拿到 CLI",
                  _cli_path(AppConfig()).resolve() == cli, str(_cli_path(AppConfig())))
        finally:
            sys.platform = saved[0]
            if saved[1] is None:
                del sys.frozen      # type: ignore[attr-defined]
            else:
                sys.frozen = saved[1]  # type: ignore[attr-defined]
            sys.executable = saved[2]
            if saved[3] is None:
                del sys._MEIPASS    # type: ignore[attr-defined]
            else:
                sys._MEIPASS = saved[3]  # type: ignore[attr-defined]

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
