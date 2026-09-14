"""把一件慢活放到后台线程跑，主线程用嵌套事件循环等它。

为什么要有这个：组合素材、备份存档、收贴图、打包 zip 都是几秒到几十秒的活；
放主线程会让界面整段冻住，看起来像卡死（M1 踩过）。

主界面和项目界面都要用，所以单独放在这儿，谁都能 import。
"""

from __future__ import annotations

from PySide6.QtCore import QEventLoop, QThread, Signal
from PySide6.QtWidgets import QProgressDialog
from PySide6.QtCore import Qt


class Worker(QThread):
    """把 work() 的结果（或异常）带回主线程。"""

    finished_with = Signal(object)

    def __init__(self, work, parent=None) -> None:
        super().__init__(parent)
        self._work = work

    def run(self) -> None:
        try:
            self.finished_with.emit(self._work())
        except Exception as error:      # 交给主线程决定怎么说
            self.finished_with.emit(error)


def run_in_background(parent, title: str, text: str, work) -> object:
    """跑 work()，其间显示不确定进度框；返回结果，异常原样抛回调用方。"""

    dialog = QProgressDialog(text, "", 0, 0, parent)
    dialog.setWindowTitle(title)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setCancelButton(None)
    dialog.setMinimumDuration(0)
    dialog.show()

    worker = Worker(work, parent)
    result: dict = {}
    loop = QEventLoop()

    def finished(payload) -> None:
        result["payload"] = payload
        loop.quit()

    worker.finished_with.connect(finished)
    worker.start()
    loop.exec()
    worker.wait()
    dialog.close()
    payload = result.get("payload")
    if isinstance(payload, Exception):
        raise payload
    return payload
