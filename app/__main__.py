"""入口：`python -m app`。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .config import AppConfig
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("LittleTiles Reader")
    window = MainWindow(AppConfig.load())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
