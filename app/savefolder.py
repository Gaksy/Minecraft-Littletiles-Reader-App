"""存档根目录的检查：用户选完路径，立刻告诉他"这个目录对不对"。

踩过的坑：状态栏显示"素材包已配置"、导出却一个区块都没有——因为选错了目录。
选错有两种常见形态，都要当场说清楚：

* 选到了 `region/` 里面（少了一层：这里没有 level.dat，也没有 region/region/）
* 选到了 `saves/` 这一层（一个存档都没有，但有子目录藏着存档）

这一层不碰 Qt，只给结论与文字，颜色由界面决定。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .records import DIMENSION_SUBFOLDERS, region_file


@dataclass
class SaveInspection:
    ok: bool = False                 # 能用来导出吗
    level_dat: bool = False
    mca_count: int = 0
    message: str = ""
    hint: str = ""                   # 认出来"你大概想选哪个"时给的补充
    candidates: list = field(default_factory=list)   # 附近看起来像存档的目录


def inspect(root: str | Path, dimension: str = "overworld") -> SaveInspection:
    path = Path(str(root).strip()) if str(root).strip() else None
    if path is None:
        return SaveInspection(message="还没有选择存档目录。")
    if not path.is_dir():
        return SaveInspection(message="这个路径不存在，或者不是目录。")

    sub = DIMENSION_SUBFOLDERS.get(dimension, "region")
    region_dir = path / Path(sub)
    mca_count = len(list(region_dir.glob("*.mca"))) if region_dir.is_dir() else 0
    level_dat = (path / "level.dat").is_file()

    result = SaveInspection(level_dat=level_dat, mca_count=mca_count)
    if mca_count > 0:
        result.ok = True
        result.message = "找到 %s/（%d 个 .mca）%s" % (
            sub, mca_count, "，含 level.dat" if level_dat else ""
        )
        return result

    # 选进了 region/ 里面：往上退一层就是存档根目录
    if path.name in ("region", "DIM-1", "DIM1") and any(path.glob("*.mca")):
        result.message = "这里像是 %s/ 目录本身，不是存档根目录。" % path.name
        result.hint = "往上退一层选：%s" % path.parent
        return result

    # 选到了 saves/ 这一层：找找哪个子目录像存档
    candidates = [
        child
        for child in sorted(path.iterdir())
        if child.is_dir()
        and (
            (child / "level.dat").is_file()
            or (child / Path(sub)).is_dir()
        )
    ]
    result.candidates = candidates
    if candidates:
        result.message = "这个目录里没有直接的存档，但里面有 %d 个像存档的文件夹。" % len(
            candidates
        )
        result.hint = "大概想选的是：%s" % "、".join(c.name for c in candidates[:3])
        return result

    if level_dat:
        result.message = "有 level.dat，但 %s/ 里没有 .mca 文件。" % sub
        result.hint = "这个存档可能还没生成过地图，或者维度选错了。"
        return result

    result.message = "这里既没有 level.dat，也没有 %s/。" % sub
    result.hint = "存档根目录是含 level.dat 与 region/ 的那一层。"
    return result


def region_file_count(root: str | Path, dimension: str = "overworld") -> int:
    """某个维度下有多少个 .mca（给界面显示用）。"""
    sub = DIMENSION_SUBFOLDERS.get(dimension, "region")
    folder = Path(root) / Path(sub)
    return len(list(folder.glob("*.mca"))) if folder.is_dir() else 0


__all__ = ["SaveInspection", "inspect", "region_file_count", "region_file"]
