"""LittleTiles Reader 桌面应用。

与库的边界：**通过子进程调用** `LittleTilesReader`，契约是库仓库的
`docs/job.md`（job JSON 进、NDJSON 进度出）。应用从不链接库，也不自己解析存档。

生成端（`ltgen/`、`tools/`）则在本进程内直接 import——这正是两边同一个仓库的原因。
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
