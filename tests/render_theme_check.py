"""把界面在深色与浅色主题下各渲染一张 PNG，人工核对配色。

离屏运行，不需要显示器：
    python tests/render_theme_check.py [输出目录]

主题由 `app/ui/design` 决定（与网站同一套令牌），所以这里直接切设计系统的
主题名——早期版本是手工造一份 Qt 调色板来模拟深浅色，那套已经管不到界面了。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.project import Project  # noqa: E402
from app.records import ExportRecord, RecordStore  # noqa: E402
from app.ui import design  # noqa: E402
from app.ui.export_dialog import ExportRegionDialog  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.project_window import ProjectWindow  # noqa: E402


def render(theme_name: str, path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    design.install(application, theme_name)
    window = MainWindow(AppConfig())
    window.resize(880, 620)
    window.show()
    application.processEvents()
    window.grab().save(str(path))
    window.close()


def render_dialog(theme_name: str, path: Path) -> None:
    """导出对话框里画得最多（自绘网格），单独出一张。"""
    application = QApplication.instance() or QApplication([])
    design.install(application, theme_name)
    dialog = ExportRegionDialog(AppConfig())
    dialog.resize(760, 620)
    dialog.show()
    application.processEvents()
    dialog.grab().save(str(path))
    dialog.close()


def render_project(theme_name: str, path: Path) -> None:
    """项目界面：容量条和图例只有这里有，配色对不对得看它。"""
    application = QApplication.instance() or QApplication([])
    design.install(application, theme_name)
    with tempfile.TemporaryDirectory(prefix="lt-theme-proj-") as tmp:
        root = Path(tmp)
        project = Project.create(root / "house", "海滨小屋")
        project.description = "给朋友看的版本"
        project.materials = ["演示素材"]
        project.save()
        # 造点体积，容量条才有东西可画
        (project.path / "outputs" / "2026-09-14_0031_c12_-3_r1").mkdir(parents=True)
        (project.path / "outputs" / "2026-09-14_0031_c12_-3_r1" / "house.obj").write_bytes(
            b"v 0 0 0\n" * 6000
        )
        (project.path / "package").mkdir(exist_ok=True)
        (project.path / "package" / "block_textures.tsv").write_bytes(b"x" * 240000)
        (project.path / "inputs" / "saves").mkdir(parents=True, exist_ok=True)
        (project.path / "inputs" / "saves" / "2026-09-14_0040_house.zip").write_bytes(b"z" * 90000)
        (project.path / "textures" / "ab").mkdir(parents=True, exist_ok=True)
        (project.path / "textures" / "ab" / "abcdef.png").write_bytes(b"p" * 60000)
        RecordStore(project.path).add(
            ExportRecord(
                id="2026-09-14_0031_c12_-3_r1", kind="region", name="c12_-3_r1",
                created_at="2026-09-14 00:31:12",
                output_dir="outputs/2026-09-14_0031_c12_-3_r1",
                obj="outputs/2026-09-14_0031_c12_-3_r1/house.obj",
                world=str(root / "world"), dimension="overworld",
                chunks=[[12, -3]], faces=4940, textures=["abcdef"],
            )
        )
        config = AppConfig()
        config.save = lambda path=None: root / "app.json"      # 别写进仓库
        window = ProjectWindow(project, config, root)
        window.resize(1000, 860)
        window.show()
        application.processEvents()
        window.grab().save(str(path))
        window.close()


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tmp" / "theme"
    out_dir.mkdir(parents=True, exist_ok=True)
    light = out_dir / "light.png"
    dark = out_dir / "dark.png"
    # 深色是默认主题（与网站一致），浅色是另一套；文件名保持 light/dark
    render("dark", dark)
    render("light", light)
    render_dialog("dark", out_dir / "dialog_dark.png")
    render_dialog("light", out_dir / "dialog_light.png")
    render_project("dark", out_dir / "project_dark.png")
    render_project("light", out_dir / "project_light.png")
    for name in ("light", "dark", "dialog_light", "dialog_dark",
                 "project_light", "project_dark"):
        print("  %s: %s" % (name, out_dir / (name + ".png")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
