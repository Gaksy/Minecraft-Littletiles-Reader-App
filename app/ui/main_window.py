"""启动界面：两个大入口 + 导出进度与日志。

M1 只做"快速导出"这条路（不绑定项目、不留记录）；项目模式在 M2。
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from PySide6.QtCore import QEvent, QEventLoop, QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QCheckBox,
    QVBoxLayout,
    QWidget,
)

from ltgen import paths
from ltgen.lint import lint_package

from ..applog import logger
from ..config import APP_DIR, AppConfig
from ..job import ExportProgress, build_snbt_job, default_options, write_job
from ..runner import ExportRunner
from ..sources import ARCHIVE_SUFFIXES, resolve_source
from ..vanilla import build_package_from_resolved, detect_kind
from .export_dialog import ExportRegionDialog
from .material_dialog import MaterialChoiceDialog
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
    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.setWindowTitle("LittleTiles Reader")
        self.resize(880, 640)
        self.config = config
        self.progress = ExportProgress()
        self._last_output_dir: Path | None = None
        self._library_version = ""   # 由 start 事件带回
        self.runner = ExportRunner(self)
        self.runner.event.connect(self._on_event)
        self.runner.output_line.connect(self._log)
        self.runner.finished.connect(self._on_finished)
        self._build_ui()
        self._refresh_status()
        # 启动时把"这次是在什么环境下跑的"记进会话日志，排错第一眼就看这些
        cli = self._cli_path()
        logger().info("库 CLI: %s（存在=%s）", cli, Path(cli).is_file())
        logger().info("默认素材包: %s", self.config.default_assets or "（未设置）")
        logger().info("默认输出目录: %s", self.config.resolved_output_dir())

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
        # 素材包：不可用的要当场标出来。否则一个失效路径（比如误选成了导出目录）
        # 会被当成"已配置"，用户看状态栏以为没问题。
        configured = self.config.default_assets
        if not configured:
            assets = "（未设置）"
        elif lint_package(Path(configured)).ok:
            assets = configured
        else:
            assets = "（不可用，导出时会让你重选）%s" % configured
        version = ("    库 %s" % self._library_version) if self._library_version else ""
        self.status.showMessage(
            "素材包: %s    模型输出目录: %s%s    CLI: %s"
            % (assets, self.config.resolved_output_dir(), version, cli)
        )

    # ---- 依赖解析 --------------------------------------------------------

    def _cli_path(self) -> Path:
        if self.config.library_cli:
            return Path(self.config.library_cli)
        return paths.reader_executable()

    def _choose_assets(self) -> str | None:
        """问一句本次用什么材质。

        返回素材包路径；`""` = 不用材质（导出白模）；`None` = 用户取消。

        为什么要问而不是直接用配置：第一次用的人手上通常什么都没有，
        "不用材质"必须能一步选到，而不是被逼着去翻目录选择框。
        """
        configured = self.config.default_assets
        if configured and not lint_package(Path(configured)).ok:
            self._log("已配置的素材包不可用，请重新选择：%s" % configured)
            configured = ""

        dialog = MaterialChoiceDialog(configured, self)
        if dialog.exec() != MaterialChoiceDialog.DialogCode.Accepted:
            return None
        if dialog.choice == "none":
            self._log(
                "本次不使用材质：导出白模（几何完整，但没有贴图/MTL）。"
            )
            return ""
        if dialog.choice == "configured" and configured:
            for warning in lint_package(Path(configured)).warnings:
                self._log("素材包提示: %s" % warning)
            return configured
        return self._import_assets_file()

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
            QMessageBox.warning(self, "导入失败", str(payload))
            return None
        try:
            return self._apply_import(payload)
        except Exception as error:      # 兜底：别让界面卡在一个异常上
            logger().exception("导入素材文件失败: %s", chosen)
            QMessageBox.warning(self, "导入失败", str(error))
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
                QMessageBox.warning(self, "生成失败", report.render())
                return None
            self.config.default_assets = str(build.package_dir)
            self.config.save()
            self._refresh_status()
            QMessageBox.information(
                self,
                "素材包已生成",
                "已用你选择的文件生成素材包：\n%s\n\n%d 个方块 / %d 张贴图，缺失 %d 张。\n"
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
            QMessageBox.information(
                self,
                "这个文件还不能单独用",
                "识别为：%s\n\n"
                "它只有贴图，没有「哪个方块的哪一面用哪张图」的信息——那部分是"
                "原版模型定义的。所以它需要先有一个原版底子才能合并进来。\n\n"
                "现在可以先选你自己的 Minecraft 1.12.2 客户端 jar（"
                "versions\\1.12.2\\1.12.2.jar）生成素材包；"
                "资源包与模组的合并是后续步骤。"
                % ("资源包" if kind == "resourcepack" else "模组"),
            )
            return None

        QMessageBox.warning(
            self,
            "认不出这个文件",
            "解压后没找到 assets/minecraft，也不像资源包或模组。\n\n"
            "如果是客户端 jar，请确认是 1.12.2 版本；"
            "客户端的 assets/ 目录里没有贴图（那只有声音和语言）。",
        )
        return None

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
        # 只有它能完整还原"这次到底跑的是什么"——tmp/ 里的 job 文件会被后来的运行挤掉，
        # 所以原文也进会话日志。
        logger().info(
            "job 原文 (%s):\n%s",
            job_path,
            json.dumps(job, ensure_ascii=False, indent=2),
        )
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
            QMessageBox.warning(self, "缺少存档", "请先选择存档根目录。")
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
        chosen, _ = QFileDialog.getOpenFileName(
            self, "选择 LittleTiles 结构文件", "", "结构文件 (*.txt *.struct);;所有文件 (*)"
        )
        if not chosen:
            return
        assets = self._choose_assets()
        if assets is None:
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
        """界面日志与文件日志同源：屏幕上看到的每一行都带时间戳落到会话日志里。"""
        self.log.appendPlainText(text)
        logger().info(text)

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
            library = event.get("library")
            if library:
                # 记下是哪个版本的库在干活：产物出问题时这是第一条线索
                self._library_version = str(library)
                self._refresh_status()
            self._log(
                "开始：%s，%s 个区块（库 %s）"
                % (event.get("mode"), event.get("chunks"), library or "?")
            )
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
