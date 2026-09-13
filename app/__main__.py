"""入口：`python -m app`。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import __version__
from .applog import logger, start_session
from .config import APP_DIR, AppConfig
from .ui import design
from .ui.main_window import MainWindow


def main() -> int:
    app_config = AppConfig.load()
    path = start_session(APP_DIR, __version__)
    app = QApplication(sys.argv)
    app.setApplicationName("LittleTiles Reader")
    # 风格与网站统一：像素字体 + 直角 + 石头底/草绿/亮黄（app/ui/design/）
    design.install(app, app_config.ui_theme)
    logger().info("会话日志: %s", path)
    window = MainWindow(app_config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
