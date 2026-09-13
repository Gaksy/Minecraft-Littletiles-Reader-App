"""把模组 jar 叠加到已有的素材包上。

为什么必须先有素材包：模组只带来**新增方块**的贴图与模型，而"方块 → 六面贴图"
的映射表是以原版为底建起来的，模组条目是往这张表里追加。所以顺序是
**先导入客户端 jar 出素材包，再叠模组**。

一个模组 jar 里可能有多个命名空间（`assets/<ns>/`），只有带 `blockstates/` 的
才是有方块可解析的，其余（纯贴图/音效包）跳过。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .sources import resolve_source

APP_DIR = Path(__file__).resolve().parents[1]


@dataclass
class ModMerge:
    package_dir: Path
    namespaces: list[str] = field(default_factory=list)
    output: str = ""


def find_namespaces(extracted_root: Path) -> list[tuple[Path, str]]:
    """找出解压结果里"有方块可解析"的命名空间。

    返回 [(mod_root, namespace)]，mod_root 指 `<...>/assets/<ns>` 那一层——
    生成端要的正是这个形状（blockstates/ models/block/ textures/blocks/）。
    """
    assets = extracted_root / "assets"
    if not assets.is_dir():
        # jar 根可能多套一层，比如 <外层>/assets
        for candidate in sorted(extracted_root.glob("*/assets")):
            assets = candidate
            break
    found: list[tuple[Path, str]] = []
    if not assets.is_dir():
        return found
    for namespace_dir in sorted(p for p in assets.iterdir() if p.is_dir()):
        if (namespace_dir / "blockstates").is_dir():
            found.append((namespace_dir, namespace_dir.name))
    return found


def merge_mods(
    base_package: Path | str,
    jars: list[Path | str],
    work_dir: Path,
    out_dir: Path,
) -> ModMerge:
    """把若干模组 jar 叠加到 base_package 上，输出到 out_dir。"""
    base_package = Path(base_package)
    if not (base_package / "block_textures.tsv").is_file():
        raise FileNotFoundError(
            "叠加模组需要一个已生成的素材包作底（缺 block_textures.tsv）：%s"
            % base_package
        )

    roots: list[tuple[Path, str]] = []
    for jar in jars:
        resolved = resolve_source(Path(jar), work_dir)
        pairs = find_namespaces(resolved.path)
        if not pairs:
            raise ValueError(
                "这个 jar 里没有可解析的方块（找不到带 blockstates 的命名空间）：%s" % jar
            )
        roots.extend(pairs)

    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    command = [sys.executable, str(APP_DIR / "tools" / "add_mod_textures.py")]
    for root, namespace in roots:
        command += ["--mod-root", str(root), "--namespace", namespace]
    command += ["--base", str(base_package), "--out", str(out_dir)]

    # 这些脚本输出中文，必须显式按 utf-8 解码——默认按系统 locale(cp1252)
    # 会在读取线程里直接抛 UnicodeDecodeError。
    done = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    output = (done.stdout or "") + (done.stderr or "")
    if done.returncode != 0:
        raise RuntimeError("叠加模组失败：\n%s" % output.strip())

    # add_mod_textures 会自己复制原版的 block_ids.tsv（从 --base 拿），
    # 万一底包里没有，就补上随应用带的那份，否则普通方块会变白模。
    bundled = Path(__file__).resolve().parent / "data" / "block_ids.tsv"
    if not (out_dir / "block_ids.tsv").is_file() and bundled.is_file():
        shutil.copyfile(bundled, out_dir / "block_ids.tsv")

    return ModMerge(
        package_dir=out_dir,
        namespaces=[namespace for _, namespace in roots],
        output=output.strip(),
    )
