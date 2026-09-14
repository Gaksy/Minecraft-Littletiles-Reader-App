"""导出面板：进度条 + 取消/打开输出目录 + 日志。

主界面（快速导出）和项目界面（项目导出）用的是同一块——**同一套进度语义只能
有一份实现**。以前"写文件阶段切不确定进度"这种修正就吃过亏：改了一处，另一处
还停在 100% 让人以为卡死。

"打开目录"和"消息框"是**注入**的：主界面测试会把 `main_window.open_directory`
换成替身，直接在别的模块里调用 `QDesktopServices` 就绕过了替身，测试会真的弹出
文件管理器。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..applog import logger
from ..config import AppConfig
from ..job import ExportProgress, write_job
from ..runner import ExportRunner
from ..storage import human_size

# 阶段名 → 给用户看的中文（库发的是 parse/mesh/write）
STAGE_LABELS = {"parse": "解析", "mesh": "建网格", "write": "写出文件"}

OPTION_LABELS = {
    "plain_blocks": "普通方块",
    "cull_hidden_faces": "剔除遮挡面",
    "center": "居中",
    "normalize_scale": "单位缩放",
}


def default_open_directory(path: Path) -> bool:
    """用系统默认的文件管理器打开目录（Windows 资源管理器 / macOS 访达）。"""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class ExportPanel(QWidget):
    """一次导出 = 一个子进程。事件走日志与进度条。"""

    finished_ok = Signal(bool, dict)   # 成功与否，库的 done 事件（失败时为空）
    library_version = Signal(str)      # 本次干活的是哪个版本的库

    def __init__(
        self,
        config: AppConfig,
        app_dir: Path,
        parent: QWidget | None = None,
        open_directory: Callable[[Path], bool] | None = None,
        message_box=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.app_dir = Path(app_dir)
        self.last_output_dir: Path | None = None
        self.last_obj: Path | None = None       # 最近一次导出的模型（打包用）
        self.progress = ExportProgress()
        self.runner = ExportRunner(self)
        self._open_directory = open_directory or default_open_directory
        self._message_box = message_box or QMessageBox
        self._version = ""
        self._build_ui()
        self.runner.event.connect(self.apply_event)
        self.runner.output_line.connect(self.log_line)
        self.runner.finished.connect(self.handle_finished)

    # ---- 界面 ------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout()
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        # 打包：把 OBJ + MTL + 这次用到的贴图收成一个能拷走的 zip
        self.open_output = QPushButton("打开输出目录")
        self.open_output.setEnabled(False)
        self.open_output.clicked.connect(self.open_last_output)
        self.pack = QPushButton("打包成 zip")
        self.pack.setEnabled(False)
        self.pack.setToolTip(
            "把模型、MTL 与这次用到的贴图收成一个 zip（放在产物目录里），"
            "拷贝到别处也能直接用"
        )
        self.pack.clicked.connect(self.pack_last_output)
        self.cancel = QPushButton("取消")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.runner.cancel)
        row.addWidget(self.bar, 1)
        row.addWidget(self.open_output)
        row.addWidget(self.pack)
        row.addWidget(self.cancel)
        root.addLayout(row)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("导出日志会显示在这里")
        root.addWidget(self.log_view, 1)

    # ---- 跑一次 ----------------------------------------------------------

    def run(self, job: dict, cli: Path, job_dir: Path | None = None) -> bool:
        """写 job、起进程。返回 False 表示这次没跑起来（调用方据此提示）。

        `job_dir` 给了就把 job 写在那里（项目模式写进产物目录，随产物一起留下，
        将来"重建贴图"靠它）；不给就写进应用目录的 `tmp/`（快速导出，不留副本）。
        """
        if self.runner.is_running:
            return False
        if not Path(cli).is_file():
            self._message_box_warning(
                "找不到库", "找不到 LittleTilesReader：\n%s" % cli
            )
            return False
        if job_dir is not None:
            job_path = Path(job_dir) / "job.json"
        else:
            stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            job_path = self.app_dir / "tmp" / ("job_%s.json" % stamp)
        write_job(job, job_path)
        # 只有它能完整还原"这次到底跑的是什么"——tmp/ 里的 job 文件会被后来的运行挤掉，
        # 所以原文也进会话日志。
        logger().info(
            "job 原文 (%s):\n%s", job_path, json.dumps(job, ensure_ascii=False, indent=2)
        )
        self.last_output_dir = Path(job["output"]["dir"])
        self.last_obj = None
        self.open_output.setEnabled(True)
        self.pack.setEnabled(False)
        self.progress = ExportProgress()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.log_view.clear()
        self.log_line("运行: %s --job %s --progress json" % (cli, job_path))
        self.log_line("输出: %s" % job["output"]["dir"])
        options = job.get("options") or {}
        if options:
            # 把本次选项写进日志：用户怀疑"某个开关没生效"时，先看这一行。
            self.log_line(
                "选项: "
                + "  ".join(
                    "%s=%s" % (OPTION_LABELS.get(k, k), "是" if v else "否")
                    for k, v in options.items()
                )
            )
        self.cancel.setEnabled(True)
        self.runner.start(cli, job_path, self.app_dir)
        return True

    # ---- 事件 ------------------------------------------------------------

    def log_line(self, text: str) -> None:
        """界面日志与文件日志同源：屏幕上看到的每一行都带时间戳落到会话日志里。"""
        self.log_view.appendPlainText(text)
        logger().info(text)

    def apply_event(self, event: dict) -> None:
        self.progress.apply(event)
        self.bar.setValue(self.progress.percent)
        kind = event.get("event")
        if kind == "assets":
            self.log_line(
                "素材包: %s 个方块 / %s 张贴图 / 缺 %s"
                % (event.get("blocks"), event.get("textures"), event.get("missing"))
            )
        elif kind == "start":
            library = event.get("library")
            if library:
                # 记下是哪个版本的库在干活：产物出问题时这是第一条线索
                self._version = str(library)
                self.library_version.emit(self._version)
            self.log_line(
                "开始：%s，%s 个区块（库 %s）"
                % (event.get("mode"), event.get("chunks"), library or "?")
            )
        elif kind == "chunk":
            self.log_line(
                "  区块 (%s, %s)  %s/%s"
                % (
                    event.get("x"),
                    event.get("z"),
                    event.get("index"),
                    event.get("total"),
                )
            )
        elif kind == "stage":
            name = str(event.get("name", ""))
            self.log_line("阶段: %s" % STAGE_LABELS.get(name, name))
            if name in ("write", "mesh"):
                # 区块读完了，接下来是建网格/写文件+烘焙贴图，可能很久。
                # 进度条切到"不确定"模式，别停在 100% 让人以为卡死。
                self.bar.setRange(0, 0)
        elif kind == "warning":
            self.log_line("警告: %s" % event.get("message"))
        elif kind == "error":
            self.log_line("错误: %s" % event.get("message"))

    def handle_finished(self, ok: bool, exit_code: int) -> None:
        self.bar.setRange(0, 100)     # 从"不确定"模式切回来
        self.cancel.setEnabled(False)
        result = self.progress.result
        if ok and not self.progress.error:
            self.bar.setValue(100)
            self.log_line(
                "完成：%s 面 / %s 顶点 / %s 材质 / %s 贴图，耗时 %ss"
                % (
                    result.get("faces"),
                    result.get("vertices"),
                    result.get("materials"),
                    result.get("textures_written"),
                    result.get("seconds"),
                )
            )
            self.log_line("产物: %s" % result.get("obj"))
            self.set_obj(result.get("obj"))
            self.offer_open_output(self.output_dir_of(result))
        else:
            self.bar.setValue(0)
            self.log_line("失败（退出码 %d）" % exit_code)
        self.finished_ok.emit(bool(ok and not self.progress.error), dict(result))

    # ---- 输出目录 --------------------------------------------------------

    def set_obj(self, obj: str | Path | None) -> None:
        """记下"这次的模型是哪个文件"，并让「打包成 zip」可用。"""

        path = Path(str(obj)) if obj else None
        self.last_obj = path if (path is not None and path.is_file()) else None
        self.pack.setEnabled(self.last_obj is not None)

    def pack_last_output(self) -> dict | None:
        """把最近一次导出的产物打成 zip（自足：OBJ + MTL + 贴图）。"""

        if self.last_obj is None:
            self.log_line("没有可打包的模型（先导出一次）。")
            return None
        return self.pack_obj(self.last_obj)

    def pack_obj(self, obj: Path) -> dict | None:
        """打包指定模型；成功后在日志里说清包在哪、装了什么。"""

        from ..packaging import pack
        from .background import run_in_background

        try:
            result = run_in_background(
                self,
                "打包成 zip",
                "正在把模型、MTL 与贴图收进一个 zip…\n\n%s" % Path(obj).name,
                lambda: pack(obj),
            )
        except Exception as error:      # 打包失败不该盖住"导出其实成功了"
            logger().exception("打包失败：%s", obj)
            self.log_line("打包失败：%s" % error)
            self._message_box_warning("打包失败", str(error))
            return None
        self.log_line(
            "打包完成：%s（%d 个 MTL / %d 张贴图 / %s）"
            % (
                result.zip_path,
                result.materials,
                result.textures,
                human_size(result.size_bytes),
            )
        )
        if result.missing:
            self.log_line(
                "警告：有 %d 个贴图文件没找到，包里缺它们：%s"
                % (len(result.missing), "、".join(result.missing[:5]))
            )
        box = self._message_box(self)
        box.setWindowTitle("打包完成")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText("已打包成 zip。")
        box.setInformativeText(
            "%s\n\n模型 + MTL + %d 张贴图，约 %s。\n"
            "把这个 zip 拷到别处解压即可使用，不需要再拷贴图库。"
            % (result.zip_path, result.textures, human_size(result.size_bytes))
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Close
        )
        box.setDefaultButton(QMessageBox.StandardButton.Open)
        if box.exec() == QMessageBox.StandardButton.Open:
            self._open_directory(result.zip_path.parent)
        return {
            "zip": str(result.zip_path),
            "textures": result.textures,
            "missing": list(result.missing),
        }

    def output_dir_of(self, result: dict) -> Path | None:
        """优先用产物所在目录；拿不到就退回 job 里指定的那个。"""
        obj = result.get("obj")
        if obj:
            return Path(str(obj)).parent
        return self.last_output_dir

    def open_last_output(self) -> None:
        if self.last_output_dir is not None and self.last_output_dir.is_dir():
            self._open_directory(self.last_output_dir)

    def offer_open_output(self, directory: Path | None) -> None:
        """导出完成后问一句要不要打开。可以在配置里关掉（勾选一次即可）。"""
        if directory is None or not self.config.ask_open_output:
            return
        if not directory.is_dir():
            # 目录都没了（用户挪走/删掉）就不问了
            return

        box = self._message_box(self)
        box.setWindowTitle("导出完成")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText("导出完成。")
        box.setInformativeText(
            "要打开输出目录吗？\n%s\n\n"
            "要把模型拷到别处用（发人或换机器），点面板上的「打包成 zip」——"
            "它会连贴图一起打包。" % directory
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Close
        )
        box.setDefaultButton(QMessageBox.StandardButton.Open)
        never = QCheckBox("以后不再询问")
        box.setCheckBox(never)

        if box.exec() == QMessageBox.StandardButton.Open:
            self._open_directory(directory)
        if never.isChecked():
            self.config.ask_open_output = False
            self.config.save()

    def _message_box_warning(self, title: str, text: str) -> None:
        box = self._message_box(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()
