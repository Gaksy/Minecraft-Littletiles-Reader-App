"""路径解析：把"数据在哪、库在哪"从写死的仓库内相对路径里解放出来。

历史包袱：这些脚本原先住在库仓库里，默认路径是 `<库仓库>/data/assets/...`。
现在生成端独立成仓库，数据在别处（例如 `../minecraft-littletiles-reader-data/data`），
库在另一个仓库，所以统一在这里解析，并允许用环境变量覆盖：

``LTR_DATA_ROOT``   测试数据根（其下是 regions/ snbt/ matlab/ assets/）
``LTR_LIBRARY``     库仓库路径（benchmark 要找它编出来的 LittleTilesReader）
"""

from __future__ import annotations

import os
from pathlib import Path

# 本文件在 <项目根>/ltgen/paths.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 同级的默认位置（本项目与库、测试数据是兄弟目录）
DEFAULT_DATA_ROOT = PROJECT_ROOT.parent / "minecraft-littletiles-reader-data" / "data"
DEFAULT_LIBRARY_ROOT = PROJECT_ROOT.parent / "minecraft-littletiles-reader"


def _from_env(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else None


def data_root() -> Path:
    """测试数据根：环境变量 → 同级目录 → 仓库内的 `data/`（老布局）。"""
    override = _from_env("LTR_DATA_ROOT")
    if override:
        return override
    if DEFAULT_DATA_ROOT.is_dir():
        return DEFAULT_DATA_ROOT
    return PROJECT_ROOT / "data"


def library_root() -> Path:
    """库仓库根：环境变量 → 同级目录。"""
    override = _from_env("LTR_LIBRARY")
    if override:
        return override
    return DEFAULT_LIBRARY_ROOT


def assets_dir() -> Path:
    return data_root() / "assets"


def regions_dir() -> Path:
    return data_root() / "regions"


def snbt_dir() -> Path:
    return data_root() / "snbt"


def matlab_dir() -> Path:
    return data_root() / "matlab"


def reader_executable() -> Path:
    """库编出来的 CLI。Windows 上是 .exe，其它平台没有后缀。"""
    build_dir = library_root() / "cmake-build-debug"
    for name in ("LittleTilesReader.exe", "LittleTilesReader"):
        candidate = build_dir / name
        if candidate.is_file():
            return candidate
    return build_dir / "LittleTilesReader"


def describe() -> str:
    """把当前解析结果打出来，排查"到底用了哪份数据"用。"""
    return "\n".join(
        [
            "项目根      : %s" % PROJECT_ROOT,
            "数据根      : %s" % data_root(),
            "素材目录    : %s" % assets_dir(),
            "库仓库      : %s" % library_root(),
            "库可执行文件: %s" % reader_executable(),
        ]
    )
