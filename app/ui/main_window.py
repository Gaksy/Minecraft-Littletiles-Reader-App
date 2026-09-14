"""启动界面：项目列表 + 两个大入口（快速导出）+ 导出进度与日志。

两种用法在这一页并存，各自的取舍也写在界面上：

* **快速导出**（两个大按钮）：不绑定项目、不留记录，产物落在默认输出目录；
* **项目模式**（下面的卡片）：素材副本、历史记录、贴图库、区块查询都在项目里，
  点一张卡片就开一个新的项目窗口（`project_window.py`）。

进度、取消、打开输出目录、日志用同一个 `ExportPanel`——主界面与项目界面只此一份。
"""

from __future__ import annotations

from datetime import datetime
import subprocess
from pathlib import Path

from PySide6.QtCore import QEvent, QEventLoop, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QActionGroup, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ltgen import paths
from ltgen.lint import lint_package

from .. import appdata, i18n
from ..applog import logger
from ..config import APP_DIR, AppConfig
from ..job import build_snbt_job, default_options
from ..project import Project
from ..sources import ARCHIVE_SUFFIXES, resolve_source
from ..compose import ComposeError, compose
from ..library import Library
from ..library_probe import probe as probe_library
from ..storage import human_size
from ..vanilla import build_package_from_resolved, detect_kind
from .export_panel import ExportPanel
from .export_dialog import ExportRegionDialog
from . import design
from . import popup
from .material_dialog import MaterialChoiceDialog
from .material_manager import MaterialManagerDialog
from .illustration_dialog import IllustrationDialog
from .project_list import ProjectListWidget
from .project_window import ProjectWindow
from .snbt_source import choose_snbt_source, save_pasted_snbt


def open_directory(path: Path) -> bool:
    """用系统默认的文件管理器打开目录（Windows 资源管理器 / macOS 访达）。

    独立成函数，一是跨平台只在这一处，二是测试时可以替换掉，避免真弹窗口。
    """
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class _PackageBuilder(QThread):
    """在后台线程里解压并生成素材包。

    这套活要几十秒（解 jar、解析 blockstates/models、挑贴图）。放在主线程里做，
    界面会整段冻住、看着像死了——所以挪到线程里，主线程只负责转圈。
    """

    finished_with = Signal(object)   # PackageBuild，或捕到的 Exception

    def __init__(self, source: Path, work: Path, out: Path, parent=None) -> None:
        super().__init__(parent)
        self._source = source
        self._work = work
        self._out = out

    def run(self) -> None:
        """解压 → 认类型 → （是客户端 jar 就）生成素材包。

        整段都在线程里：解压十几秒、生成二十几秒，放主线程界面会冻住。
        """
        try:
            resolved = resolve_source(self._source, self._work)
            kind = detect_kind(resolved.path)
            self.progress_note = "识别为 %s" % kind
            if kind != "vanilla":
                self.finished_with.emit({"kind": kind, "note": resolved.note})
                return
            build = build_package_from_resolved(
                resolved.path, self._out, resolved.note or "目录"
            )
            self.finished_with.emit({"kind": kind, "note": resolved.note, "build": build})
        except Exception as error:      # 解压失败、脚本报错…都带回主线程处理
            self.finished_with.emit(error)


class _Composer(QThread):
    """后台把素材按启用顺序组合起来（首次 4~5 秒，放主线程会冻住界面）。"""

    finished_with = Signal(object)   # Composed，或捕到的 Exception

    def __init__(self, app_dir: Path, library, parent=None) -> None:
        super().__init__(parent)
        self._app_dir = app_dir
        self._library = library

    def run(self) -> None:
        try:
            self.finished_with.emit(compose(self._app_dir, self._library))
        except Exception as error:
            self.finished_with.emit(error)


def busy_dialog(title: str, text: str, parent) -> QProgressDialog:
    """不确定时长的进度框：一直在动，但不说"还剩多少"，因为确实不知道。"""
    dialog = QProgressDialog(text, "", 0, 0, parent)
    dialog.setWindowTitle(title)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setCancelButton(None)        # 中途取消会留下半个素材包，先不给取消
    dialog.setMinimumDuration(0)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    dialog.show()
    return dialog


