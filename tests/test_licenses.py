"""许可全文的查找：打包后**许可在包根、字体许可在解包目录**，两边都要找得到。

补这条是因为真机撞到过：装完之后"许可全文"的下拉框里只剩「字体」那一条 ——
原来只按 `bundle_root()`（= PyInstaller 的 `_internal`）找，而 `LICENSE` /
`licenses/*.txt` 是打包脚本放在**包根**的，只有字体那份（跟着 `--add-data` 进去）在
解包目录里。模拟一遍已安装的布局就能复现。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import licenses  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name, "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    print("== 许可全文查找（模拟打包版） ==")
    saved = {name: getattr(sys, name, None) for name in ("_MEIPASS", "frozen", "executable")}
    try:
        with tempfile.TemporaryDirectory(prefix="lt-lic-") as tmp:
            # 模拟 dist 里的布局
            package = Path(tmp) / "LittleTilesReader-0.1.0-windows-x64"
            internal = package / "LittleTilesReader" / "_internal"
            (internal / "app" / "resources" / "fonts").mkdir(parents=True)
            (package / "licenses").mkdir(parents=True)
            (package / "LICENSE").write_text("MIT 全文占位", encoding="utf-8")
            (package / "THIRD-PARTY.md").write_text("第三方总览占位", encoding="utf-8")
            (package / "licenses" / "GPL-3.0.txt").write_text("GPL 全文占位", encoding="utf-8")
            (internal / "app" / "resources" / "fonts" / "OFL.txt").write_text(
                "OFL 全文占位", encoding="utf-8"
            )
            (package / "LittleTilesReader" / "LittleTilesReader.exe").write_text("", encoding="utf-8")

            # 假装自己就是这个"已安装的冻结版"
            sys._MEIPASS = str(internal)
            sys.frozen = True
            sys.executable = str(package / "LittleTilesReader" / "LittleTilesReader.exe")

            titles = [title for title, _ in licenses.texts()]
            # 标题里带中点之类的符号，按关键字匹配更稳
            check("包根的 MIT 找得到",
                  any(title.startswith("LittleTiles Reader") for title in titles), str(titles))
            check("包根的 licenses/ 找得到",
                  any("GNU GPL" in title for title in titles))
            check("第三方总览找得到", any("第三方" in title for title in titles))
            check("字体许可（在解包目录里）也找得到",
                  any("Open Font License" in title for title in titles))
            check("该有的都在（没有的跳过）", len(titles) == 4, "%d 份：%s" % (len(titles), titles))
    finally:
        for name, value in saved.items():
            if value is None:
                try:
                    delattr(sys, name)
                except AttributeError:
                    pass
            else:
                setattr(sys, name, value)

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
