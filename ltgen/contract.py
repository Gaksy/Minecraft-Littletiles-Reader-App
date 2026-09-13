"""素材包契约的读写：映射表、manifest、tint 表。

这里的解析规则必须与库侧一致——两边不一致的后果是"生成端认为没问题，
库读出来却是另一回事"。库侧对应实现：

* 映射表   `Galib/.../TextureSupport/BlockTextureTable.cpp` 的 `LoadFromTsv`
* manifest `Galib/.../TextureSupport/AssetsPackage.cpp` 的 `ProbeFormatVersion`
* tint 表  `Galib/.../TextureSupport/AssetsPackage.cpp` 的 `LoadTintTable`
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import FACES, FORMAT_VERSION

TABLE_NAME = "block_textures.tsv"
TEXTURES_DIR = "textures"
MANIFEST_NAME = "manifest.json"
TINT_NAME = "tint.tsv"

# 库侧约定：贴图列写成 "-"（或空）表示该面无贴图；tint 列为 -1 表示不染色
NO_TEXTURE = "-"
NO_TINT = -1

# 1.12 里"带 meta 的方块"在表里是 <block>:<meta>；库查表时会依次尝试
# 原名 -> 去掉 meta -> 通配 "*"。tint 表的键用同一套规则。
WILDCARD_KEY = "*"


class ContractError(Exception):
    """素材包不满足契约（generating/lint 共用）。"""


@dataclass
class BlockEntry:
    """表里的一行：一个方块（可带 meta）的六面贴图与 tintindex。"""

    key: str
    paths: list[str]  # 6 个，'' 表示该面无贴图
    tints: list[int]  # 6 个，-1 表示不染色
    line_no: int

    def texture_paths(self) -> list[str]:
        return [p for p in self.paths if p]

    def tint_indexes(self) -> list[int]:
        return [t for t in self.tints if t >= 0]


@dataclass
class TextureTable:
    """解析结果 + 解析过程中的问题（lint 要用）。"""

    entries: dict[str, BlockEntry] = field(default_factory=dict)
    malformed: list[tuple[int, str]] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    commented_lines: int = 0

    def texture_paths(self) -> list[str]:
        """表里引用到的唯一贴图路径（保持首次出现顺序，输出稳定）。"""
        seen: dict[str, None] = {}
        for entry in self.entries.values():
            for path in entry.texture_paths():
                seen.setdefault(path, None)
        return list(seen)

    def tint_pairs(self) -> list[tuple[str, int]]:
        """(方块键, tintindex) 去重后的列表。"""
        seen: dict[tuple[str, int], None] = {}
        for entry in self.entries.values():
            for index in entry.tint_indexes():
                seen.setdefault((entry.key, index), None)
        return list(seen)


def parse_texture_table(path: Path) -> TextureTable:
    """读 `block_textures.tsv`。

    列：``<block(+meta)> <6 面贴图> [<6 面 tintindex>]``，制表符分隔，``#`` 开头是注释。
    tint 列整体缺失时全部按不染色处理（与库一致的向后兼容）。
    """
    table = TextureTable()
    if not path.is_file():
        raise ContractError("找不到映射表：%s" % path)

    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            line = raw.rstrip("\n").rstrip("\r")
            if not line.strip() or line.lstrip().startswith("#"):
                table.commented_lines += 1
                continue

            fields = line.split("\t")
            if len(fields) < 1 + len(FACES):
                table.malformed.append(
                    (line_no, "只有 %d 列，至少需要 %d 列" % (len(fields), 1 + len(FACES)))
                )
                continue

            key = fields[0].strip()
            if not key:
                table.malformed.append((line_no, "方块键为空"))
                continue

            paths = []
            for index in range(len(FACES)):
                value = fields[1 + index].strip()
                paths.append("" if value in ("", NO_TEXTURE) else value)

            tints = [NO_TINT] * len(FACES)
            for index in range(len(FACES)):
                column = 1 + len(FACES) + index
                if column >= len(fields):
                    break
                value = fields[column].strip()
                if not value:
                    continue
                try:
                    tints[index] = int(value)
                except ValueError:
                    table.malformed.append(
                        (line_no, "第 %d 个 tintindex 不是整数：%r" % (index + 1, value))
                    )

            if key in table.entries:
                table.duplicates.append(key)
            table.entries[key] = BlockEntry(key, paths, tints, line_no)

    return table


def write_texture_table(path: Path, table: TextureTable) -> None:
    """把映射表按契约格式写回（生成端产出用）。"""
    columns = ["block(+meta)"] + list(FACES) + ["%s_tint" % face for face in FACES]
    lines = ["#" + "\t".join(columns)]
    for entry in table.entries.values():
        paths = [p if p else NO_TEXTURE for p in entry.paths]
        tints = [str(t) for t in entry.tints]
        lines.append("\t".join([entry.key] + paths + tints))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_manifest(package_dir: Path) -> dict:
    """读 manifest.json；不存在返回空 dict（它是可选的）。"""
    path = package_dir / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ContractError("manifest.json 不是合法 JSON：%s" % error) from error


def write_manifest(package_dir: Path, manifest: dict) -> Path:
    """写 manifest.json，固定缩进与键顺序，便于 diff。"""
    version = manifest.get("format_version")
    if version != FORMAT_VERSION:
        raise ContractError(
            "format_version 必须是 %d，收到 %r" % (FORMAT_VERSION, version)
        )
    path = package_dir / MANIFEST_NAME
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def resolve_texture(package_dir: Path, rel: str) -> Path:
    """``<package>/textures/<rel>.png``（与库的 ResolveTexture 一致）。"""
    return package_dir / TEXTURES_DIR / (rel + ".png")


def check_format_version(version: object, supported: int = FORMAT_VERSION) -> list[str]:
    """返回 format_version 相关的问题列表（空表示没问题）。"""
    if version is None:
        return []
    if not isinstance(version, int):
        return ["format_version 不是整数：%r" % (version,)]
    if version > supported:
        return [
            "format_version %d 比生成端认识的 %d 新，库会拒绝打开"
            % (version, supported)
        ]
    return []
