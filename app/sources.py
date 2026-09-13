"""用户给的"来源"可能是目录，也可能是 zip / rar / jar——统一解析成可用的目录。

为什么要单独一层：用户手上的东西形态各异（存档是 zip、模组是 jar、原版素材是
客户端 jar），而库只认目录。解压、"包内套了几层文件夹"的探测、定位真正的根，
都收在这里，不散落到各个调用点。

两条原则：
  * **只读用户的文件**：解压到我们自己的缓存目录，绝不安置、改写用户的东西。
  * 不假设包内结构：很多包会多套一层文件夹（`INCEPTION texture V1.4/...`），
    所以按 marker 找"最外层含该标记的目录"，而不是硬编码层级。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

# jar 和 zip 是同一个格式；rar 得借外部工具
ZIP_LIKE = (".zip", ".jar")
RAR_LIKE = (".rar",)
ARCHIVE_SUFFIXES = ZIP_LIKE + RAR_LIKE


@dataclass
class Resolved:
    """解析结果。`path` 才是可以直接交给下游的目录。"""

    path: Path
    extracted: bool          # 是否由解压得到（调用方据此决定要不要清理）
    note: str = ""           # 给人看的说明，进日志用


def is_archive(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in ARCHIVE_SUFFIXES


def resolve_source(
    source: Path | str,
    work_dir: Path,
    marker: str | None = None,
) -> Resolved:
    """把来源变成可用目录。

    marker 是"目标根里应该存在的东西"，用来穿过包内多余的层级：
      * 存档        -> "*.mca"
      * 素材包      -> "block_textures.tsv"
      * 原版客户端 jar -> "assets/minecraft"
    找不到 marker 时返回解压出来的顶层目录（让调用方自己报错，别在这儿猜）。
    """
    source = Path(source)
    if source.is_dir():
        root = _find_root(source, marker) if marker else source
        return Resolved(root or source, False, "目录")

    if not source.is_file():
        raise FileNotFoundError("找不到来源：%s" % source)
    if not is_archive(source):
        raise ValueError(
            "不支持的来源类型：%s（只认目录或 %s）"
            % (source.suffix or source.name, "/".join(ARCHIVE_SUFFIXES))
        )

    target = work_dir / source.stem
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)   # 每次重新解，避免残留上次的内容
    target.mkdir(parents=True, exist_ok=True)

    if source.suffix.lower() in ZIP_LIKE:
        _extract_zip(source, target)
        how = "解压 zip/jar"
    else:
        _extract_rar(source, target)
        how = "解压 rar"

    root = _find_root(target, marker) if marker else target
    note = "%s → %s" % (how, _relative_hint(target, root or target))
    return Resolved(root or target, True, note)


def _relative_hint(base: Path, root: Path) -> str:
    try:
        relative = root.relative_to(base)
    except ValueError:
        return str(root)
    return str(relative) if str(relative) != "." else "（包根就是目标根）"


def _find_root(base: Path, marker: str | None, max_depth: int = 4) -> Path | None:
    """广度优先找最外层"含 marker"的目录（穿越多余的嵌套层）。"""
    if marker is None:
        return base
    if _has_marker(base, marker):
        return base
    frontier = [(base, 0)]
    while frontier:
        current, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        try:
            children = sorted(p for p in current.iterdir() if p.is_dir())
        except OSError:
            continue
        for child in children:
            if _has_marker(child, marker):
                return child
            frontier.append((child, depth + 1))
    return None


def _has_marker(directory: Path, marker: str) -> bool:
    if "/" in marker:      # 多级标记，如 assets/minecraft
        return (directory / marker).exists()
    return any(directory.glob(marker))


def _extract_zip(archive: Path, target: Path) -> None:
    """zip/jar 用标准库。自己写而不是 extractall，是为了挡住"zip slip"。"""
    with zipfile.ZipFile(archive) as zf:
        base = target.resolve()
        for member in zf.infolist():
            name = member.filename
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError("压缩包里有越界路径，已中止：%s" % name)
            destination = (target / name).resolve()
            if not str(destination).startswith(str(base)):
                raise ValueError("压缩包里有越界路径，已中止：%s" % name)
        zf.extractall(target)


def _extract_rar(archive: Path, target: Path) -> None:
    """rar 得借外部工具。各平台名字不同，按顺序试。

    Windows 10+ 自带的 `tar` 就是 bsdtar/libarchive，能读 rar；WinRAR 装了就有
    `unrar`。macOS 有 bsdtar，brew 装的是 unar。
    """
    candidates = [
        ["bsdtar", "-xf", str(archive), "-C", str(target)],
        ["tar", "-xf", str(archive), "-C", str(target)],
        ["unar", "-q", "-o", str(target), str(archive)],
        ["unrar", "x", "-y", str(archive), str(target) + os.sep],
    ]
    tried = []
    for command in candidates:
        if shutil.which(command[0]) is None:
            continue
        tried.append(command[0])
        done = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if done.returncode == 0 and any(target.iterdir()):
            return
    raise RuntimeError(
        "解压 rar 失败（试过：%s）。可以手动解压后选那个目录。"
        % (", ".join(tried) or "无可用命令")
    )
