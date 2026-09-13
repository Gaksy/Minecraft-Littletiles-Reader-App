"""项目：一个目录 + 一份 `project.json`，装这个项目的一切。

目录布局（详见 docs/design.md §4.2）::

    <项目目录>/
    ├── project.json          名称、描述、封面、绑定的素材、默认导出选项
    ├── cover.png             封面原图
    ├── packs/  mods/         绑定的素材副本（从素材库复制进来）
    ├── inputs/snbt/          导入过的结构文件副本
    ├── textures/             贴图库（后端维护，按内容哈希）
    ├── outputs/              每次导出一个时间戳目录
    └── records/              导出记录与区块索引

为什么项目要自带素材副本：项目目录是用户自己挑的位置，可能被搬到别的盘、
发给别人、几年后再打开。那时素材库里那份早就没了，项目必须能自给自足。

**项目目录是用户指定的**，所以"项目列表"不能靠扫目录树——登记表在应用配置里，
而项目内的 `project.json` 是权威（读到什么就以什么为准）。
"""

from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

CONFIG_NAME = "project.json"
LAYOUT_DIRS = ("packs", "mods", "inputs/snbt", "textures", "outputs", "records")
PACKAGE_DIR = "package"
BACKUP_DIR = "inputs/saves"


@dataclass
class Project:
    name: str = ""
    description: str = ""
    cover: str = ""                    # 相对项目目录的封面文件名，空 = 没有
    materials: list[str] = field(default_factory=list)   # 素材库里的 source id，有序=优先级
    save_root: str = ""                # 本项目默认存档根目录（含 level.dat）
    package_fingerprint: str = ""      # <项目>/package 是哪次组合的结果
    options: dict = field(default_factory=dict)          # 上次用过的导出选项
    # 保留策略（§7.7）：默认全 0 = 什么都不自动删
    keep_exports: int = 0              # 只保留最近 N 次导出；0 = 不限
    keep_days: int = 0                 # 只保留最近 X 天；0 = 不限
    keep_size_mb: int = 0              # 总大小上限（MB）；0 = 不限
    auto_clean: bool = False           # 打开项目时按策略自动清理（会先问一次）
    created_at: str = ""
    updated_at: str = ""
    directory: str = ""                # 项目目录（绝对路径）

    # ---- 路径 ------------------------------------------------------------

    @property
    def path(self) -> Path:
        return Path(self.directory)

    def config_path(self) -> Path:
        return self.path / CONFIG_NAME

    @property
    def package_dir(self) -> Path:
        """本项目自己的素材包（组合结果副本）——导出只用它，见 project_assets.py。"""
        return self.path / PACKAGE_DIR

    @property
    def cover_path(self) -> Path | None:
        if not self.cover:
            return None
        candidate = self.path / self.cover
        return candidate if candidate.is_file() else None

    # ---- 读写 ------------------------------------------------------------

    @staticmethod
    def load(directory: Path | str) -> "Project | None":
        """读项目；目录里没有 `project.json` 就返回 None（调用方据此显示"不可用"）。"""
        directory = Path(directory)
        config = directory / CONFIG_NAME
        if not config.is_file():
            return None
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        known = set(Project.__dataclass_fields__)
        project = Project(**{k: v for k, v in data.items() if k in known})
        project.directory = str(directory)      # 以实际读到的位置为准
        return project

    def save(self) -> Path:
        self.updated_at = _now()
        if not self.created_at:
            self.created_at = self.updated_at
        path = self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    @staticmethod
    def create(directory: Path | str, name: str) -> "Project":
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        project = Project(name=name, directory=str(directory))
        project.created_at = _now()
        project.ensure_layout()
        project.save()
        return project

    def ensure_layout(self) -> None:
        """把缺的子目录补出来。搬过一个半成品目录之后也能用。"""
        for child in LAYOUT_DIRS:
            (self.path / child).mkdir(parents=True, exist_ok=True)

    def cover_png(self) -> Path | None:
        """封面图（找不到就返回 None，界面显示占位块）。"""
        if not self.cover:
            return None
        candidate = self.path / self.cover
        return candidate if candidate.is_file() else None

    def set_cover(self, image: Path | str) -> Path:
        """把用户选的图片存成项目里的 `cover.png`。

        存副本而不是记原路径：项目要能自给自足，原图被删/被挪都不该影响项目。
        但**不**顺手做缩放——那需要 Qt 的图片栈，而这层是不依赖 Qt 的数据层；
        卡片显示时由界面按需缩放。
        """
        source = Path(image)
        target = self.path / "cover.png"
        self.path.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        self.cover = target.name
        self.save()
        return target

    # ---- 存档 ------------------------------------------------------------

    def backups(self) -> list[Path]:
        """已有的存档备份（新的在前）。"""
        target = self.path / BACKUP_DIR
        if not target.is_dir():
            return []
        return sorted(
            (item for item in target.glob("*.zip")), reverse=True
        )

    def backup_save(self, save_root: Path | str, note: str = "") -> Path:
        """把**整个存档**打成一个 zip 存进项目（设计文档 §0 第 4 条）。

        整个存档而不是 region：用户要的是"这个世界的备份"，少一个 level.dat 就打不开了。
        """
        source = Path(save_root)
        if not source.is_dir():
            raise FileNotFoundError("找不到存档目录：%s" % source)
        target_dir = self.path / BACKUP_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        name = "%s_%s" % (stamp, _safe_stem(note or source.name))
        archive = target_dir / ("%s.zip" % name)
        candidate = archive
        index = 2
        while candidate.exists():
            candidate = target_dir / ("%s_%d.zip" % (name, index))
            index += 1
        with zipfile.ZipFile(candidate, "w", zipfile.ZIP_DEFLATED) as handle:
            for item in sorted(source.rglob("*")):
                if item.is_file():
                    handle.write(item, item.relative_to(source.parent))
        return candidate

    # ---- 项目配置的导入导出 ----------------------------------------------

    def export_config(self, target: Path | str) -> Path:
        """把项目配置打成一个 zip：project.json + 封面。

        只带配置，不带素材副本与产物——那几样动辄几百 MB，"换机器/备份配置"
        要的不是它们（素材可以在新机器上重新绑定）。
        """
        archive = Path(target)
        archive.parent.mkdir(parents=True, exist_ok=True)
        self.save()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
            handle.write(self.config_path(), CONFIG_NAME)
            cover = self.cover_png()
            if cover is not None:
                handle.write(cover, cover.name)
        return archive

    @staticmethod
    def import_config(archive: Path | str, directory: Path | str) -> "Project":
        """从配置包恢复一个项目到指定目录。

        `materials` 里的 id 是**素材库内**的指纹：新机器上素材库可能没有同样的条目，
        所以这里原样保留 id，由界面提示"绑定的素材缺失，请重新绑定"。
        """
        source = Path(archive)
        if not source.is_file():
            raise FileNotFoundError("找不到项目包：%s" % source)
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source) as handle:
            names = set(handle.namelist())
            if CONFIG_NAME not in names:
                raise ValueError("这个包里没有 %s，不像项目配置包" % CONFIG_NAME)
            handle.extract(CONFIG_NAME, target)
            if "cover.png" in names:
                handle.extract("cover.png", target)
        project = Project.load(target)
        if project is None:
            raise ValueError("配置包里的 %s 读不出来" % CONFIG_NAME)
        # 目录以实际解出来的位置为准：包里记的是原来的路径，换机器就失效了
        project.directory = str(target)
        project.ensure_layout()
        project.save()
        return project

    # ---- 导出产物 --------------------------------------------------------

    def next_output_dir(self, stem: str) -> Path:
        """按时间戳新建一个产物目录，**从复用已有的**（见 design §7.5）。

        同一分钟内重复导出加 `_2`、`_3`；时间戳在前，便于按名字排序就是时间顺序。
        """
        self.ensure_layout()
        safe = _safe_stem(stem)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        base = self.path / "outputs" / ("%s_%s" % (stamp, safe))
        candidate = base
        index = 2
        while candidate.exists():
            candidate = Path("%s_%d" % (base, index))
            index += 1
        candidate.mkdir(parents=True)
        return candidate

    # ---- 素材副本 --------------------------------------------------------

    def bind_material(self, source, kind_dir: str) -> Path:
        """把素材库里的一个来源复制进项目（`packs/` 或 `mods/`）。

        复制而不是引用：项目要能自给自足，见模块开头。
        """
        self.ensure_layout()
        target = self.path / kind_dir / source.name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(source.path, target)
        if source.id not in self.materials:
            self.materials.append(source.id)
        return target

    def bound_sources(self) -> list[tuple[str, Path]]:
        """项目里实际绑着的素材副本：`[(kind_dir, 目录), ...]`，按目录名排。"""
        result: list[tuple[str, Path]] = []
        for kind_dir in ("packs", "mods"):
            base = self.path / kind_dir
            if not base.is_dir():
                continue
            result.extend(
                (kind_dir, child)
                for child in sorted(base.iterdir())
                if child.is_dir()
            )
        return result

    def unbind(self, name: str, kind_dir: str) -> None:
        """从项目里解绑：删掉副本，并从 `materials` 里去掉对应的 id。

        id 与目录名不是一回事（id 是内容指纹），所以按目录名反查素材库拿不到时就
        只删副本——宁可留一个"绑定失效"的登记，也别把别的素材的 id 顺手删了。
        """
        target = self.path / kind_dir / name
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        self.save()

    def move_to(self, new_directory: Path | str, keep: bool = False) -> "Project":
        """把项目搬到新目录（`keep=False` 时是移动，True 时是复制一份过去）。"""
        target = Path(new_directory)
        if target.exists() and any(target.iterdir()):
            raise FileExistsError("目标目录不是空的：%s" % target)
        source = self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        if keep:
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.move(str(source), str(target))
        self.directory = str(target)
        self.save()
        return self


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_stem(stem: str) -> str:
    """目录名要能跨平台：去掉路径分隔符与 Windows 不接受的字符。"""
    cleaned = "".join(
        ch if (ch.isalnum() or ch in "_-") else "_" for ch in stem
    )
    return cleaned.strip("_") or "export"
