"""job 的构造与进度解析——**不依赖 Qt**，所以能单独跑测试。

字段与事件格式的权威定义在库仓库的 `docs/job.md`；这里只做构造与解析，
不重复解释语义。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# 维度 → job 里的 dimension 值（库侧接受这些写法）
DIMENSIONS = ("overworld", "nether", "the_end")
DIMENSION_LABELS = {
    "overworld": "主世界",
    "nether": "下界",
    "the_end": "末地",
}

CHUNK_MODES = ("single", "range", "center")
CHUNK_MODE_LABELS = {
    "single": "单区块",
    "range": "区块范围",
    "center": "中心 + 半径",
}


@dataclass
class ChunkRange:
    """展开后的区块矩形（含两端）。"""

    min_x: int
    min_z: int
    count_x: int
    count_z: int

    @property
    def total(self) -> int:
        return self.count_x * self.count_z

    def cells(self) -> list[tuple[int, int]]:
        return [
            (self.min_x + dx, self.min_z + dz)
            for dz in range(self.count_z)
            for dx in range(self.count_x)
        ]


def expand_chunks(
    mode: str,
    *,
    x: int = 0,
    z: int = 0,
    radius: int = 0,
    x1: int = 0,
    z1: int = 0,
    x2: int = 0,
    z2: int = 0,
) -> ChunkRange:
    """把三种选择模式展开成矩形。与库侧 `ParseChunkRange` 同一套规则。"""
    if mode == "single":
        return ChunkRange(x, z, 1, 1)
    if mode == "range":
        return ChunkRange(
            min(x1, x2), min(z1, z2), abs(x2 - x1) + 1, abs(z2 - z1) + 1
        )
    if mode == "center":
        r = max(0, radius)
        return ChunkRange(x - r, z - r, 2 * r + 1, 2 * r + 1)
    raise ValueError("unknown chunk mode: %r" % mode)


def chunks_field(mode: str, **kwargs: int) -> dict:
    """拼 job 里的 `input.chunks`（保留用户选的原模式，让库自己展开）。"""
    if mode == "single":
        return {"mode": "single", "x": kwargs["x"], "z": kwargs["z"]}
    if mode == "range":
        return {
            "mode": "range",
            "x1": kwargs["x1"],
            "z1": kwargs["z1"],
            "x2": kwargs["x2"],
            "z2": kwargs["z2"],
        }
    if mode == "center":
        return {
            "mode": "center",
            "x": kwargs["x"],
            "z": kwargs["z"],
            "radius": max(0, kwargs["radius"]),
        }
    raise ValueError("unknown chunk mode: %r" % mode)


def default_options(
    *,
    plain_blocks: bool = True,
    cull_hidden_faces: bool = True,
    center: bool = True,
    normalize_scale: bool = False,
) -> dict:
    return {
        "plain_blocks": plain_blocks,
        "cull_hidden_faces": cull_hidden_faces,
        "center": center,
        "normalize_scale": normalize_scale,
    }


def build_region_job(
    *,
    world_root: str,
    dimension: str,
    chunks: dict,
    assets_package: str,
    output_dir: str,
    output_name: str,
    options: dict | None = None,
) -> dict:
    """存档导出。`world_root` 是**存档根目录**（含 level.dat），不是 region 目录。"""
    return {
        "schema": 1,
        "mode": "region",
        "input": {
            "world": {"root": world_root, "dimension": dimension},
            "chunks": chunks,
        },
        "assets": {"package": assets_package},
        "output": {"dir": output_dir, "name": output_name},
        "options": dict(options or {}),
    }


def build_snbt_job(
    *,
    snbt_path: str,
    assets_package: str,
    output_dir: str,
    output_name: str,
    options: dict | None = None,
) -> dict:
    """结构文件导出。粘贴来的文本由调用方先落成文件再传路径。"""
    return {
        "schema": 1,
        "mode": "snbt",
        "input": {"snbt": {"path": snbt_path}},
        "assets": {"package": assets_package},
        "output": {"dir": output_dir, "name": output_name},
        "options": dict(options or {}),
    }


def write_job(job: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def parse_event(line: str) -> dict | None:
    """解析一行 NDJSON；不是事件（空行、非 JSON）返回 None。"""
    text = line.strip()
    if not text or not text.startswith("{"):
        return None
    try:
        event = json.loads(text)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) and "event" in event else None


@dataclass
class ExportProgress:
    """把事件流折叠成界面要用的状态。UI 只读这里，不自己解析事件。"""

    total: int = 0
    done: int = 0
    stage: str = ""
    assets: dict = field(default_factory=dict)
    result: dict = field(default_factory=dict)
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def percent(self) -> int:
        if self.total <= 0:
            return 0
        return min(100, int(self.done * 100 / self.total))

    def apply(self, event: dict) -> None:
        kind = event.get("event")
        if kind == "assets":
            self.assets = event
        elif kind == "warning":
            message = str(event.get("message", ""))
            if message:
                self.warnings.append(message)
        elif kind == "start":
            self.total = int(event.get("chunks", 0) or 0)
        elif kind == "chunk":
            self.done = int(event.get("index", self.done) or self.done)
        elif kind == "stage":
            self.stage = str(event.get("name", ""))
        elif kind == "done":
            self.result = event
            if self.total:
                self.done = self.total
        elif kind == "error":
            self.error = str(event.get("message", "unknown error"))
