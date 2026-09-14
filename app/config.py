"""应用配置：便携式，存在应用所在目录下。

`config/app.json` 记录与"用户是谁"无关的东西：库 CLI 在哪、默认输出目录、
最近用过的素材包与存档。项目自己的配置在项目目录里（M2），不在这里。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# 仓库根 = 应用目录。打包后它就是安装目录（便携式），所以配置与受管资源都放在旁边。
APP_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = APP_DIR / "config"
CONFIG_PATH = CONFIG_DIR / "app.json"

MAX_RECENT = 10


@dataclass
class AppConfig:
    """全部字段都有默认值，缺字段的旧配置也能读。"""

    library_cli: str = ""       # LittleTilesReader 可执行文件；空 = 交给 ltgen.paths 找
    default_assets: str = ""    # 最近使用的素材包目录
    output_dir: str = ""        # 快速导出的默认输出目录；空 = 应用目录下的 outputs/
    recent_saves: list[str] = field(default_factory=list)
    recent_snbt: list[str] = field(default_factory=list)
    projects: list[dict] = field(default_factory=list)  # 项目登记表（M2 用）
    last_project: str = ""                              # 最近打开的项目目录
    last_export: dict = field(default_factory=dict)     # 上次的导出选项，作为下次默认
    ask_open_output: bool = True                        # 导出完成后是否询问打开目录
    shown_chunk_help: bool = False                      # 区块选择说明是否已经自动弹过一次
    ui_theme: str = "dark"                              # 界面主题：dark（默认，同网站）/ light
    language: str = ""                                  # 界面语言：空 = 跟随系统；否则是 i18n 的语言代码

    @staticmethod
    def load(path: Path | None = None) -> "AppConfig":
        target = path or CONFIG_PATH
        if not target.is_file():
            return AppConfig()
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # 配置坏了不该让应用起不来：退回默认值，保存时覆盖。
            return AppConfig()
        if not isinstance(data, dict):
            return AppConfig()
        known = set(AppConfig.__dataclass_fields__)
        return AppConfig(**{k: v for k, v in data.items() if k in known})

    def save(self, path: Path | None = None) -> Path:
        target = path or CONFIG_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return target

    def remember_save(self, path: str) -> None:
        self.recent_saves = _bump(self.recent_saves, path)

    def remember_snbt(self, path: str) -> None:
        self.recent_snbt = _bump(self.recent_snbt, path)

    def resolved_output_dir(self) -> Path:
        return Path(self.output_dir) if self.output_dir else APP_DIR / "outputs"

    # ---- 项目登记表 ------------------------------------------------------
    #
    # 项目目录是用户自己挑的，所以"项目列表"不能靠扫目录树——登记表在配置里，
    # 而项目内的 `project.json` 是权威：读得到就以它为准（项目可能被搬过地方）。

    def project_paths(self) -> list[str]:
        """登记的项目目录，按登记顺序（列表里的顺序就是界面上的顺序）。"""
        result: list[str] = []
        for item in self.projects:
            path = item.get("path") if isinstance(item, dict) else str(item)
            if path and path not in result:
                result.append(path)
        return result

    def register_project(self, path: Path | str) -> None:
        text = str(Path(path))
        if text in self.project_paths():
            return
        self.projects.append({"path": text})

    def unregister_project(self, path: Path | str) -> None:
        text = str(Path(path))
        self.projects = [
            item
            for item in self.projects
            if (item.get("path") if isinstance(item, dict) else str(item)) != text
        ]
        if self.last_project == text:
            self.last_project = ""


def _bump(items: list[str], value: str) -> list[str]:
    """把 value 提到最前，去重，并截断到 MAX_RECENT。"""
    rest = [item for item in items if item != value]
    return [value] + rest[: MAX_RECENT - 1]
