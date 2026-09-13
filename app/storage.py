"""项目体积统计：一条按颜色分段的容量条要用的数据（设计文档 §7.8）。

只有**一条**条：各段宽度 = 该类占比。类别固定为下面这几种，颜色也在这里定死——
写成一套语义色，浅色与深色背景下都能区分（别在控件里各写各的）。

这一层不碰 Qt，所以能单独测；界面只负责画。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 类别键 → (中文标签, 颜色)。颜色取自 Tableau 10：饱和度适中，明暗背景都分得开。
CATEGORY_SPECS: list[tuple[str, str, str]] = [
    ("package", "素材组合结果", "#4e79a7"),
    ("outputs", "导出模型 (OBJ/MTL)", "#f28e2b"),
    ("textures", "贴图库", "#edc948"),
    ("backups", "存档备份", "#e15759"),
    ("packs", "素材包副本", "#76b7b2"),
    ("mods", "模组副本", "#59a14f"),
    ("records", "记录与输入副本", "#b07aa1"),
]

# 每条记录/每个类别对应项目里的哪些路径（相对项目目录）
CATEGORY_PATHS: dict[str, tuple[str, ...]] = {
    "package": ("package",),
    "outputs": ("outputs",),
    "textures": ("textures",),
    "backups": ("inputs/saves",),
    "packs": ("packs",),
    "mods": ("mods",),
    "records": ("records", "inputs/snbt"),
}


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    color: str      # "#rrggbb"
    size: int       # 字节

    @property
    def is_empty(self) -> bool:
        return self.size <= 0


def dir_size(path: Path | str) -> int:
    """目录（或单个文件）占多少字节；读不动的东西按 0 算，不因为一个坏文件崩掉。"""
    target = Path(path)
    try:
        if target.is_file():
            return target.stat().st_size
        if not target.is_dir():
            return 0
    except OSError:
        return 0
    total = 0
    for item in target.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def categories(project_dir: Path | str, with_empty: bool = False) -> list[Category]:
    """按类别统计；默认只给非空的（空类别画在条上就是 0 宽度，还占图例一行）。"""
    root = Path(project_dir)
    result: list[Category] = []
    for key, label, color in CATEGORY_SPECS:
        size = sum(dir_size(root / child) for child in CATEGORY_PATHS.get(key, ()))
        result.append(Category(key, label, color, size))
    if not with_empty:
        result = [c for c in result if not c.is_empty]
    # 图例按大小降序；完全一样大时按定义顺序，别让顺序随机跳
    order = {key: index for index, (key, _, _) in enumerate(CATEGORY_SPECS)}
    return sorted(result, key=lambda c: (-c.size, order[c.key]))


def total_size(project_dir: Path | str) -> int:
    return sum(c.size for c in categories(project_dir, with_empty=True))


def human_size(size: int) -> str:
    """人看的单位：1024 进制，保留一位小数（和文件管理器里看到的一致）。"""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return "%d B" % int(value)
            return "%.1f %s" % (value, unit)
        value /= 1024
    return "%d B" % size


def percent(size: int, total: int) -> float:
    return (size / total * 100.0) if total > 0 else 0.0
