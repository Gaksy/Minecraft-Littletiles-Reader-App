"""选题输入来源：结构文件，还是粘贴一段文本（两个界面共用）。

项目模式早就支持粘贴，快速导出只有"选文件"——同一个动作两种行为，
用户得先记住"想要粘贴得进项目"。这里抽成一处，两边的体验一致。

粘贴的文本会落成一个真实文件再交给库：job 契约只认路径，
而且留一份文件才好追溯（放在应用的 `tmp/` 下，随时可删）。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


class PasteSnbtDialog(QDialog):
    """粘贴一段 SNBT 文本（框里给个最小示例，省得用户不知道贴什么）。"""

    EXAMPLE = "{tiles:[{boxes:[[I;0,0,0,16,16,16]],tile:{block:\"minecraft:stone\"}}],grid:16}"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("粘贴 SNBT")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("把结构文本粘进来（游戏里复制或从文件里复制的都行）："))
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText(self.EXAMPLE)
        self.text.setMinimumSize(560, 300)
        layout.addWidget(self.text)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def snbt(self) -> str:
        return self.text.toPlainText()


def choose_snbt_source(parent: QWidget | None) -> tuple[str, str] | None:
    """问一次"结构从哪来"，返回 `("file", 路径)` / `("paste", 文本)`；取消返回 None。"""

    box = QMessageBox(parent)
    box.setWindowTitle("导出 SNBT")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText("结构从哪里来？")
    box.setInformativeText("选一个 .txt / .struct 结构文件，或者直接把文本粘进来。")
    from_file = box.addButton("选择文件", QMessageBox.ButtonRole.AcceptRole)
    from_paste = box.addButton("粘贴文本", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    clicked = box.clickedButton()

    if clicked is from_paste:
        dialog = PasteSnbtDialog(parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        text = dialog.snbt()
        return ("paste", text) if text.strip() else None
    if clicked is not from_file:
        return None
    chosen, _ = QFileDialog.getOpenFileName(
        parent, "选择 LittleTiles 结构文件", "",
        "结构文件 (*.txt *.struct);;所有文件 (*)",
    )
    return ("file", chosen) if chosen else None


def save_pasted_snbt(text: str, tmp_dir: Path, stem: str | None = None) -> Path:
    """把粘贴的文本落成一个文件；`tmp_dir` 一般是应用的 `tmp/`。"""

    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target = tmp_dir / ("%s_paste.txt" % (stem or stamp))
    target.write_text(text, encoding="utf-8")
    return target
