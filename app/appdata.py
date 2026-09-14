"""应用自己名下的数据：算体积、清空。

**属于应用、可以随时重建的**（"清空所有数据"动的就是这些）：

  - ``config/app.json``    项目登记表、最近存档/结构、界面偏好、默认输出目录
  - ``resources/sources/`` 导入的素材（解包结果或原样副本）与素材库登记
  - ``cache/``             解包中间件与素材组合结果
  - ``outputs/``           快速导出的产物
  - ``tmp/``               每次导出的 job.json、粘贴进来的 SNBT
  - ``logs/``              会话日志

**不属于应用、永远不动的**：用户自己挑的项目目录（可能在别的盘、别的地方）。
项目里的产物、素材副本、历史记录都归项目所有——要删项目，去项目卡片上删。

清空之后应用照常运行：缺的目录下次用到时自己重建。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .storage import dir_size


@dataclass(frozen=True)
class Category:
    """一类可清空的数据：key 用于选择，label/hint 用于界面。"""

    key: str
    label: str
    hint: str
    paths: tuple[str, ...]


CATEGORIES: tuple[Category, ...] = (
    Category(
        "settings",
        "设置与项目登记",
        "默认输出目录、最近打开过的存档/结构、界面偏好、项目列表",
        ("config/app.json",),
    ),
    Category(
        "materials",
        "素材库",
        "导入的材质包 / 模组、解包结果、素材组合缓存",
        ("resources/sources", "resources/index.json", "cache"),
    ),
    Category(
        "outputs",
        "导出产物与临时文件",
        "快速导出的 outputs/、导出与粘贴用的 tmp/",
        ("outputs", "tmp"),
    ),
    Category(
        "logs",
        "会话日志",
        "logs/ 下按启动时间切分的日志文件",
        ("logs",),
    ),
)

_BY_KEY = {category.key: category for category in CATEGORIES}


def category_for(key: str) -> Category:
    return _BY_KEY[key]


def path_size(app_dir: Path | str, key: str) -> int:
    """这一类现在占多少字节（文件和目录都算）。"""

    total = 0
    for relative in category_for(key).paths:
        target = Path(app_dir) / relative
        if target.is_dir():
            total += dir_size(target)
        elif target.is_file():
            total += target.stat().st_size
    return total


def sizes(app_dir: Path | str) -> dict[str, int]:
    return {category.key: path_size(app_dir, category.key) for category in CATEGORIES}


def clear(app_dir: Path | str, keys) -> dict[str, int]:
    """清掉选定的几类数据，返回每类释放的字节数。

    目录是"删掉再建回空目录"（而不是留着旧内容），这样应用接着用不会踩到
    半个状态；单文件（config/app.json、resources/index.json）直接删。
    """

    app_dir = Path(app_dir)
    freed: dict[str, int] = {}
    for key in keys:
        category = category_for(key)
        before = path_size(app_dir, key)
        for relative in category.paths:
            target = app_dir / relative
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
                target.mkdir(parents=True, exist_ok=True)
            elif target.exists():
                target.unlink()
        freed[key] = before
    return freed


def reset_config(config: AppConfig) -> Path:
    """把内存里的配置恢复成出厂值并落盘（清空设置时用）。"""

    defaults = AppConfig()
    for name in AppConfig.__dataclass_fields__:
        setattr(config, name, getattr(defaults, name))
    return config.save()
