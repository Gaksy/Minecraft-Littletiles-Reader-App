"""按"每次启动"切割的会话日志。

一次启动 = 一个文件：`logs/<YYYY-MM-DD_HHMMSS>.log`。
为什么要按启动切：出问题时你关心的是"**那一次**到底做了什么"——把多次运行混在
一个文件里，时间线会被搅在一起，而且旧记录会被不断追加得越来越长。

每行都有时间戳。除了界面上的操作，**每次导出的 job 原文也会记进来**：
只有它完整记录了当时用的是哪个存档、哪几个区块、什么选项、哪个素材包——
排错时第一个要看的就是它，而 tmp/ 里的 job 文件会被后来的运行挤掉。
"""

from __future__ import annotations

import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

LOGGER_NAME = "ltr"
KEEP_SESSIONS = 30  # 保留最近多少次会话的日志

_session_path: Path | None = None


def logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def session_path() -> Path | None:
    return _session_path


def start_session(app_dir: Path, version: str) -> Path:
    """开一个会话日志并返回它的路径。重复调用只会返回同一个文件。"""
    global _session_path
    if _session_path is not None:
        return _session_path

    log_dir = app_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / (datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".log")

    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
    )
    log = logger()
    log.setLevel(logging.DEBUG)
    log.handlers.clear()   # 同一进程里重复调用时别叠加 handler
    log.addHandler(handler)
    log.propagate = False
    _session_path = path

    log.info("=== 会话开始 · 应用 %s ===", version)
    log.info("应用目录: %s", app_dir)
    log.info("Python: %s", sys.version.split()[0])
    _install_excepthook(log)
    _prune(log_dir)
    return path


def _install_excepthook(log: logging.Logger) -> None:
    """未捕获的异常也要落盘——那正是最需要事后分析的时刻。"""

    def hook(kind, value, tb) -> None:
        log.critical(
            "未捕获异常:\n%s", "".join(traceback.format_exception(kind, value, tb))
        )
        sys.__excepthook__(kind, value, tb)

    sys.excepthook = hook


def _prune(log_dir: Path, keep: int = KEEP_SESSIONS) -> None:
    """只留最近 keep 个会话日志，避免无限增长。"""
    try:
        files = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    for old in files[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass
