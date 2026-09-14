"""导出完成后的"是否打开输出目录"提示。

不动真的文件管理器：把 `open_directory` 和 `QMessageBox` 都换成替身，
只验证**判断与参数**——传对目录、勾了"不再询问"会写进配置、关掉后不再弹。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# 数据目录指到临时目录：自检绝不能碰用户真实的 config/ 与 logs/
# （`data_dir()` 每次调用重新解析 LTR_HOME，所以在这里设就够了）
_LTR_HOME = tempfile.mkdtemp(prefix="lt-home-")
os.environ["LTR_HOME"] = _LTR_HOME

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.ui import main_window as mw  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name, "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


class FakeBox:
    """替身 QMessageBox：按预设按钮返回，并记录收到的文本。"""

    Icon = QMessageBox.Icon
    StandardButton = QMessageBox.StandardButton

    result = QMessageBox.StandardButton.Open
    tick_never = False
    last_text = ""
    shown = 0

    def __init__(self, _parent=None) -> None:
        self._checkbox = None

    def setWindowTitle(self, _text): pass
    def setIcon(self, _icon): pass
    def setText(self, _text): pass

    def setInformativeText(self, text):
        FakeBox.last_text = text

    def setStandardButtons(self, _buttons): pass
    def setDefaultButton(self, _button): pass

    def setCheckBox(self, checkbox):
        self._checkbox = checkbox

    def exec(self):
        FakeBox.shown += 1
        if self._checkbox is not None:
            self._checkbox.setChecked(FakeBox.tick_never)
        return FakeBox.result


def main() -> int:
    print("== 输出目录提示 ==")
    QApplication([])
    mw.QMessageBox = FakeBox  # type: ignore[assignment]

    opened: list[Path] = []
    mw.open_directory = lambda path: opened.append(Path(path)) or True  # type: ignore[assignment]

    with tempfile.TemporaryDirectory(prefix="lt-prompt-") as tmp:
        out_dir = Path(tmp) / "2026-09-14_0031_house"
        out_dir.mkdir()

        config = AppConfig()
        config.save = lambda path=None: Path(tmp) / "app.json"  # 别写进仓库
        window = mw.MainWindow(config)

        # 1) 默认：弹一次，选"打开"→ 打开该目录
        FakeBox.result = QMessageBox.StandardButton.Open
        FakeBox.tick_never = False
        FakeBox.shown = 0
        window._offer_open_output(out_dir)
        check("弹了一次提示", FakeBox.shown == 1)
        check("提示里带上了输出目录", str(out_dir) in FakeBox.last_text)
        check("选了打开就打开该目录", opened == [out_dir])

        # 2) 选"关闭"：不打开，但下次还会问
        opened.clear()
        FakeBox.result = QMessageBox.StandardButton.Close
        window._offer_open_output(out_dir)
        check("选了关闭就不打开", opened == [])
        check("没勾不再询问，配置不变", config.ask_open_output is True)

        # 3) 勾"以后不再询问"：写进配置
        FakeBox.tick_never = True
        window._offer_open_output(out_dir)
        check("勾了不再询问就记住", config.ask_open_output is False)

        # 4) 关掉之后不再弹
        FakeBox.shown = 0
        FakeBox.tick_never = False
        window._offer_open_output(out_dir)
        check("关掉后不再弹", FakeBox.shown == 0)

        # 5) 目录不存在时也不弹（比如用户挪走了）
        config.ask_open_output = True
        FakeBox.shown = 0
        window._offer_open_output(out_dir / "gone")
        check("目录不存在就不问", FakeBox.shown == 0)

        # 6) 产物路径优先：有 obj 就用它所在目录
        window._last_output_dir = Path(tmp) / "另一个目录"
        resolved = window._output_dir_of({"obj": str(out_dir / "house.obj")})
        check("优先用产物所在目录", resolved == out_dir, str(resolved))
        check(
            "没有产物时退回 job 目录",
            window._output_dir_of({}) == window._last_output_dir,
        )

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
