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

from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

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
    # 没有存档时也出一张；再出一张"有导出记录"的概览图（第 5 格才看得出差别）
    dialog = ExportRegionDialog(AppConfig())
    dialog.resize(1080, 720)
    dialog.show()
    application.processEvents()
    dialog.grab().save(str(path))
    dialog.close()

    # 再出一张"有导出记录"的：项目模式下网格里出现绿/黄两色
    with tempfile.TemporaryDirectory(prefix="lt-theme-world-") as tmp:
        world = Path(tmp) / "世界"
        (world / "region").mkdir(parents=True)
        (world / "region" / "r.0.0.mca").write_bytes(b"x" * 100)
        (world / "level.dat").write_bytes(b"level")

        def states(_world, _dimension, cells):
            result = {}
            for x, z in cells:
                if abs(x) <= 1 and abs(z) <= 1:
                    result[(x, z)] = ("fresh", "导出于 2026-09-14 01:00:00")
                elif (x + 2 * z) % 3 == 0:
                    result[(x, z)] = ("stale", "导出于 2026-09-13 22:10:00，存档此后已修改")
                else:
                    result[(x, z)] = ("missing", "")
            return result

        mapped = ExportRegionDialog(
            AppConfig(), initial_save=str(world), state_provider=states
        )
        mapped.resize(1080, 720)
        mapped.show()
        application.processEvents()
        mapped.grab().save(str(path.with_name("dialog_map_" + theme_name + ".png")))
        mapped.close()


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
        (root / "world" / "region").mkdir(parents=True, exist_ok=True)
        (root / "world" / "region" / "r.0.0.mca").write_bytes(b"x" * 100)
        store = RecordStore(project.path)
        # 几条散开的记录：导出概览图才有东西可画（历史记录表也跟着有行）
        for index, (x, z) in enumerate(((12, -3), (13, -3), (12, -4), (18, -9))):
            store.add(
                ExportRecord(
                    id="2026-09-14_003%d_c%d_%d_r1" % (index, x, z), kind="region",
                    name="c%d_%d_r1" % (x, z),
                    created_at="2026-09-14 00:31:1%d" % index,
                    output_dir="outputs/2026-09-14_0031_c12_-3_r1",
                    obj="outputs/2026-09-14_0031_c12_-3_r1/house.obj",
                    world=str(root / "world"), dimension="overworld",
                    chunks=[[x, z]], faces=4940 + index * 120, textures=["abcdef"],
                )
            )
        config = AppConfig()
        config.save = lambda path=None: root / "app.json"      # 别写进仓库
        window = ProjectWindow(project, config, root)
        window.resize(1000, 860)
        window.show()
        application.processEvents()
        window.grab().save(str(path))
        # 容量条 / 图例 / 清理按钮在最底下，单独出一张（浅色下最看得出问题）
        scroll = window.centralWidget().findChild(QScrollArea)
        if scroll is not None:
            bar = scroll.verticalScrollBar()
            bar.setValue(bar.maximum())
            application.processEvents()
            bottom = path.with_name(path.stem + "_bottom" + path.suffix)
            window.grab().save(str(bottom))
        window.close()


def render_dialogs(theme_name: str, output_dir: Path) -> None:
    """两个新弹窗（项目配置 / 清空所有数据）也各出一张。"""

    application = QApplication.instance() or QApplication([])
    design.install(application, theme_name)
    from app.ui.delete_project import DeleteProjectDialog
    from app.ui.report_dialog import ReportDialog
    from app.ui.project_window import _ProjectConfigDialog
    from app.ui.project_wizard import NewProjectWizard
    from app.ui.reset_dialog import ResetDataDialog
    from app.ui.update_dialog import UpdateDialog
    from app.update import UpdateInfo

    with tempfile.TemporaryDirectory(prefix="lt-theme-dlg-") as tmp:
        root = Path(tmp)
        project = Project.create(root / "house", "海滨小屋")
        project.description = "给朋友看的版本"
        project.save()
        for dialog, name in (
            (_ProjectConfigDialog(project, lambda: None), "config"),
            (DeleteProjectDialog(str(project.path), project), "delete"),
            (ResetDataDialog(root), "reset"),
            (NewProjectWizard(AppConfig(), project.path), "wizard"),
            (
                ReportDialog(
                    AppConfig(), root, None,
                    client=__import__("app.api", fromlist=["ApiClient"]).ApiClient(
                        opener=lambda _request: b'{"success":true,"payload":{}}'
                    ),
                ),
                "report",
            ),
            (
                UpdateDialog(
                    UpdateInfo(current="0.1.0", latest="v0.9.0", has_update=True,
                               platform="macos-arm", url="https://example.invalid/a.zip",
                               note="12 MB")
                ),
                "update",
            ),
        ):
            dialog.resize(760, 520)
            dialog.show()
            application.processEvents()
            dialog.grab().save(str(output_dir / ("%s_%s.png" % (name, theme_name))))
            dialog.close()


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
    render_dialogs("dark", out_dir)
    render_dialogs("light", out_dir)
    for name in ("light", "dark", "dialog_light", "dialog_dark",
                 "dialog_map_light", "dialog_map_dark",
                 "project_light", "project_dark",
                 "project_light_bottom", "project_dark_bottom",
                 "config_light", "config_dark",
                 "delete_light", "delete_dark",
                 "reset_light", "reset_dark",
                 "wizard_light", "wizard_dark",
                 "report_light", "report_dark",
                 "update_light", "update_dark"):
        print("  %s: %s" % (name, out_dir / (name + ".png")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
