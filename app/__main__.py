"""入口：`python -m app`。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import __version__
from . import i18n, licenses
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

    # 首次启动（或协议集合变了）先把许可协议看完并同意——不同意就直接退出
    if not licenses.accepted(app_config):
        from .ui.license_dialog import LicenseDialog

        dialog = LicenseDialog()
        if dialog.exec() != LicenseDialog.DialogCode.Accepted:
            logger().info("用户未同意许可协议，退出")
            return 0
        licenses.accept(app_config)
        logger().info(
            "已同意许可协议 v%d（%s）",
            licenses.LICENSE_SET_VERSION, app_config.licenses_accepted_at,
        )

    window = MainWindow(app_config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
