"""素材库：导入过的素材、它们的图标、以及启用顺序。

对应界面上的两列列表——**左列是这里登记的东西，右列是 `enabled` 这个有序列表**。
顺序 = 叠加顺序 = 优先级（和 Minecraft 的资源包界面同一个模型）。

为什么要有登记表：用户导入的是 zip/rar/jar，解压结果放在 `resources/` 下，
但"用户给它起的名字、它是哪一类、图标在哪"这些必须记下来，否则每次打开都要
重新解压、重新猜。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .sources import resolve_source

# 导入物的类型。`vanilla` 是底（映射表以它建成），其余都是往上叠。
KIND_VANILLA = "vanilla"
KIND_PACK = "resourcepack"
KIND_MOD = "mod"
KIND_UNKNOWN = "unknown"

KIND_LABELS = {
    KIND_VANILLA: "原版",
    KIND_PACK: "资源包",
    KIND_MOD: "模组",
    KIND_UNKNOWN: "未识别",
}

INDEX_NAME = "index.json"


@dataclass
class Source:
    """一个导入过的素材。"""

    id: str                 # 内容指纹，同一个文件重复导入不会产生两份
    name: str               # 显示名（去掉扩展名的文件名，之后可改）
    kind: str
    path: str               # 解压后放在 resources/sources/ 下的目录
    icon: str = ""          # 图标路径（cache/icons/），空 = 没有，界面用占位图
    imported_at: str = ""

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)


@dataclass
class Library:
    """登记表 + 启用顺序。整体序列化成一个 json。"""

    sources: list[Source] = field(default_factory=list)
    enabled: list[str] = field(default_factory=list)   # 有序的 Source.id

    # ---- 读写 ------------------------------------------------------------

    @staticmethod
    def load(app_dir: Path) -> "Library":
        path = app_dir / "resources" / INDEX_NAME
        if not path.is_file():
            return Library()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return Library()
        sources = [Source(**item) for item in data.get("sources", [])]
        enabled = [i for i in data.get("enabled", []) if any(s.id == i for s in sources)]
        return Library(sources=sources, enabled=enabled)

    def save(self, app_dir: Path) -> Path:
        path = app_dir / "resources" / INDEX_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "sources": [asdict(s) for s in self.sources],
                    "enabled": self.enabled,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    # ---- 查询 ------------------------------------------------------------

    def by_id(self, source_id: str) -> Source | None:
        return next((s for s in self.sources if s.id == source_id), None)

    def available(self) -> list[Source]:
        """左列：没被启用的。"""
        return [s for s in self.sources if s.id not in self.enabled]

    def selected(self) -> list[Source]:
        """右列：按启用顺序排好的。"""
        return [s for s in (self.by_id(i) for i in self.enabled) if s is not None]

    @property
    def base(self) -> Source | None:
        """底包：启用列表里第一个原版。没有它，别的都叠不上去。"""
        return next((s for s in self.selected() if s.kind == KIND_VANILLA), None)

    # ---- 修改 ------------------------------------------------------------

    def enable(self, source_id: str) -> None:
        if source_id in self.enabled:
            return
        source = self.by_id(source_id)
        # 原版是映射表的底：永远排在最前（优先级最低）。让它跑到下面等于原版去
        # 覆盖模组，而用户在列表上完全看不出这件事——所以直接不允许。
        if source is not None and source.kind == KIND_VANILLA:
            self.enabled.insert(0, source_id)
        else:
            self.enabled.append(source_id)      # 追加到末尾 = 优先级更高

    def disable(self, source_id: str) -> None:
        self.enabled = [i for i in self.enabled if i != source_id]

    def move(self, source_id: str, delta: int) -> None:
        """在启用列表里上下移动（-1 上移，+1 下移）；越界不动。"""
        if source_id not in self.enabled:
            return
        source = self.by_id(source_id)
        index = self.enabled.index(source_id)
        target = max(0, min(len(self.enabled) - 1, index + delta))
        # 原版钉在最前：它自己不许下移，别的也不许越过它。
        # 只挡"原版下移"是不够的——别的项上移会跑到原版上面，同样让原版去覆盖模组。
        if source is not None and source.kind == KIND_VANILLA:
            target = 0
        else:
            base = self.base
            if base is not None:
                target = max(self.enabled.index(base.id) + 1, target)
        if target != index:
            self.enabled.insert(target, self.enabled.pop(index))

    def add(self, source: Source) -> Source:
        """登记（同一个指纹已存在就返回已有的那份）。"""
        existing = self.by_id(source.id)
        if existing:
            return existing
        self.sources.append(source)
        return source


def fingerprint(path: Path, chunk: int = 1 << 20) -> str:
    """内容指纹：用来判重，也用来给解压目录与图标命名。"""
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()[:16]


def detect_kind_from_dir(root: Path) -> str:
    """看解压结果是什么。和 app.vanilla.detect_kind 同一套判断，这里避免循环引用。

    判断顺序很讲究：**不能先看 `pack.mcmeta`**——模组 jar 通常也带它（对游戏而言
    模组就是个资源包），先看它会把模组全判成资源包。正确的顺序是：
      1. 先分"是不是 jar"：jar 里有 META-INF / 类文件，资源包没有。
         这一条比"看有没有 blockstates/models"可靠得多——实测那份
         INCEPTION 资源包就带了 48 个 blockstates 和 85 个 models 去覆盖原版模型，
         按文件数判断会把它当成客户端。
      2. jar：带 assets/minecraft/blockstates → 客户端；否则 → 模组
      3. 非 jar：有 pack.mcmeta 或 assets/ → 资源包
    """
    assets = root / "assets"
    minecraft = assets / "minecraft"
    # jar（客户端或模组）的根一定有 META-INF，资源包没有
    is_jar = (root / "META-INF").is_dir() or (root / "net").is_dir()
    if is_jar:
        if (minecraft / "blockstates").is_dir():
            return KIND_VANILLA
        return KIND_MOD if assets.is_dir() else KIND_UNKNOWN
    if (root / "pack.mcmeta").is_file() or assets.is_dir():
        return KIND_PACK
    return KIND_UNKNOWN


def extract_icon(root: Path, kind: str, target_png: Path) -> str:
    """抓一张能代表这个素材的图。

    资源包用 `pack.png`（MC 的标准位置）；模组/原版用第一张方块贴图；
    都没有就返回空串，界面用占位图。
    """
    candidates: list[Path] = []
    for base in (root, *[p for p in sorted(root.glob("*")) if p.is_dir()][:3]):
        candidates.append(base / "pack.png")
    for base in (root, *[p for p in sorted(root.glob("*")) if p.is_dir()][:3]):
        blocks = base / "assets"
        if blocks.is_dir():
            for namespace in sorted(p for p in blocks.iterdir() if p.is_dir()):
                candidates.extend(
                    sorted((namespace / "textures" / "blocks").glob("*.png"))[:1]
                )
    for candidate in candidates:
        if candidate.is_file():
            target_png.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, target_png)
            return str(target_png)
    return ""


def import_source(
    archive: Path | str,
    app_dir: Path,
    work_dir: Path,
    name: str | None = None,
) -> Source:
    """导入一个 zip/rar/jar：解压 → 认类型 → 提图标 → 登记。

    解压结果按指纹存放，所以同一个文件重复导入不会越堆越多。
    `name` 是显示名（用户自己起）；不给就用去掉扩展名的文件名。
    """
    archive = Path(archive)
    if not archive.is_file():
        raise FileNotFoundError("找不到文件：%s" % archive)
    digest = fingerprint(archive)
    # marker 用"有 assets/ 或有 pack.mcmeta"：客户端 jar、模组 jar、资源包三者
    # 都满足其一，而且能穿过多套的那一层文件夹。
    resolved = resolve_source(archive, work_dir, marker=["assets", "pack.mcmeta"])
    kind = detect_kind_from_dir(resolved.path)

    stored = app_dir / "resources" / "sources" / digest
    if stored.exists():
        shutil.rmtree(stored, ignore_errors=True)
    shutil.move(str(resolved.path), str(stored))

    icon = extract_icon(
        stored, kind, app_dir / "cache" / "icons" / ("%s.png" % digest)
    )
    return Source(
        id=digest,
        name=(name or "").strip() or archive.stem,
        kind=kind,
        path=str(stored),
        icon=icon,
        imported_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
