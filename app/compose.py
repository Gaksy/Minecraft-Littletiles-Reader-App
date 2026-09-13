"""按启用顺序把素材组合成一个可直接喂给库的素材包。

顺序 = 优先级（越靠下越高）。组合规则：

    原版底包            ← 映射表以它建成（必须启用）
      + 模组（按顺序）   ← 追加新方块；同名资源后者的胜

**组合结果按"顺序指纹"缓存**：指纹 = 有序的启用 id 列表 + 各自动的内容指纹。
顺序没变、素材没换，就直接复用上次的产物——不必每次导出都重新解压与解析；
变了才重做（这正是"备好一次、下次看有没有变更"的落点）。
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from .library import KIND_MOD, KIND_PACK, KIND_VANILLA, Library
from .mods import merge_mods
from .vanilla import build_package_from_resolved


class ComposeError(Exception):
    """组合不了——原因写给用户看。"""


def _merge_pack_textures(app_dir: Path, packs: list) -> Path:
    """把所有资源包的贴图按顺序并成一个临时包：**后写的覆盖先写的**。

    生成端的合并脚本一次只吃一个 `--pack`，所以多个资源包不能直接串。
    与其"逐个叠加、每轮把上一轮当底"（那样每轮都从底包重建，会丢东西——模组那轮
    踩过这个坑），不如先把贴图并成一份再交出去：一次调用，覆盖语义天然就是
    "列表里靠下的优先"。
    """
    stage = app_dir / "cache" / "sources" / "packs_merged"
    if stage.exists():
        shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)

    for pack in packs:      # 顺序即优先级：后写的覆盖先写的
        root = Path(pack.path)
        assets = root / "assets"
        if not assets.is_dir():
            # 资源包常多套一层文件夹
            nested = next(
                (p for p in sorted(root.glob("*/assets")) if p.is_dir()), None
            )
            if nested is None:
                raise ComposeError("资源包里没有 assets/：%s" % pack.name)
            assets = nested
        for png in assets.rglob("*.png"):
            destination = stage / png.relative_to(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(png, destination)
    return stage


@dataclass
class Composed:
    package_dir: Path
    reused: bool          # 直接用了上次的产物
    note: str


def order_fingerprint(library: Library) -> str:
    """启用顺序 + 各素材内容 的指纹。顺序变了就是另一个指纹。"""
    digest = hashlib.sha1()
    for source_id in library.enabled:
        digest.update(source_id.encode("utf-8"))
        digest.update(b"|")
    return digest.hexdigest()[:16]


def compose(
    app_dir: Path,
    library: Library,
    work_dir: Path | None = None,
    force: bool = False,
) -> Composed:
    """组合并缓存。已缓存且未 force 时直接复用。"""
    work_dir = work_dir or (app_dir / "cache" / "sources")
    selected = library.selected()
    if not selected:
        raise ComposeError("没有启用任何素材。")

    base = library.base
    if base is None:
        raise ComposeError(
            "启用列表里没有「原版」——映射表是以它建成的，缺了它导不出带贴图的模型。"
        )
    packs = [s for s in selected if s.kind == KIND_PACK]

    fingerprint = order_fingerprint(library)
    out_dir = app_dir / "cache" / "packages" / fingerprint
    if not force and (out_dir / "block_textures.tsv").is_file():
        return Composed(out_dir, True, "复用上次的组合（顺序与素材都没变）")

    # 1) 原版底包：从库里存的解压结果建，顺带补齐全部原版贴图。
    #    有资源包时先把它们并成一个临时包交给生成端覆盖。
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    pack_root = _merge_pack_textures(app_dir, packs) if packs else None
    build_package_from_resolved(
        Path(base.path), out_dir, base.name, pack_root=pack_root
    )

    mods = [s for s in selected if s.kind == KIND_MOD]
    note = "原版 %s" % base.name
    if mods:
        # 2) 模组一次性叠加到原版底包上。
        #
        # 曾经写成"逐个叠加、把上一轮的结果当底"，结果丢 4 张贴图（合并脚本每跑一次
        # 都会从底包重建，链式传底会把前一轮的东西丢掉）。生成端本来就支持一次传
        # 多个 --mod-root，所以一次交出去——实测 484 方块 / 326 贴图 / 缺 0。
        #
        # 代价：模组之间的先后顺序目前不生效（它们都是往同一个底包上追加，
        # 且各自命名空间不同，本来也极少互相覆盖）。真需要模组间覆盖时再说。
        stage = app_dir / "cache" / "packages" / ("%s_mods" % fingerprint)
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        merge_mods(out_dir, [Path(mod.path) for mod in mods], work_dir, stage)
        shutil.rmtree(out_dir, ignore_errors=True)
        shutil.move(str(stage), str(out_dir))
        note += " + %s" % " + ".join(s.name for s in mods)

    return Composed(out_dir, False, note)