class MainWindow(QMainWindow):
    def _git_revision(self) -> str:
        """当前跑的是哪次提交——"我到底测的是哪版"这个问题，一行就答了。"""
        try:
            done = subprocess.run(
                ["git", "-C", str(APP_DIR), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            revision = (done.stdout or "").strip() or "未知"
            status = subprocess.run(
                ["git", "-C", str(APP_DIR), "status", "--porcelain"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if (status.stdout or "").strip():
                revision += "（工作区有未提交改动）"
            return revision
        except Exception:
            return "未知"

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.setWindowTitle("LittleTiles Reader")
        self.resize(980, 760)
        self.config = config
        # 启动就问一次库版本（不用先导出一次）；导出时 start 事件会再报一次同样的值
        self._library_version = probe_library(self._cli_path())
        self._faded_in = False
        # 打开的项目窗口留一份引用：不然会被 GC 掉，看起来就是"一闪而过"
        self._project_windows: list[ProjectWindow] = []
        # 进度、日志、取消、打开输出目录都在面板里：项目界面用的是同一块，
        # "写文件阶段切不确定进度"这类修正只需要改一处。
        # open_directory / QMessageBox 按**本模块的名字**注入，测试替换本模块的
        # 同名对象就能拦住真实弹窗。
        self.panel = ExportPanel(
            config,
            APP_DIR,
            self,
            open_directory=open_directory,
            message_box=QMessageBox,
        )
        self.panel.library_version.connect(self._on_library_version)
        # 兼容旧调用点（测试与部分代码直接用 window.runner / window.progress）
        self.runner = self.panel.runner
        self.bar = self.panel.bar
        self.cancel = self.panel.cancel
        self.open_output = self.panel.open_output
        self.log = self.panel.log_view
        self._build_ui()
        self._refresh_status()
        self.panel.log_view.setMaximumHeight(120)   # 日志别把上面的内容挤没了
        # 启动时把"这次是在什么环境下跑的"记进会话日志，排错第一眼就看这些
        cli = self._cli_path()
        logger().info("库 CLI: %s（存在=%s）", cli, Path(cli).is_file())
        logger().info("默认素材包: %s", self.config.default_assets or "（未设置）")
        logger().info("默认输出目录: %s", self.config.resolved_output_dir())
        # 启动后查一次更新：每天最多一次，失败静默（离线也要能正常用）。
        # 放到事件循环里跑，别让网络请求卡住窗口显示。
        QTimer.singleShot(0, self._maybe_check_update_on_start)

    # ---- 兼容层 ----------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        """第一次显示时淡入一次（避免整屏"啪"地出现）。"""

        super().showEvent(event)
        if not self._faded_in:
            self._faded_in = True
            design.motion.fade_in(self.centralWidget())

    @property
    def progress(self):
        return self.panel.progress

    @property
    def _last_output_dir(self) -> Path | None:
        return self.panel.last_output_dir

    @_last_output_dir.setter
    def _last_output_dir(self, value: Path | None) -> None:
        self.panel.last_output_dir = value

    # ---- 界面 ------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(
            design.METRICS.gap_lg,
            design.METRICS.gap_lg,
            design.METRICS.gap_lg,
            design.METRICS.gap_lg,
        )
        layout.setSpacing(design.METRICS.gap_md)

        layout.addWidget(design.title("快速导出"))

        buttons = QHBoxLayout()
        buttons.setSpacing(design.METRICS.gap_md)
        # 两个入口同级：都用大号主按钮（网站的大按钮档 258×48）
        self.btn_snbt = design.primary_button("导出 SNBT\n（结构文件 / 粘贴文本）")
        self.btn_region = design.primary_button("导出存档\n（选区块导出 OBJ）")
        for button in (self.btn_snbt, self.btn_region):
            button.setProperty("size", "large")
            button.setMinimumHeight(design.METRICS.button_large_height * 2)
            buttons.addWidget(button, 1)
        layout.addLayout(buttons)
        self.btn_snbt.clicked.connect(self._export_snbt)
        self.btn_region.clicked.connect(self._export_region)

        self.projects = ProjectListWidget(self.config, self)
        self.projects.opened.connect(self._open_project)
        layout.addWidget(self.projects, 1)

        # 进度、取消、打开输出目录、日志 = 一块面板（主界面与项目界面共用）
        layout.addWidget(self.panel, 0)

        self.setCentralWidget(central)
        self.status = self.statusBar()
        # 菜单栏最后建：它引用了日志面板这些控件，得等它们都存在
        self._build_menu()

    def _refresh_status(self) -> None:
        cli = self._cli_path()
        # 素材包：不可用的要当场标出来。否则一个失效路径（比如误选成了导出目录）
        # 会被当成"已配置"，用户看状态栏以为没问题。
        configured = self.config.default_assets
        if not configured:
            assets = i18n.tr("（未设置）")
        elif lint_package(Path(configured)).ok:
            assets = configured
        else:
            assets = i18n.tr("（不可用，导出时会要求重新选择）%s") % configured
        version = ("    库 %s" % self._library_version) if self._library_version else ""
        self.status.showMessage(
            i18n.tr("素材包: %s    模型输出目录: %s%s    CLI: %s")
            % (assets, self.config.resolved_output_dir(), version, cli)
        )

    # ---- 依赖解析 --------------------------------------------------------

    def _cli_path(self) -> Path:
        if self.config.library_cli:
            return Path(self.config.library_cli)
        return paths.reader_executable()

    def _choose_assets(self) -> str | None:
        """决定这次用哪套素材：**默认沿用上次的选择**，走缓存。

        返回素材包路径；`""` = 不用材质（白模）；`None` = 用户取消。

        用户面对的是"素材列表"而不是"选一个目录/文件"：导入、启用、排序都在材质
        管理里做，这里只把右列的顺序变成实际可用的素材包。

        非项目模式下不该每次都逼用户过一遍列表——选择记在库里，这次直接用；
        要改就点主界面的「材质管理」。组合按顺序指纹缓存，没变就是毫秒级命中。
        """
        library = Library.load(APP_DIR)
        kept = library.selected()
        # 每次导出都问一句，三选一：继续用上次 / 去材质管理 / 不用材质（白模）。
        # 有"上次"才出现第一个按钮；一次都没配过时只剩后两条路。
        dialog = MaterialChoiceDialog(
            " → ".join(s.name for s in kept) if kept else "", self
        )
        if dialog.exec() != MaterialChoiceDialog.DialogCode.Accepted:
            return None
        if dialog.choice == "none":
            self._log("本次不使用材质：导出白模（几何完整，但没有贴图/MTL）。")
            return ""
        if dialog.choice == "manage":
            manager = MaterialManagerDialog(APP_DIR, self)
            if manager.exec() != MaterialManagerDialog.DialogCode.Accepted:
                return None
            library = manager.library
            if not library.selected():
                self._log("未启用任何素材：本次导出白模。")
                return ""
        else:
            self._log("继续使用上次的材质：%s" % " → ".join(s.name for s in kept))
        return self._compose_assets(library)

    def _compose_assets(self, library) -> str | None:
        """按启用顺序组合并返回素材包路径；失败时提示并返回 None。"""
        # 组合在后台线程里跑：首次或素材变动要 4~5 秒，放主线程界面会冻住
        # （进度框也不转，看着像卡死）。用嵌套事件循环等它，界面照常重绘。
        progress = busy_dialog("材质组合", "正在按启用顺序组合素材…", self)
        composer = _Composer(APP_DIR, library, self)
        result: dict = {}
        loop = QEventLoop()

        def finished(payload) -> None:
            result["payload"] = payload
            loop.quit()

        composer.finished_with.connect(finished)
        composer.start()
        loop.exec()
        composer.wait()
        progress.close()

        payload = result.get("payload")
        if isinstance(payload, ComposeError):
            popup.warning(self, "组合不了", str(payload))
            return None
        if isinstance(payload, Exception):      # 解压/脚本报错…
            logger().exception("组合素材失败")
            popup.warning(self, "组合失败", str(payload))
            return None
        composed = payload
        self._log(
            "  素材包: %s（%s%s）"
            % (
                composed.package_dir.name,
                composed.note,
                "，复用上次结果" if composed.reused else "",
            )
        )
        return str(composed.package_dir)

    def _build_menu(self) -> None:
        """管理类入口放菜单栏：主界面只留两个导出按钮，不跟它们抢位置。

        菜单里只放"不常按、按了有明显后果"的东西；导出流程里要用的
        （进度、取消、打开输出目录）留在主界面上。
        """
        bar = self.menuBar()

        materials = bar.addMenu("素材(&M)")
        self.action_materials = materials.addAction("材质管理", self._open_materials)
        materials.addAction("区块选择说明", self._show_help)

        output = bar.addMenu("输出(&O)")
        output.addAction("设置默认输出目录", self._choose_output_dir)
        output.addAction("恢复默认输出目录", self._reset_output_dir)
        output.addAction("打开输出目录", self._open_last_output)
        output.addAction("清空日志窗口", self.log.clear)

        view = bar.addMenu("视图(&V)")
        self.action_theme = view.addAction(self._theme_action_text(), self._toggle_theme)
        # 语言：改完写进配置，重启后生效（Qt 的文案是死值，重启最不容易出半截界面）
        language = view.addMenu("语言")
        group = QActionGroup(self)
        group.setExclusive(True)
        for code, name in i18n.LANGUAGES:
            action = language.addAction(name)
            action.setCheckable(True)
            action.setChecked(code == i18n.current())
            action.triggered.connect(lambda _checked=False, chosen=code: self._set_language(chosen))
            group.addAction(action)
        self.language_group = group
        language.addSeparator()
        follow = language.addAction("跟随系统")
        follow.setCheckable(True)
        follow.setChecked(not self.config.language)
        follow.triggered.connect(lambda _checked=False: self._set_language(""))

        # 应用级操作放最后：都是"按了有明显后果"的东西
        app_menu = bar.addMenu("应用(&A)")
        app_menu.addAction("清空所有数据", self._reset_app_data)

        help_menu = bar.addMenu("帮助(&H)")
        help_menu.addAction("检查更新", self._check_update)
        help_menu.addAction("反馈问题", self._report_problem)
        help_menu.addSeparator()
        help_menu.addAction("关于", self._show_about)
        i18n.translate(self)

    def _set_language(self, code: str) -> None:
        """切换界面语言：写进配置，提示重启。"""

        chosen = code or i18n.system_language()
        self.config.language = code
        self._save_config("语言")
        logger().info("界面语言改为 %s（重启后生效）", code or "跟随系统")
        popup.info(
            self,
            "语言",
            "界面语言已切换为 %s，重启应用后生效。" % i18n.display_name(chosen),
        )

    def _theme_action_text(self) -> str:
        return "切换到浅色主题" if design.manager().is_dark else "切换到深色主题"

    # ---- 默认输出目录 ----------------------------------------------------

    def _choose_output_dir(self) -> None:
        """选快速导出的默认落点（项目模式仍旧写进项目自己的目录）。

        以前这个值只能改配置文件（`AppConfig.output_dir` 有字段、没有界面），
        状态栏里也只显示不可改。
        """

        current = str(self.config.resolved_output_dir())
        chosen = QFileDialog.getExistingDirectory(
            self, "选择默认输出目录（快速导出的落点）", current
        )
        if not chosen:
            return
        self.config.output_dir = chosen
        self._save_config("输出目录")
        self._refresh_status()
        logger().info("默认输出目录改为 %s", chosen)

    def _reset_output_dir(self) -> None:
        """清掉自定义值，回到"应用目录下的 outputs/"。"""

        if not self.config.output_dir:
            return
        self.config.output_dir = ""
        self._save_config("输出目录")
        self._refresh_status()

    def _save_config(self, what: str) -> None:
        try:
            self.config.save()
        except OSError as error:
            logger().warning("%s没保存下来：%s", what, error)

    def _toggle_theme(self) -> None:
        """深色 ↔ 浅色（与网站同一套两套配色），并记住选择。"""

        theme = design.toggle_theme()
        self.config.ui_theme = theme.name
        self._save_config("主题偏好")
        self.action_theme.setText(self._theme_action_text())

    def _show_help(self) -> None:
        IllustrationDialog(self).exec()

    # ---- 检查更新 / 反馈问题 ---------------------------------------------

    def _api_client(self):
        from ..api import ApiClient

        return ApiClient(self.config.server_base or None)

    def _check_update(self, *_args, silent: bool = False) -> None:
        """查一次更新。`silent=True`（启动时那次）出错不打扰用户。"""

        from ..api import ApiError
        from ..update import check
        from .update_dialog import UpdateDialog

        try:
            info = check(self._api_client())
        except ApiError as error:
            logger().info("检查更新失败（%s）：%s", error.kind, error)
            if not silent:
                popup.warning(
                    self,
                    i18n.tr("检查更新"),
                    i18n.tr("连不上服务器：%s\n\n可以稍后再试；检查更新的接口是公开的。")
                    % error,
                )
            return

        today = datetime.now().strftime("%Y-%m-%d")
        self.config.last_update_check = today
        self._save_config("检查更新时间")
        if info.has_update:
            self.panel.log_line(
                "发现新版本：%s（当前 %s）%s"
                % (info.latest, info.current, ("　" + info.url) if info.url else "")
            )
            UpdateDialog(info, self).exec()
        elif not silent:
            UpdateDialog(info, self).exec()

    def _maybe_check_update_on_start(self) -> None:
        """启动时最多每天查一次；失败静默（离线也要能正常用）。"""

        if not self.config.check_update_on_start:
            return
        today = datetime.now().strftime("%Y-%m-%d")
        if self.config.last_update_check == today:
            return
        self._check_update(silent=True)

    def _report_problem(self) -> None:
        from .report_dialog import ReportDialog

        dialog = ReportDialog(
            self.config,
            APP_DIR,
            self,
            client=self._api_client(),
            extra={
                "library": self._library_version or "?",
                "theme": design.manager().name,
                "language": i18n.current(),
                "cli": str(self._cli_path()),
            },
        )
        dialog.exec()
        self._save_config("联系方式")

    # ---- 清空所有数据 ----------------------------------------------------

    def _reset_app_data(self) -> None:
        """清掉应用自己的数据（设置 / 素材库 / 产物 / 日志），不碰项目目录。"""

        if self.runner.is_running:
            popup.info(
                self, "导出进行中", "导出任务还没结束，现在不能清空数据。"
            )
            return

        from .reset_dialog import ResetDataDialog

        dialog = ResetDataDialog(APP_DIR, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        keys = dialog.keys()
        if not keys:
            return
        try:
            freed = appdata.clear(APP_DIR, keys)
        except OSError as error:
            logger().exception("清空数据失败：%s", keys)
            popup.warning(self, "清空失败", str(error))
            return

        total = sum(freed.values())
        names = "、".join(appdata.category_for(key).label for key in keys)
        # 清空是个大动作，必须留痕（"我的素材怎么没了"不能变成无头案）
        logger().info("清空数据：%s，释放 %d 字节", names, total)
        if "settings" in keys:
            appdata.reset_config(self.config)
            design.set_theme(self.config.ui_theme)
            self.action_theme.setText(self._theme_action_text())
        self.projects.refresh()
        self._refresh_status()
        self.panel.log_line("已清空：%s（释放约 %s）" % (names, human_size(total)))
        popup.info(
            self,
            "已清空",
            "已清空：%s\n释放约 %s。\n\n项目目录没有被改动。"
            % (names, human_size(total)),
        )

    # ---- 项目 ------------------------------------------------------------

    def _open_project(self, directory: str) -> None:
        """点开一张项目卡片：开一个新窗口，项目的一切都在那里面。"""
        project = Project.load(directory)
        if project is None:
            popup.warning(
                self,
                "项目读不出来",
                "这个目录里读不到 project.json：\n%s\n\n"
                "如果项目被搬到别处，用卡片上的「重新定位」。" % directory,
            )
            self.projects.refresh()
            return
        self.config.register_project(project.path)
        self.config.last_project = str(project.path)
        self.config.save()
        window = ProjectWindow(project, self.config, APP_DIR, self)
        window.closed.connect(lambda: self._forget_project_window(window))
        self._project_windows.append(window)
        window.show()
        window.raise_()

    def _forget_project_window(self, window: "ProjectWindow") -> None:
        self._project_windows = [w for w in self._project_windows if w is not window]
        self.projects.refresh()

    def _show_about(self) -> None:
        from .. import __version__
        from ..applog import session_path

        # 还没问到版本（CLI 换过位置 / 启动时不可用）就现场再问一次
        if not self._library_version:
            self._library_version = probe_library(self._cli_path())
        text = (
            "LittleTiles Reader\n\n"
            + i18n.tr("界面版本：%s\n库版本：%s\n\n")
            + i18n.tr("提交：%s\n\n")
            + i18n.tr("会话日志：\n%s\n\n")
            + i18n.tr("素材来自本机游戏与资源包，本工具只读取、不附带、不分发。")
        )
        popup.info(
            self,
            i18n.tr("关于"),
            text
            % (
                __version__,
                self._library_version or i18n.tr("（没问到库版本）"),
                self._git_revision(),
                session_path() or i18n.tr("（未启用日志）"),
            ),
        )

    def _open_materials(self) -> None:
        """管理素材（导入 / 启用 / 排序）。改完下次导出自动生效。"""
        # 导出进行中不许改素材：组合结果是那次导出正在用的东西，中途换掉会让
        # 产物一半用旧素材、一半用新素材。
        if self.runner.is_running:
            popup.info(
                self, "导出进行中", "导出任务还没结束，现在不能更改素材。"
            )
            return
        manager = MaterialManagerDialog(APP_DIR, self)
        if manager.exec() != MaterialManagerDialog.DialogCode.Accepted:
            return
        chosen = manager.library.selected()
        self._log(
            "素材选择已更新：%s"
            % (" → ".join(s.name for s in chosen) if chosen else "（无，导出白模）")
        )
        self._refresh_status()
        # 有变动就立刻重新组合：组合按顺序指纹缓存，没变是毫秒级命中，
        # 变了正好在用户还在看界面时把它算完，别拖到导出那一刻。
        if chosen:
            # 有变动就立刻重组（走同一条后台线程路径），别拖到导出那一刻
            self._compose_assets(manager.library)

    def _import_assets_file(self) -> str | None:
        """选一个 zip / rar / jar，应用自己判断是什么并整理成素材包。

        只收压缩包，不收目录：用户手上拿到的是下载来的 zip、或游戏里的 jar，
        不该要求他先凑出我们内部的目录格式。
        """
        patterns = " ".join("*%s" % s for s in ARCHIVE_SUFFIXES)
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "选择 zip / rar / jar（Minecraft 1.12.2 客户端 jar 可直接生成素材包）",
            "",
            "压缩包 (%s);;所有文件 (*)" % patterns,
        )
        if not chosen:
            return None
        return self._build_assets_from_file(Path(chosen))

    def _build_assets_from_file(self, chosen: Path) -> str | None:
        """解压 → 认类型 → 能处理就生成素材包。

        慢活全在后台线程里，主线程只负责转圈——不然四十秒的冻结会让用户以为卡死。
        """
        work = APP_DIR / "cache" / "sources"
        self._log("导入素材文件: %s" % chosen)
        out = APP_DIR / "resources" / "packages" / ("vanilla_" + chosen.stem)
        builder = _PackageBuilder(chosen, work, out, self)
        result: dict = {}
        loop = QEventLoop()

        def finished(payload) -> None:
            result["payload"] = payload
            loop.quit()

        builder.finished_with.connect(finished)
        dialog = busy_dialog(
            "导入素材",
            "正在解压并整理素材包…\n\n%s\n\n这一步要几十秒，请稍候。" % chosen.name,
            self,
        )
        builder.start()
        loop.exec()          # 嵌套事件循环：界面照常重绘，进度框一直在动
        builder.wait()
        dialog.close()

        payload = result.get("payload")
        if isinstance(payload, Exception):
            logger().exception("导入素材文件失败: %s", chosen, exc_info=payload)
            popup.warning(self, "导入失败", str(payload))
            return None
        try:
            return self._apply_import(payload)
        except Exception as error:      # 兜底：别让界面卡在一个异常上
            logger().exception("导入素材文件失败: %s", chosen)
            popup.warning(self, "导入失败", str(error))
            return None

    def _apply_import(self, payload: dict) -> str | None:
        """线程回来的结果落到界面与配置上。"""
        kind = payload.get("kind", "unknown")
        self._log("  %s（识别为 %s）" % (payload.get("note") or "已解压", kind))

        if kind == "vanilla":
            build = payload["build"]
            for line in build.output.splitlines()[-4:]:
                self._log("  " + line.strip())
            report = lint_package(build.package_dir)
            self._log(
                "  素材包: %d 方块 / %d 贴图 / 缺 %d"
                % (
                    report.block_count,
                    report.texture_ref_count,
                    len(report.missing_textures),
                )
            )
            if not report.ok:
                popup.warning(self, "生成失败", report.render())
                return None
            self.config.default_assets = str(build.package_dir)
            self.config.save()
            self._refresh_status()
            popup.info(
                self,
                "素材包已生成",
                "已用所选文件生成素材包：\n%s\n\n%d 个方块 / %d 张贴图，缺失 %d 张。\n"
                "已设为默认，之后导出直接用。"
                % (
                    build.package_dir,
                    report.block_count,
                    report.texture_ref_count,
                    len(report.missing_textures),
                ),
            )
            return str(build.package_dir)

        if kind in ("resourcepack", "mod"):
            popup.info(
                self,
                "这个文件还不能单独用",
                "识别为：%s\n\n"
                "它只有贴图，没有「哪个方块的哪一面用哪张图」的信息——那部分是"
                "原版模型定义的。所以它需要先有一个原版底子才能合并进来。\n\n"
                "现在可以先选本机的 Minecraft 1.12.2 客户端 jar（"
                "versions\\1.12.2\\1.12.2.jar）生成素材包；"
                "资源包与模组的合并是后续步骤。"
                % ("资源包" if kind == "resourcepack" else "模组"),
            )
            return None

        popup.warning(
            self,
            "认不出这个文件",
            "解压后没找到 assets/minecraft，也不像资源包或模组。\n\n"
            "如果是客户端 jar，请确认是 1.12.2 版本；"
            "客户端的 assets/ 目录里没有贴图（那只有声音和语言）。",
        )
        return None

    def _run(self, job: dict) -> None:
        """写 job、起进程。工作目录固定为应用目录，产物路径都从 job 里来。"""
        self.panel.run(job, self._cli_path())

    # ---- 两个入口 --------------------------------------------------------

    def _export_region(self) -> None:
        # 第一次用的人不知道三种选择方式的区别，自动把说明弹一次；之后收进按钮。
        first_time = not self.config.shown_chunk_help
        dialog = ExportRegionDialog(
            self.config,
            self,
            initial=self.config.last_export,
            show_help_on_open=first_time,
        )
        if first_time:
            self.config.shown_chunk_help = True
            self.config.save()
        if dialog.exec() != ExportRegionDialog.DialogCode.Accepted:
            return
        if not dialog.save_edit.text().strip():
            popup.warning(self, "缺少存档", "请先选择存档根目录。")
            return
        assets = self._choose_assets()
        if assets is None:
            return
        root = self.config.resolved_output_dir()
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        out_dir = root / ("%s_%s" % (stamp, dialog.output_name()))
        self.config.remember_save(dialog.save_edit.text().strip())
        job = dialog.result_job(assets_package=assets, output_dir=str(out_dir))
        self.config.last_export = dict(job.get("options") or {})
        self.config.save()
        self._run(job)

    def _export_snbt(self) -> None:
        """快速导出结构：文件或粘贴文本，两者等价（与项目模式同一套入口）。

        粘贴的文本先落成 `tmp/<时间戳>_paste.txt` 再交给库——job 契约只认路径，
        留一份文件也便于事后追溯。
        """

        picked = choose_snbt_source(self)
        if picked is None:
            return
        kind, payload = picked
        if kind == "paste":
            chosen = str(save_pasted_snbt(payload, APP_DIR / "tmp"))
            self.panel.log_line("粘贴的 SNBT 已存为：%s" % chosen)
            stem = "paste_%s" % datetime.now().strftime("%Y%m%d_%H%M%S")
        else:
            chosen = payload
            stem = Path(chosen).stem
        assets = self._choose_assets()
        if assets is None:
            return
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        out_dir = self.config.resolved_output_dir() / ("%s_%s" % (stamp, stem))
        self.config.remember_snbt(chosen)
        self.config.save()
        self._run(
            build_snbt_job(
                snbt_path=chosen,
                assets_package=assets,
                output_dir=str(out_dir),
                output_name=stem,
                options=default_options(center=True, normalize_scale=False),
            )
        )

    # ---- 进度与日志 ------------------------------------------------------

    def _log(self, text: str) -> None:
        self.panel.log_line(text)

    def _on_event(self, event: dict) -> None:
        self.panel.apply_event(event)

    def _on_finished(self, ok: bool, exit_code: int) -> None:
        self.panel.handle_finished(ok, exit_code)
        self.raise_()

    def _on_library_version(self, version: str) -> None:
        self._library_version = version
        self._refresh_status()

    # ---- 输出目录 --------------------------------------------------------

    def _output_dir_of(self, result: dict) -> Path | None:
        return self.panel.output_dir_of(result)

    def _open_last_output(self) -> None:
        self.panel.open_last_output()

    def _offer_open_output(self, directory: Path | None) -> None:
        self.panel.offer_open_output(directory)
