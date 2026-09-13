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
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

CONFIG_NAME = "project.json"
LAYOUT_DIRS = ("packs", "mods", "inputs/snbt", "textures", "outputs", "records")


@dataclass
class Project:
    name: str = ""
    description: str = ""
    cover: str = ""                    # 相对项目目录的封面文件名，空 = 没有
    materials: list[str] = field(default_factory=list)   # 素材库里的 source id，有序=优先级
    options: dict = field(default_factory=dict)          # 上次用过的导出选项
    created_at: str = ""
    updated_at: str = ""
    directory: str = ""                # 项目目录（绝对路径）

    # ---- 路径 ------------------------------------------------------------

    @property
    def path(self) -> Path:
        return Path(self.directory)

    def config_path(self) -> Path:
        return self.path / CONFIG_NAME

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


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_stem(stem: str) -> str:
    """目录名要能跨平台：去掉路径分隔符与 Windows 不接受的字符。"""
    cleaned = "".join(
        ch if (ch.isalnum() or ch in "_-") else "_" for ch in stem
    )
    return cleaned.strip("_") or "export"
