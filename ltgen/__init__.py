"""LittleTiles Reader 生成端：把素材组合成库能直接消费的"素材包"。

职责边界（与库侧 `docs/assets-package.md` 对齐）：

* 生成端（本包）：解 jar、解析 blockstate/models、抠纹理、归一化、去重、
  组合层级（原版 / +资源包 / +模组），产出 **素材包目录**。
* 库：只读素材包，结合网格做 tile 颜色与 tint 的最终调制。

**生成端不烘焙**：tile 颜色只有库合并网格时才知道，合成 PNG 必须留给库。

素材包布局（库只认这些）::

    <dir>/block_textures.tsv   必需：<block(+meta)> + 六面贴图 + 六面 tintindex
    <dir>/textures/<rel>.png   必需：纹理源，只读；<rel> 是不透明相对路径
    <dir>/manifest.json        可选：库只读 format_version
    <dir>/tint.tsv             可选：tint 覆盖表
"""

from __future__ import annotations

__all__ = ["__version__", "FORMAT_VERSION", "FACES"]

__version__ = "0.1.0"

# 与库侧 AssetsPackage::kSupportedFormatVersion 对齐；两边改动要一起走
FORMAT_VERSION = 1

# 与库侧 BlockTextureTable 的列顺序一致
FACES = ("down", "up", "north", "south", "west", "east")
