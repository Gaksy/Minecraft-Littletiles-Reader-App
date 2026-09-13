"""生成 `manifest.json`：把"这份素材包是怎么来的"写下来。

库只读 `format_version`（读到不认识的版本就拒绝打开），其余字段是给人和生成端
回溯用的——层序在生成端合并时就已经落地，库没有"按层叠加"这个动作。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import FORMAT_VERSION
from .contract import (
    MANIFEST_NAME,
    ContractError,
    load_manifest,
    write_manifest,
)

# 纹理引用是不透明相对路径（库不强制 <namespace>/ 前缀），这里只记录约定
DEFAULT_TEXTURE_LAYOUT = "<相对路径>.png"


@dataclass
class Pack:
    """一个素材来源：id + 版本 + 它贡献的命名空间。"""

    id: str
    version: str = ""
    namespaces: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        data = {"id": self.id}
        if self.version:
            data["version"] = self.version
        if self.namespaces:
            data["namespaces"] = list(self.namespaces)
        return data

    @staticmethod
    def parse(spec: str) -> "Pack":
        """解析 ``id[@version][:ns1,ns2]``，例如 ``vanilla@1.12.2:minecraft``。"""
        body, _, namespaces = spec.partition(":")
        pack_id, _, version = body.partition("@")
        pack_id = pack_id.strip()
        if not pack_id:
            raise ContractError("--pack 的 id 不能为空：%r" % spec)
        return Pack(
            id=pack_id,
            version=version.strip(),
            namespaces=tuple(n.strip() for n in namespaces.split(",") if n.strip()),
        )


def build_manifest(
    layers: list[str],
    packs: list[Pack],
    note: str = "",
    texture_layout: str = DEFAULT_TEXTURE_LAYOUT,
    format_version: int = FORMAT_VERSION,
) -> dict:
    """按契约字段拼一份 manifest。"""
    if not layers:
        raise ContractError("至少要有一层（--layer）")
    if not packs:
        raise ContractError("至少要有一个来源（--pack）")
    manifest = {
        "format_version": format_version,
        "texture_layout": texture_layout,
        "layers": list(layers),
        "packs": [pack.as_dict() for pack in packs],
    }
    if note:
        manifest["note"] = note
    return manifest


def write_package_manifest(
    package_dir: Path, manifest: dict, merge_existing: bool = True
) -> Path:
    """写 `<package_dir>/manifest.json`。

    `merge_existing=True` 时保留已有 manifest 里本次没提供的字段（例如手写的
    `note`），避免生成端一次重跑把人工补充的信息抹掉。
    """
    package_dir = Path(package_dir)
    if not package_dir.is_dir():
        raise ContractError("素材包目录不存在：%s" % package_dir)

    final = dict(manifest)
    if merge_existing:
        existing = load_manifest(package_dir)
        for key, value in existing.items():
            if key not in final:
                final[key] = value
    return write_manifest(package_dir, final)


def describe(package_dir: Path) -> str:
    """给人看的一行摘要（CLI 用）。"""
    manifest = load_manifest(Path(package_dir))
    if not manifest:
        return "%s：没有 %s" % (package_dir, MANIFEST_NAME)
    packs = manifest.get("packs") or []
    names = []
    for pack in packs:
        if isinstance(pack, dict):
            version = pack.get("version")
            names.append(
                "%s%s" % (pack.get("id", "?"), "@%s" % version if version else "")
            )
        else:
            names.append(str(pack))
    return "%s：format_version=%s，layers=%s，packs=%s" % (
        package_dir,
        manifest.get("format_version"),
        " -> ".join(manifest.get("layers") or []) or "(未写)",
        ", ".join(names) or "(未写)",
    )
