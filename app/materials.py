"""看一眼一个素材来源里到底有什么（方块数 / 贴图数 / 缺哪些贴图）。

用途：材质管理里"选中某个导入物"时给出内容摘要，避免用户只能看到一个名字。
导入物解压后是**资源包布局**（`assets/<命名空间>/blockstates|models|textures`），
这里就按这个布局数：

* 方块数 = `blockstates/*.json` 的数量（一个 blockstate 就是一个可渲染的方块）；
* 模型数 = `models/block/*.json`；
* 贴图数 = `textures/**/*.png`；
* 缺失   = 模型里 `textures` 引用了、但磁盘上没有的贴图（按命名空间回退找）。

只读、不落盘，也不做完整的 blockstate→模型 解析（那是生成端
`tools/resolve_block_textures.py` 的活）——这里要的是"够快、看得懂"。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# 缺失贴图最多列这么多条（界面上一行放不下太多）
MAX_MISSING_SHOWN = 6


@dataclass(frozen=True)
class SourceSummary:
    """一个素材来源的内容摘要。"""

    namespaces: tuple[str, ...] = ()
    blocks: int = 0
    models: int = 0
    textures: int = 0
    missing: tuple[str, ...] = field(default_factory=tuple)

    @property
    def empty(self) -> bool:
        return not self.namespaces

    def render(self) -> str:
        """给界面用的一行（或两行）文字。"""

        if self.empty:
            return "这里没有 assets/ —— 不是资源包或模组，导入后没法参与组合。"
        parts = [
            "命名空间 %s" % "、".join(self.namespaces),
            "方块 %d" % self.blocks,
            "模型 %d" % self.models,
            "贴图 %d" % self.textures,
        ]
        if self.missing:
            shown = "、".join(self.missing[:MAX_MISSING_SHOWN])
            if len(self.missing) > MAX_MISSING_SHOWN:
                shown += " 等 %d 张" % len(self.missing)
            parts.append("缺失 %d（%s）" % (len(self.missing), shown))
        else:
            parts.append("缺失 0")
        return "　".join(parts)


def _load_lenient(text: str) -> dict:
    """读模型 JSON；坏文件尽量救（真实模组素材里见过多余的 `}` 和 `"x"= 90`）。"""

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.JSONDecoder().raw_decode(text.lstrip())[0]
    except json.JSONDecodeError:
        pass
    salvaged: dict = {}
    block = re.search(r'"textures"\s*:\s*\{(.*?)\}', text, re.S)
    if block:
        textures = dict(re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', block.group(1)))
        if textures:
            salvaged["textures"] = textures
    return salvaged


def namespaces_in(root: Path) -> tuple[str, ...]:
    """资源包布局里的命名空间（`assets/` 下的一级目录）。"""

    assets = root / "assets"
    if not assets.is_dir():
        return ()
    return tuple(
        sorted(
            entry.name
            for entry in assets.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        )
    )


def inspect_source(root: Path) -> SourceSummary:
    """数一数这个来源里有什么。root 是解压后的包根（含 `assets/`）。"""

    root = Path(root)
    namespaces = namespaces_in(root)
    if not namespaces:
        return SourceSummary()

    blocks = models = textures = 0
    missing: list[str] = []
    seen_missing: set[str] = set()

    for namespace in namespaces:
        base = root / "assets" / namespace
        blockstates = base / "blockstates"
        if blockstates.is_dir():
            blocks += sum(1 for _ in blockstates.glob("*.json"))
        model_dir = base / "models" / "block"
        if model_dir.is_dir():
            for path in sorted(model_dir.glob("*.json")):
                models += 1
                try:
                    data = _load_lenient(path.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
                for reference in (data.get("textures") or {}).values():
                    if not isinstance(reference, str) or reference.startswith("#"):
                        continue
                    owner, _, rel = reference.partition(":")
                    if not rel:
                        owner, rel = namespace, owner
                    if (root / "assets" / owner / "textures" / (rel + ".png")).is_file():
                        continue
                    key = "%s:%s" % (owner, rel)
                    if key not in seen_missing:
                        seen_missing.add(key)
                        missing.append(key)
        texture_dir = base / "textures"
        if texture_dir.is_dir():
            textures += sum(1 for _ in texture_dir.rglob("*.png"))

    return SourceSummary(
        namespaces=namespaces,
        blocks=blocks,
        models=models,
        textures=textures,
        missing=tuple(missing),
    )
