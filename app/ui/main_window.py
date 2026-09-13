"""启动界面：两个大入口 + 导出进度与日志。

M1 只做"快速导出"这条路（不绑定项目、不留记录）；项目模式在 M2。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QCheckBox,
    QVBoxLayout,
    QWidget,
)

from ltgen import paths

from ..config import APP_DIR, AppConfig
from ..job import ExportProgress, build_snbt_job, default_options, write_job
from ..runner import ExportRunner
from .export_dialog import ExportRegionDialog
from .theme import colors_for


def big_button_style(palette) -> str:
    """两个大入口的样式。

    颜色从调色板取——写死 `#ffffff` 的话，深色模式下就是白底浅字。
    """
    colors = colors_for(palette)
    return """
QPushButton {{
    font-size: 18px; padding: 26px 18px; border-radius: 10px;
    border: 1px solid {border}; background: {surface};
    color: {text}; text-align: center;
}}
QPushButton:hover {{ background: {hover}; border-color: {accent}; }}
QPushButton:disabled {{ color: {muted}; }}
""".format(
        border=colors.border.name(),
        surface=colors.surface.name(),
        text=colors.text.name(),
        hover=colors.surface_hover.name(),
        accent=colors.accent_strong.name(),
        muted=colors.muted.name(),
    )


def open_directory(path: Path) -> bool:
    """用系统默认的文件管理器打开目录（Windows 资源管理器 / macOS 访达）。

    独立成函数，一是跨平台只在这一处，二是测试时可以替换掉，避免真弹窗口。
    """
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.setWindowTitle("LittleTiles Reader")
        self.resize(880, 640)
        self.config = config
        self.progress = ExportProgress()
        self._last_output_dir: Path | None = None
        self.runner = ExportRunner(self)
        self.runner.event.connect(self._on_event)
        self.runner.output_line.connect(self._log)
        self.runner.finished.connect(self._on_finished)
        self._build_ui()
        self._refresh_status()

    # ---- 界面 ------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        title = QLabel("要做什么？")
        title.setFont(QFont("", 12, QFont.Weight.Bold))
        layout.addWidget(title)

        buttons = QHBoxLayout()
        self.btn_snbt = QPushButton("导出 SNBT\n（结构文件 / 粘贴文本）")
        self.btn_region = QPushButton("导出存档\n（选区块导出 OBJ）")
        for button in (self.btn_snbt, self.btn_region):
            buttons.addWidget(button, 1)
        layout.addLayout(buttons)
        self.btn_snbt.clicked.connect(self._export_snbt)
        self.btn_region.clicked.connect(self._export_region)

        self.hint = QLabel(
            "两个入口都是快速导出：不绑定项目、不记录历史。"
            "项目管理在 M2 提供。"
        )
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        # 等两个控件都建好了再上色（它俩的样式都从调色板来）
        self._apply_button_style()

        row = QHBoxLayout()
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.cancel = QPushButton("取消")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.runner.cancel)
        self.open_output = QPushButton("打开输出目录")
        self.open_output.setEnabled(False)
        self.open_output.clicked.connect(self._open_last_output)
        row.addWidget(self.bar, 1)
        row.addWidget(self.open_output)
        row.addWidget(self.cancel)
        layout.addLayout(row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("导出日志会显示在这里")
        layout.addWidget(self.log, 1)

        self.setCentralWidget(central)
        self.status = self.statusBar()

    def _apply_button_style(self) -> None:
        style = big_button_style(self.palette())
        for button in (self.btn_snbt, self.btn_region):
            button.setStyleSheet(style)
        self.hint.setStyleSheet("color: %s;" % colors_for(self.palette()).muted.name())

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_button_style()
        super().changeEvent(event)

    def _refresh_status(self) -> None:
        cli = self._cli_path()
        assets = self.config.default_assets or "（未设置）"
        self.status.showMessage("库 CLI: %s    素材包: %s" % (cli, assets))

    # ---- 依赖解析 --------------------------------------------------------

    def _cli_path(self) -> Path:
        if self.config.library_cli:
            return Path(self.config.library_cli)
        return paths.reader_executable()

    def _ensure_assets(self) -> str:
        """M1 还没有素材管理，先让用户指一个素材包目录并用配置记住。"""
        if self.config.default_assets and Path(self.config.default_assets).is_dir():
            return self.config.default_assets
        chosen = QFileDialog.getExistingDirectory(
            self, "选择素材包目录（含 block_textures.tsv 与 textures/）"
        )
        if not chosen:
            return ""
        self.config.default_assets = chosen
        self.config.save()
        self._refresh_status()
        return chosen

    def _run(self, job: dict) -> None:
        """写 job、起进程。工作目录固定为应用目录，产物路径都从 job 里来。"""
        if self.runner.is_running:
            return
        cli = self._cli_path()
        if not Path(cli).is_file():
            QMessageBox.warning(self, "找不到库", "找不到 LittleTilesReader：\n%s" % cli)
            return
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        job_path = APP_DIR / "tmp" / ("job_%s.json" % stamp)
        write_job(job, job_path)
        self._last_output_dir = Path(job["output"]["dir"])
        self.open_output.setEnabled(True)
        self.progress = ExportProgress()
        self.bar.setValue(0)
        self.log.clear()
        self._log("运行: %s --job %s --progress json" % (cli, job_path))
        self._log("输出: %s" % job["output"]["dir"])
        # 把本次选项写进日志：用户怀疑"某个开关没生效"时，先看这一行。
        options = job.get("options") or {}
        if options:
            names = {
                "plain_blocks": "普通方块",
                "cull_hidden_faces": "剔除遮挡面",
                "center": "居中",
                "normalize_scale": "单位缩放",
            }
            self._log(
                "选项: "
                + "  ".join(
                    "%s=%s" % (names.get(k, k), "是" if v else "否")
                    for k, v in options.items()
                )
            )
        self.cancel.setEnabled(True)
        self.runner.start(cli, job_path, APP_DIR)

    # ---- 两个入口 --------------------------------------------------------

    def _export_region(self) -> None:
        dialog = ExportRegionDialog(self.config, self, initial=self.config.last_export)
        if dialog.exec() != ExportRegionDialog.DialogCode.Accepted:
            return
        if not dialog.save_edit.text().strip():
            QMessageBox.warning(self, "缺少存档", "请先选择存档根目录。")
            return
        assets = self._ensure_assets()
        if not assets:
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
        chosen, _ = QFileDialog.getOpenFileName(
            self, "选择 LittleTiles 结构文件", "", "结构文件 (*.txt *.struct);;所有文件 (*)"
        )
        if not chosen:
            return
        assets = self._ensure_assets()
        if not assets:
            return
        stem = Path(chosen).stem
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
        self.log.appendPlainText(text)

    def _on_event(self, event: dict) -> None:
        self.progress.apply(event)
        self.bar.setValue(self.progress.percent)
        kind = event.get("event")
        if kind == "assets":
            self._log(
                "素材包: %s 个方块 / %s 张贴图 / 缺 %s"
                % (event.get("blocks"), event.get("textures"), event.get("missing"))
            )
        elif kind == "start":
            self._log("开始：%s，%s 个区块" % (event.get("mode"), event.get("chunks")))
        elif kind == "chunk":
            self._log(
                "  区块 (%s, %s)  %s/%s"
                % (event.get("x"), event.get("z"), event.get("index"), event.get("total"))
            )
        elif kind == "stage":
            self._log("阶段: %s" % event.get("name"))
        elif kind == "warning":
            self._log("警告: %s" % event.get("message"))
        elif kind == "error":
            self._log("错误: %s" % event.get("message"))

    def _on_finished(self, ok: bool, exit_code: int) -> None:
        self.cancel.setEnabled(False)
        result = self.progress.result
        if ok and not self.progress.error:
            self.bar.setValue(100)
            self._log(
                "完成：%s 面 / %s 顶点 / %s 材质 / %s 贴图，耗时 %ss"
                % (
                    result.get("faces"),
                    result.get("vertices"),
                    result.get("materials"),
                    result.get("textures_written"),
                    result.get("seconds"),
                )
            )
            self._log("产物: %s" % result.get("obj"))
            self._offer_open_output(self._output_dir_of(result))
        else:
            self.bar.setValue(0)
            self._log("失败（退出码 %d）" % exit_code)
        self.raise_()

    # ---- 输出目录 --------------------------------------------------------

    def _output_dir_of(self, result: dict) -> Path | None:
        """优先用产物所在目录；拿不到就退回 job 里指定的那个。"""
        obj = result.get("obj")
        if obj:
            return Path(str(obj)).parent
        return self._last_output_dir

    def _open_last_output(self) -> None:
        if self._last_output_dir is not None and self._last_output_dir.is_dir():
            open_directory(self._last_output_dir)

    def _offer_open_output(self, directory: Path | None) -> None:
        """导出完成后问一句要不要打开。可以在配置里关掉（勾选一次即可）。"""
        if directory is None or not self.config.ask_open_output:
            return
        if not directory.is_dir():
            # 目录都没了（用户挪走/删掉）就不问了
            return

        box = QMessageBox(self)
        box.setWindowTitle("导出完成")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText("导出完成。")
        box.setInformativeText("要打开输出目录吗？\n%s" % directory)
        box.setStandardButtons(
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Close
        )
        box.setDefaultButton(QMessageBox.StandardButton.Open)
        never = QCheckBox("以后不再询问")
        box.setCheckBox(never)

        if box.exec() == QMessageBox.StandardButton.Open:
            open_directory(directory)
        if never.isChecked():
            self.config.ask_open_output = False
            self.config.save()
