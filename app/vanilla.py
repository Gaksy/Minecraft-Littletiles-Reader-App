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


def detect_kind(root: Path) -> str:
    """看看解出来的目录是什么东西，好告诉用户下一步能不能用。

    目前只有 `vanilla` 这条路是打通了的（从客户端 jar 直接生成素材包）；
    资源包与模组都要先有原版底子再合并，属于下一步。
    """
    if (root / "assets" / "minecraft" / "blockstates").is_dir():
        return "vanilla"
    if (root / "pack.mcmeta").is_file():
        return "resourcepack"
    assets = root / "assets"
    if any(p.is_dir() for p in assets.glob("*")) if assets.is_dir() else False:
        return "mod"
    return "unknown"


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
    resolved = resolve_source(source, work_dir, marker=VANILLA_MARKER)
    return build_package_from_resolved(resolved.path, out_dir, resolved.note or "目录")


def build_package_from_resolved(
    package_root: Path,
    out_dir: Path,
    source_note: str = "目录",
) -> PackageBuild:
    """已经解压好（并已定位到包根）时走这条——避免为了探测再解压一遍。

    一个 1.12.2 客户端 jar 解压要十几秒，解两次是白花的。
    """
    package_root = Path(package_root)
    # jar 的包根（含 assets/ 的那层）要留给生成端认"资源包布局"，
    # 而 --vanilla 要的是里面的 assets/minecraft。
    minecraft_root = package_root / VANILLA_MARKER
    if not minecraft_root.is_dir():
        raise FileNotFoundError(
            "这个来源里没有 %s，看起来不是 Minecraft 客户端 jar：%s"
            % (VANILLA_MARKER, package_root)
        )
    pack_root = package_root   # 含 assets/ 的那层，生成端按它找包前缀

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
    # 必须显式指定 utf-8：这些脚本输出的是中文，而 subprocess 的 text=True 默认
    # 按系统 locale 解码（Windows 上可能是 cp1252），会直接把读取线程搞崩。
    done = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    output = (done.stdout or "") + (done.stderr or "")
    if done.returncode != 0:
        raise RuntimeError("生成素材包失败：\n%s" % output.strip())

    # 生成端拿到的是"光秃秃的原版素材"，里面没有 block_ids.tsv（那是我们自己的文件），
    # 所以在这里补上随应用带的那份；没有它，普通的实心方块只能出白模。
    if not (out_dir / "block_ids.tsv").is_file():
        if not BUNDLED_BLOCK_IDS.is_file():
            raise FileNotFoundError("应用自带的 block_ids.tsv 不见了：%s" % BUNDLED_BLOCK_IDS)
        shutil.copyfile(BUNDLED_BLOCK_IDS, out_dir / "block_ids.tsv")

    # 把原版 textures/blocks 全量补齐。
    #
    # 生成端只复制"映射表引用到的"贴图（这里 301 张）。但**模组方块会引用原版里
    # 没被引用的贴图**——例如 LittleTiles 的流动岩浆引用 minecraft/blocks/lava_flow，
    # 而岩浆不是完整方块、不在表里。只留 301 张的话，叠加模组后就会缺这些图。
    # 全量补上（500 张，多几 MB）一次性消掉这一整类问题。
    vanilla_blocks = minecraft_root / "textures" / "blocks"
    if vanilla_blocks.is_dir():
        target = out_dir / "textures" / "blocks"
        target.mkdir(parents=True, exist_ok=True)
        for png in vanilla_blocks.rglob("*.png"):
            destination = target / png.relative_to(vanilla_blocks)
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(png, destination)

    return PackageBuild(
        package_dir=out_dir,
        source_note=source_note,
        output=output.strip(),
    )
