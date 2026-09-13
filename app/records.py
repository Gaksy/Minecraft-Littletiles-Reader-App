"""导出记录与区块索引：查得出"哪块导过、什么时候、之后存档动过没有"。

两个问题必须一起解决，所以放在一个模块里：

1. **一次导出留下了什么**——时间、类型（存档 / SNBT）、区块列表、产物目录、选项。
   这是历史记录界面和"重建贴图"的依据。
2. **某个区块导过没有**——光靠坐标不行：不同世界的 `(0,0)` 是两个完全不同的
   区块。索引键是 `(世界目录, 维度, x, z)`。

三态判定（设计文档 §7.2）靠"导出当时那几个 `.mca` 的大小 + mtime"：

======== ==================================================  ==========
状态      条件                                               界面表现
======== ==================================================  ==========
未导出    索引里没有这条键                                    灰
已导出    有记录，且 `.mca` 的大小+mtime 与记录里一致          绿 + 时间
可能过期  有记录，但 `.mca` 变了（玩家又玩过这个世界）          黄 + 提示
======== ==================================================  ==========

记录必须**轻**：`index.json` 一整个读进内存也就是几百 KB，查询不必开文件；
`records/<id>.json` 再存一份完整记录，方便人翻、也方便以后加字段。
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

INDEX_NAME = "index.json"
RECORDS_DIR = "records"

# 维度 → 存档里的 region 子目录（与库侧 SaveFolder 同一套规则）
DIMENSION_SUBFOLDERS = {
    "overworld": "region",
    "nether": "DIM-1/region",
    "the_end": "DIM1/region",
}

STATE_MISSING = "missing"
STATE_FRESH = "fresh"
STATE_STALE = "stale"

STATE_LABELS = {
    STATE_MISSING: "未导出",
    STATE_FRESH: "已导出",
    STATE_STALE: "可能已过期",
}


def normalize_world(path: str | Path) -> str:
    """世界目录的规范化路径：大小写与分隔符都要抹平，否则同一个存档算两个世界。"""
    return os.path.normcase(os.path.normpath(str(path)))


def region_file(world: str | Path, dimension: str, x: int, z: int) -> Path:
    """区块 `(x, z)` 落在哪个 `.mca` 里（区域文件按 32×32 区块切）。"""
    sub = DIMENSION_SUBFOLDERS.get(dimension, "region")
    return Path(world) / Path(sub) / ("r.%d.%d.mca" % (x >> 5, z >> 5))


def mca_stamp(path: Path) -> list | None:
    """一个 `.mca` 的"大小 + mtime"；读不到（还没生成 / 被删）返回 None。"""
    try:
        stat = path.stat()
    except OSError:
        return None
    return [int(stat.st_size), int(stat.st_mtime)]


def stamps_for(
    world: str | Path, dimension: str, chunks: list[list[int]] | list[tuple[int, int]]
) -> dict:
    """导出时记下涉及到的每个 `.mca` 的大小与 mtime。键是文件名，便于日后比对。"""
    stamps: dict = {}
    for x, z in chunks:
        path = region_file(world, dimension, int(x), int(z))
        if path.name in stamps:
            continue
        stamp = mca_stamp(path)
        if stamp is not None:
            stamps[path.name] = stamp
    return stamps


@dataclass
class ExportRecord:
    """一次导出的完整记录。路径字段一律**相对项目目录**，项目搬走也不会失效。"""

    id: str                      # 产物目录名，项目内唯一
    kind: str                    # "region" | "snbt"
    name: str                    # 这次导出的名字（区块范围 / 结构名）
    created_at: str
    output_dir: str              # 相对项目目录
    obj: str = ""                # 相对项目目录（OBJ 文件）
    world: str = ""              # region：存档根目录；snbt：结构文件路径
    dimension: str = ""
    chunks: list = field(default_factory=list)          # [[x, z], ...]
    options: dict = field(default_factory=dict)
    mca_stamps: dict = field(default_factory=dict)      # "r.x.z.mca" -> [size, mtime]
    job: str = ""                # 相对项目目录（这次用的 job.json）
    seconds: float = 0.0
    faces: int = 0
    textures: list = field(default_factory=list)        # 贴图哈希清单（M4 用）

    @property
    def kind_label(self) -> str:
        return "存档" if self.kind == "region" else "SNBT"

    def chunk_text(self) -> str:
        """区块列表的紧凑写法：单块 `c1_2`，多块给范围和个数。"""
        if not self.chunks:
            return "—"
        if len(self.chunks) == 1:
            return "c%d_%d" % (self.chunks[0][0], self.chunks[0][1])
        xs = [int(c[0]) for c in self.chunks]
        zs = [int(c[1]) for c in self.chunks]
        return "x %d…%d / z %d…%d（%d 块）" % (
            min(xs), max(xs), min(zs), max(zs), len(self.chunks)
        )

    def size_bytes(self, project_dir: Path) -> int:
        from .storage import dir_size

        return dir_size(Path(project_dir) / self.output_dir)


class RecordStore:
    """`<项目>/records/` 的读写。索引是权威，单条记录只是副本。"""

    def __init__(self, project_dir: Path | str) -> None:
        self.project_dir = Path(project_dir)
        self.records_dir = self.project_dir / RECORDS_DIR
        self.index_path = self.records_dir / INDEX_NAME
        self._records: list[ExportRecord] = []
        self.load()

    # ---- 读写 ------------------------------------------------------------

    def load(self) -> list[ExportRecord]:
        self._records = []
        if not self.index_path.is_file():
            return self._records
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._records
        known = set(ExportRecord.__dataclass_fields__)
        for item in data.get("records", []):
            if isinstance(item, dict):
                self._records.append(
                    ExportRecord(**{k: v for k, v in item.items() if k in known})
                )
        return self._records

    def save(self) -> Path:
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(
                {"version": 1, "records": [asdict(r) for r in self._records]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return self.index_path

    # ---- 查询 ------------------------------------------------------------

    @property
    def records(self) -> list[ExportRecord]:
        """按时间倒序（新的在前）——界面直接按这个顺序排。"""
        return sorted(self._records, key=lambda r: r.created_at, reverse=True)

    def by_kind(self, kind: str) -> list[ExportRecord]:
        return [r for r in self.records if r.kind == kind]

    def by_id(self, record_id: str) -> ExportRecord | None:
        return next((r for r in self._records if r.id == record_id), None)

    def chunk_records(
        self, world: str | Path, dimension: str, x: int, z: int
    ) -> list[ExportRecord]:
        """导过这个区块的全部记录（新的在前）。"""
        key = normalize_world(world)
        return [
            r
            for r in self.records
            if r.kind == "region"
            and normalize_world(r.world) == key
            and r.dimension == dimension
            and any(int(c[0]) == x and int(c[1]) == z for c in r.chunks)
        ]

    def chunk_state(
        self, world: str | Path, dimension: str, x: int, z: int
    ) -> tuple[str, ExportRecord | None]:
        """三态：未导出 / 已导出 / 可能已过期。返回状态与最近那条记录。"""
        found = self.chunk_records(world, dimension, x, z)
        if not found:
            return STATE_MISSING, None
        latest = found[0]
        name = region_file(world, dimension, x, z).name
        recorded = latest.mca_stamps.get(name)
        current = mca_stamp(region_file(world, dimension, x, z))
        if recorded is None or current is None or list(recorded) != list(current):
            return STATE_STALE, latest
        return STATE_FRESH, latest

    def exported_chunks(self, world: str | Path, dimension: str) -> dict:
        """`(x, z) -> 最近一条记录`：画区块网格时一次取完，别一格一格查。"""
        key = normalize_world(world)
        result: dict = {}
        for record in self.records:      # 已是新的在前，先写的胜
            if record.kind != "region" or normalize_world(record.world) != key:
                continue
            if record.dimension != dimension:
                continue
            for x, z in record.chunks:
                result.setdefault((int(x), int(z)), record)
        return result

    # ---- 修改 ------------------------------------------------------------

    def add(self, record: ExportRecord) -> ExportRecord:
        self._records = [r for r in self._records if r.id != record.id]
        self._records.append(record)
        self.records_dir.mkdir(parents=True, exist_ok=True)
        (self.records_dir / ("%s.json" % record.id)).write_text(
            json.dumps(asdict(record), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.save()
        return record

    def remove(self, record_ids: list[str]) -> int:
        """删记录本身。产物目录要不要删由调用方决定（见 §7.7：默认不自动删）。"""
        wanted = set(record_ids)
        before = len(self._records)
        self._records = [r for r in self._records if r.id not in wanted]
        for record_id in wanted:
            (self.records_dir / ("%s.json" % record_id)).unlink(missing_ok=True)
        self.save()
        return before - len(self._records)

    def remove_with_outputs(self, record_ids: list[str]) -> int:
        """连产物目录一起删（用户明确选了"连产物一起删"时才走这里）。"""
        removed = 0
        for record_id in record_ids:
            record = self.by_id(record_id)
            if record is not None:
                target = self.project_dir / record.output_dir
                # 产物目录必须确实在项目目录里——记录是可以被手改成 "../.." 的
                if is_inside(target, self.project_dir) and target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                removed += 1
        self.remove(record_ids)
        return removed


def is_inside(target: Path, root: Path) -> bool:
    """target 是不是 root 里的东西（防止记录被改坏之后删到项目目录外面）。"""
    try:
        target.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True
