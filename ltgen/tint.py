"""生成 `tint.tsv`：把"哪个方块用哪种染色"从库里搬到素材包里。

背景：带 tintindex 的面在游戏里要乘上生物群系颜色（草方块顶面、树叶…）。
LittleTiles 的存档**不记录每个 tile 的生物群系**，所以只能用固定默认色，
当前这份默认色硬编码在库里（`AssetsPackage.cpp` 的
`kDefaultGrassColor` / `kDefaultFoliageColor`）。

本模块把这些默认值写成素材包里的 `tint.tsv`。写出来之后：

* 配色成了**素材知识**，换包/换风格改这一个文件即可，不用改库、不用重编译；
* 规则值与库内默认完全一致时，导出结果**逐字节不变**（可用库跑一遍验证）。

格式（与库的 `LoadTintTable` 一致）::

    <键>\t<tintindex>\t<ARGB 十六进制>
    *      0           0xFF91BD59     # 通配：所有方块的 tintindex 0 用草色
    minecraft:leaves  0  0xFF79C05A   # 精确方块覆盖通配

查表顺序：精确键 → 去掉 meta 的键 → `*`。所以对 `minecraft:leaves:1` 写
`minecraft:leaves` 一条就能覆盖所有 meta。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .contract import (
    TABLE_NAME,
    TINT_NAME,
    WILDCARD_KEY,
    ContractError,
    parse_texture_table,
)

# 与库内默认色一致（改这里之前先想清楚：库在没有 tint.tsv 时仍用它的默认值）
DEFAULT_GRASS_ARGB = 0xFF91BD59
DEFAULT_FOLIAGE_ARGB = 0xFF79C05A

# 库的 DefaultTintForBlock 里按"方块名"判定树叶族的这几个名字
FOLIAGE_BLOCKS = ("leaves", "leaves2", "vine", "vine_1")

# 方块键去掉命名空间与 meta 之后的名字（与库的 BlockNameOf 同规则）
def block_name_of(key: str) -> str:
    without_namespace = key.split(":", 1)[1] if ":" in key else key
    return without_namespace.split(":", 1)[0]


def strip_meta(key: str) -> str:
    """`minecraft:leaves:1` -> `minecraft:leaves`（与库的 StripBlockMeta 同规则）。"""
    parts = key.split(":")
    if len(parts) <= 2:
        return key
    return ":".join(parts[:2])


@dataclass
class TintRule:
    key: str
    tint_index: int
    argb: int

    def as_line(self, comment: str = "") -> str:
        line = "%s\t%d\t0x%08X" % (self.key, self.tint_index, self.argb)
        return "%s\t# %s" % (line, comment) if comment else line


def plan_rules(
    package_dir: Path,
    grass_argb: int = DEFAULT_GRASS_ARGB,
    foliage_argb: int = DEFAULT_FOLIAGE_ARGB,
) -> list[TintRule]:
    """读素材包的映射表，算出"能复现库内默认行为"的规则集。

    产出两条：通配草色（覆盖所有出现过的 tintindex），以及树叶族的逐方块覆盖。
    这样即使库里那套硬编码被删掉，行为也不变。
    """
    package_dir = Path(package_dir)
    table = parse_texture_table(package_dir / TABLE_NAME)
    if not table.entries:
        raise ContractError("%s 里没有任何方块条目" % (package_dir / TABLE_NAME))

    # 1) 出现过的 tintindex -> 通配草色
    indexes: dict[int, None] = {}
    # 2) 树叶族方块 -> 需要单独覆盖的 (键, tintindex)
    foliage: dict[tuple[str, int], None] = {}

    for entry in table.entries.values():
        name = block_name_of(entry.key)
        is_foliage = name in FOLIAGE_BLOCKS
        covered: set[str] = set()
        for index in entry.tint_indexes():
            indexes.setdefault(index, None)
            if is_foliage:
                # 用去掉 meta 的键，一条覆盖该方块的所有 meta
                key = strip_meta(entry.key)
                if key in covered:
                    continue
                covered.add(key)
                foliage.setdefault((key, index), None)

    rules = [TintRule(WILDCARD_KEY, index, grass_argb) for index in sorted(indexes)]
    rules.extend(
        TintRule(key, index, foliage_argb)
        for key, index in sorted(foliage)
    )
    # 库按"精确 -> 去 meta -> 通配"查找，所以文件顺序不影响结果；
    # 这里按"通配在前、具体覆盖在后"排，读起来更像"先默认再覆盖"。
    rules.sort(key=lambda rule: (rule.key != WILDCARD_KEY, rule.key))
    return rules


def render(rules: list[TintRule], package_name: str = "") -> str:
    """把规则渲染成 tint.tsv 文本（含说明性注释头）。"""
    header = [
        "# tint 覆盖表：<键>\\t<tintindex>\\t<ARGB 十六进制>",
        "# 查表顺序：精确键 -> 去掉 meta 的键 -> *",
        "# 本文件由生成端 ltgen tint 产出；删掉它库会回落到内置默认色。",
    ]
    if package_name:
        header.insert(3, "# 素材包：%s" % package_name)
    lines = []
    for rule in rules:
        if rule.argb == DEFAULT_GRASS_ARGB:
            comment = "默认草色"
        elif rule.argb == DEFAULT_FOLIAGE_ARGB:
            comment = "树叶色"
        else:
            comment = ""
        lines.append(rule.as_line(comment))
    return "\n".join(header + lines) + "\n"


def write_tint_table(
    package_dir: Path,
    grass_argb: int = DEFAULT_GRASS_ARGB,
    foliage_argb: int = DEFAULT_FOLIAGE_ARGB,
) -> tuple[Path, list[TintRule]]:
    """生成并写出 `<package_dir>/tint.tsv`，返回路径与规则列表。"""
    package_dir = Path(package_dir)
    rules = plan_rules(package_dir, grass_argb, foliage_argb)
    path = package_dir / TINT_NAME
    path.write_text(render(rules, package_dir.name), encoding="utf-8")
    return path, rules
