"""跑库的 CLI，把 NDJSON 事件转成 Qt 信号。

用 QProcess 而不是 subprocess：它把子进程接入 Qt 事件循环，界面不会被阻塞，
也不需要自己开线程读管道。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

from .job import parse_event


class ExportRunner(QObject):
    """一次导出 = 一个子进程。事件走 `event`，其余输出原样走 `output_line`。"""

    event = Signal(dict)
    output_line = Signal(str)
    finished = Signal(bool, int)  # ok, exit_code

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._read_stdout)
        self._process.readyReadStandardError.connect(self._read_stderr)
        self._process.finished.connect(self._on_finished)
        self._stdout_buffer = ""

    @property
    def is_running(self) -> bool:
        return self._process.state() != QProcess.ProcessState.NotRunning

    def start(self, cli: Path, job_path: Path, work_dir: Path) -> None:
        if self.is_running:
            raise RuntimeError("an export is already running")
        self._stdout_buffer = ""
        self._process.setWorkingDirectory(str(work_dir))
        self._process.start(str(cli), ["--job", str(job_path), "--progress", "json"])

    def cancel(self) -> None:
        """用户点了取消：直接终止。产物可能不完整，由调用方决定要不要清。"""
        if self.is_running:
            self._process.kill()

    def _read_stdout(self) -> None:
        chunk = bytes(self._process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        self._stdout_buffer += chunk
        while "\n" in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
            event = parse_event(line)
            if event is not None:
                self.event.emit(event)
            elif line.strip():
                # 库在 JSON 模式下不该往 stdout 写人话；真写了也照实显示，
                # 否则出错时用户看不到任何线索。
                self.output_line.emit(line)

    def _read_stderr(self) -> None:
        text = bytes(self._process.readAllStandardError()).decode(
            "utf-8", errors="replace"
        )
        for line in text.splitlines():
            if line.strip():
                self.output_line.emit(line)

    def _on_finished(self, exit_code: int, _status: object) -> None:
        # 收尾：管道里可能还剩半行
        if self._stdout_buffer.strip():
            event = parse_event(self._stdout_buffer)
            if event is not None:
                self.event.emit(event)
            else:
                self.output_line.emit(self._stdout_buffer)
            self._stdout_buffer = ""
        self.finished.emit(exit_code == 0, exit_code)
