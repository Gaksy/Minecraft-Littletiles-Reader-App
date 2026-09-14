"""入口：`python -m app`。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import __version__
from . import i18n
from .applog import logger, start_session
from .config import AppConfig, data_dir
from .ui import design
from .ui.main_window import MainWindow


def main() -> int:
    app_config = AppConfig.load()
    path = start_session(data_dir(), __version__)
    app = QApplication(sys.argv)
    app.setApplicationName("LittleTiles Reader")
    # 风格与网站统一：像素字体 + 直角 + 石头底/草绿/亮黄（app/ui/design/）
    design.install(app, app_config.ui_theme)
    # 界面语言：配置里没写就跟随系统（认不出来时用简体中文）
    i18n.set_language(app_config.language or i18n.system_language())
    logger().info("会话日志: %s", path)
    logger().info("界面语言: %s", i18n.current())
    window = MainWindow(app_config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
