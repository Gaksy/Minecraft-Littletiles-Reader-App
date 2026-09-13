"""从用户自己的客户端 jar 生成素材包。

这条路是"用户第一次用"最需要的一步：他手上只有游戏和存档，没有我们的素材包格式。
所以让他指一个 `1.12.2.jar`，我们解压 → 整理 → 得到一个能直接用的素材包。

**素材来自用户自己的游戏，我们只读不转存、不重新分发。** 唯一随应用带的是
`app/data/block_ids.tsv`——那是"数字 ID → 方块名"的对照表，由社区数据集
（PrismarineJS/minecraft-data）生成，属于事实性数据，不是 Mojang 的贴图资源。
没有它，存档里的普通方块（存的是数字 ID）就查不到名字，只能出白模。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .sources import resolve_source

APP_DIR = Path(__file__).resolve().parents[1]
BUNDLED_BLOCK_IDS = Path(__file__).resolve().parent / "data" / "block_ids.tsv"

# 原版素材在客户端 jar 里的位置
VANILLA_MARKER = "assets/minecraft"


@dataclass
class PackageBuild:
    package_dir: Path
    source_note: str
    output: str          # 生成端脚本的输出，进日志


def build_package_from_vanilla(
    source: Path | str,
    work_dir: Path,
    out_dir: Path,
) -> PackageBuild:
    """客户端 jar（或已解压的原版目录）→ 素材包目录。

    实际整理工作交给生成端的 build_assets_from_pack.py：它负责解析
    blockstates/models 生成映射表、只挑被引用到的贴图复制过去。
    这里只做三件事——解析来源、调它、补上 block_ids.tsv。
    """
    source = Path(source)
    # jar 的包根（含 assets/ 的那层）要留给生成端认"资源包布局"，
    # 而 --vanilla 要的是里面的 assets/minecraft。
    resolved = resolve_source(source, work_dir, marker=VANILLA_MARKER)
    minecraft_root = resolved.path / VANILLA_MARKER
    if not minecraft_root.is_dir():
        raise FileNotFoundError(
            "这个来源里没有 %s，看起来不是 Minecraft 客户端 jar：%s"
            % (VANILLA_MARKER, source)
        )
    pack_root = resolved.path   # 含 assets/ 的那层，生成端按它找包前缀

    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    script = APP_DIR / "tools" / "build_assets_from_pack.py"
    command = [
        sys.executable,
        str(script),
        "--vanilla", str(minecraft_root),
        "--pack", str(pack_root),
        "--out", str(out_dir),
    ]
    done = subprocess.run(command, capture_output=True, text=True)
    output = (done.stdout or "") + (done.stderr or "")
    if done.returncode != 0:
        raise RuntimeError("生成素材包失败：\n%s" % output.strip())

    # 生成端拿到的是"光秃秃的原版素材"，里面没有 block_ids.tsv（那是我们自己的文件），
    # 所以在这里补上随应用带的那份；没有它，普通的实心方块只能出白模。
    if not (out_dir / "block_ids.tsv").is_file():
        if not BUNDLED_BLOCK_IDS.is_file():
            raise FileNotFoundError("应用自带的 block_ids.tsv 不见了：%s" % BUNDLED_BLOCK_IDS)
        shutil.copyfile(BUNDLED_BLOCK_IDS, out_dir / "block_ids.tsv")

    return PackageBuild(
        package_dir=out_dir,
        source_note=resolved.note or "目录",
        output=output.strip(),
    )
