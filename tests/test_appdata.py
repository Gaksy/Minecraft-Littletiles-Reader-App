"""清空所有数据（菜单「应用 → 清空所有数据」）。

要验的是"边界"：应用自己的东西清干净（设置 / 素材库 / 产物 / 日志），
而**用户的项目目录一个字节都不能动**——项目里的素材副本、产物、记录都归项目，
要删项目得去项目卡片上删。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from app import appdata  # noqa: E402
from app.config import AppConfig  # noqa: E402
from app.library import Library  # noqa: E402
from app.project import Project  # noqa: E402
from app.ui import design  # noqa: E402
from app.ui.reset_dialog import ResetDataDialog  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def make_app_dir(root: Path) -> Path:
    """造一份"用了一阵子"的应用目录 + 一个必须活下来的项目目录。"""

    app_dir = root / "app"
    (app_dir / "config").mkdir(parents=True)
    (app_dir / "config" / "app.json").write_text('{"ui_theme": "light"}', encoding="utf-8")
    (app_dir / "resources" / "sources" / "pack").mkdir(parents=True)
    (app_dir / "resources" / "sources" / "pack" / "a.png").write_bytes(b"x" * 2048)
    (app_dir / "resources" / "index.json").write_text("{}", encoding="utf-8")
    (app_dir / "cache" / "packages" / "abc").mkdir(parents=True)
    (app_dir / "cache" / "packages" / "abc" / "b.bin").write_bytes(b"y" * 4096)
    (app_dir / "outputs" / "2026-09-14_0000_x").mkdir(parents=True)
    (app_dir / "outputs" / "2026-09-14_0000_x" / "x.obj").write_bytes(b"z" * 8192)
    (app_dir / "tmp").mkdir()
    (app_dir / "tmp" / "job_1.json").write_text("{}", encoding="utf-8")
    (app_dir / "logs").mkdir()
    (app_dir / "logs" / "2026-09-14_000000.log").write_text("hi", encoding="utf-8")

    project = Project.create(root / "项目" / "house", "海滨小屋")
    (project.path / "outputs" / "2026-09-14_0001_x").mkdir(parents=True)
    (project.path / "outputs" / "2026-09-14_0001_x" / "house.obj").write_bytes(b"o" * 1024)
    return app_dir


def main() -> int:
    print("== 清空所有数据 ==")
    application = QApplication.instance() or QApplication([])
    design.install(application, "dark")

    with tempfile.TemporaryDirectory(prefix="lt-appdata-") as tmp:
        root = Path(tmp)
        app_dir = make_app_dir(root)
        project_dir = root / "项目" / "house"

        sizes = appdata.sizes(app_dir)
        check("四类都算得出体积",
              all(sizes[key] > 0 for key in ("settings", "materials", "outputs", "logs")),
              str(sizes))

        # 对话框：默认全选、取消按钮语义正确、只勾一类时也能算总量
        dialog = ResetDataDialog(app_dir)
        check("默认四类全选", len(dialog.keys()) == 4, str(dialog.keys()))
        dialog.boxes["logs"].setChecked(False)
        check("取消勾选后少一类", dialog.keys() == ["settings", "materials", "outputs"],
              str(dialog.keys()))
        texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
        check("弹窗里写明不删项目目录", "项目目录不会被删除" in texts, texts[:40])
        check("总量跟着勾选变", "3 类" in dialog.total.text(), dialog.total.text())
        dialog.close()

        # 只清产物与临时文件：其它类必须原封不动
        appdata.clear(app_dir, ["outputs"])
        check("产物目录清空了", list((app_dir / "outputs").iterdir()) == [])
        check("临时文件清空了", list((app_dir / "tmp").iterdir()) == [])
        check("素材库没被动", (app_dir / "resources" / "index.json").is_file())
        check("配置没被动", (app_dir / "config" / "app.json").is_file())

        # 再清设置 / 素材 / 日志
        freed = appdata.clear(app_dir, ["settings", "materials", "logs"])
        check("配置删了", not (app_dir / "config" / "app.json").is_file())
        check("素材库登记删了", not (app_dir / "resources" / "index.json").is_file())
        check("解压出来的素材删空了", list((app_dir / "resources" / "sources").iterdir()) == [])
        check("组合缓存删空了", list((app_dir / "cache").iterdir()) == [])
        check("日志删空了", list((app_dir / "logs").iterdir()) == [])
        check("返回了释放体积", sum(freed.values()) > 0, str(freed))

        # 项目目录：一根毫毛都不能少
        check("项目目录还在", (project_dir / "project.json").is_file())
        check("项目产物还在",
              (project_dir / "outputs" / "2026-09-14_0001_x" / "house.obj").is_file())
        check("清空后还能把项目读回来", Project.load(project_dir) is not None)

        # 清空后应用接着用：素材库读出来是空的，不是报错
        check("素材库读出来是空的", len(Library.load(app_dir).sources) == 0)

        # 配置复位：字段回到出厂值
        config = AppConfig()
        config.default_assets = "别处"
        config.projects = [{"path": str(project_dir)}]
        config.ui_theme = "light"
        config.save(app_dir / "config" / "app.json")
        appdata.reset_config(config)
        check("配置复位到默认值",
              config.default_assets == "" and config.projects == [] and config.ui_theme == "dark",
              "%s / %s / %s" % (config.default_assets, config.projects, config.ui_theme))
        check("复位也落盘了", (app_dir / "config" / "app.json").is_file())

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
