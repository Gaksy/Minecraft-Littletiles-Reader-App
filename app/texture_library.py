"""项目贴图库：按内容哈希存一份贴图，多次导出共用（设计文档 §7.6）。

库每次导出都把 PNG 写进 OBJ 旁边的 `<名字>_textures/`。同一个项目里"换个区块再导
一次"，同一张烘焙结果会再写一遍——按导出次数翻倍增长。所以导出完成后由后端做一步：

1. 把这次的 PNG 按 `sha1` 收进 `<项目>/textures/<前2位>/<sha1>.png`；
   库里已有同哈希 → **直接把这次这份删掉**，不重复占空间；
2. 改写本次 MTL 的 `map_Kd`，指向贴图库（相对 MTL 的相对路径，模型换目录也不断）；
3. 删掉临时的 `<名字>_textures/` 目录。

于是导出目录里只剩 OBJ / MTL / job.json，贴图只存一份。

**孤儿回收**：没有任何记录引用的哈希是"没人要的"，可以安全删掉——记录里存了哈希
清单，将来要重建也只是重跑一次 job。这一层不碰 Qt，能单独测。
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

TEXTURES_DIR = "textures"
CHUNK = 1 << 20


def file_sha1(path: Path | str) -> str:
    digest = hashlib.sha1()
    with Path(path).open("rb") as handle:
        while block := handle.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def library_path(project_dir: Path | str, digest: str) -> Path:
    return Path(project_dir) / TEXTURES_DIR / digest[:2] / ("%s.png" % digest)


def mtl_of(obj_path: Path) -> Path:
    """OBJ 旁边同名的 MTL（库就是这么命名的）。"""
    return obj_path.with_suffix(".mtl")


def staging_dir(obj_path: Path) -> Path:
    """库写贴图的临时目录：`<OBJ 名>_textures/`。"""
    return obj_path.parent / ("%s_textures" % obj_path.stem)


def absorb(project_dir: Path | str, obj_path: Path | str) -> list[str]:
    """把这次产出的贴图收进贴图库，改写 MTL，返回这次的哈希清单（去重后）。"""
    project = Path(project_dir)
    obj = Path(obj_path)
    staging = staging_dir(obj)
    if not staging.is_dir():
        return []

    mtl_path = mtl_of(obj)
    mapping: dict[str, str] = {}       # 原文件名 → MTL 里该写的相对路径
    digests: list[str] = []
    for png in sorted(staging.glob("*.png")):
        digest = file_sha1(png)
        target = library_path(project, digest)
        if target.exists():
            # 库里已经有同样内容的贴图：这次这份是多余的
            png.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(png), str(target))
        if digest not in digests:
            digests.append(digest)
        mapping[png.name] = _relative_for_mtl(target, mtl_path.parent)

    shutil.rmtree(staging, ignore_errors=True)
    if mapping and mtl_path.is_file():
        rewrite_map_kd(mtl_path, mapping)
    return digests


def _relative_for_mtl(target: Path, base: Path) -> str:
    """`map_Kd` 是相对 MTL 解析的，所以这里算相对路径并统一用正斜杠。"""
    try:
        relative = os.path.relpath(target, base)
    except ValueError:      # 不同盘符：只能给绝对路径
        relative = str(target)
    return relative.replace("\\", "/")


def rewrite_map_kd(mtl_path: Path, mapping: dict[str, str]) -> int:
    """改写 MTL 里的 `map_Kd`。返回改了几行。"""
    lines = mtl_path.read_text(encoding="utf-8").splitlines()
    changed = 0
    for index, line in enumerate(lines):
        if not line.startswith("map_Kd "):
            continue
        name = Path(line[len("map_Kd "):].strip().replace("\\", "/")).name
        replacement = mapping.get(name)
        if replacement:
            lines[index] = "map_Kd %s" % replacement
            changed += 1
    if changed:
        mtl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


def referenced(records) -> set[str]:
    """所有记录引用到的贴图哈希。"""
    result: set[str] = set()
    for record in records:
        result.update(record.textures or [])
    return result


def orphans(project_dir: Path | str, records) -> list[Path]:
    """贴图库里没被任何记录引用的文件。"""
    root = Path(project_dir) / TEXTURES_DIR
    if not root.is_dir():
        return []
    used = referenced(records)
    return [
        item
        for item in sorted(root.rglob("*.png"))
        if item.stem not in used
    ]


def prune(project_dir: Path | str, records) -> tuple[int, int]:
    """删掉孤儿贴图，返回（删了几个文件, 释放的字节）。"""
    removed = 0
    freed = 0
    for item in orphans(project_dir, records):
        try:
            freed += item.stat().st_size
            item.unlink()
            removed += 1
        except OSError:
            continue
    # 顺手清掉空目录（两位前缀目录有 256 个，不及时清会显得很杂）
    root = Path(project_dir) / TEXTURES_DIR
    if root.is_dir():
        for folder in sorted(root.iterdir(), reverse=True):
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
    return removed, freed
