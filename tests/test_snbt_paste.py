"""粘贴文本导出 SNBT（P0 需求）：快速导出与项目模式都能粘贴。

    python tests/test_snbt_paste.py
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
from app.ui import design, main_window, project_window  # noqa: E402
from app.ui.snbt_source import save_pasted_snbt  # noqa: E402

SAMPLE = ('{tiles:[{boxes:[[I;0,0,0,16,16,16]],'
          'tile:{block:"minecraft:stone"}}],grid:16}')

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def test_save_helper() -> None:
    print("落盘助手：")
    with tempfile.TemporaryDirectory(prefix="lt-paste-") as tmp:
        target = save_pasted_snbt(SAMPLE, Path(tmp) / "tmp")
        check("文件写出来了", target.is_file(), str(target))
        check("内容一致", target.read_text(encoding="utf-8") == SAMPLE)
        check("落在 tmp/ 下", target.parent.name == "tmp")


def test_quick_export() -> None:
    print("快速导出粘贴：")
    application = QApplication.instance() or QApplication([])
    design.install(application, "dark")
    with tempfile.TemporaryDirectory(prefix="lt-paste-") as tmp:
        root = Path(tmp)
        config = AppConfig()
        config.save = lambda path=None: root / "app.json"
        window = main_window.MainWindow(config)

        captured: dict = {}
        # 粘贴来源 + 素材包 + 真正跑 job 的那一步都换成替身
        main_window.choose_snbt_source = lambda parent: ("paste", SAMPLE)
        window._choose_assets = lambda: str(root / "pack")
        window._run = lambda job: captured.update(job=job)
        main_window.APP_DIR = root          # 粘贴文件落到临时目录，不脏仓库

        window._export_snbt()
        job = captured.get("job") or {}
        check("生成了 snbt job", job.get("mode") == "snbt", str(job.get("mode")))
        snbt_path = Path((job.get("input") or {}).get("snbt", {}).get("path", ""))
        check("job 指向落盘的文件", snbt_path.is_file(), str(snbt_path))
        check("文件内容一致",
              snbt_path.is_file() and snbt_path.read_text(encoding="utf-8") == SAMPLE)
        check("输出目录用的是配置里的默认输出目录",
              str(config.resolved_output_dir()) in str((job.get("output") or {}).get("dir")),
              str((job.get("output") or {}).get("dir")))

        # 取消（None）什么都不做
        captured.clear()
        main_window.choose_snbt_source = lambda parent: None
        window._export_snbt()
        check("取消时不生成 job", not captured)
        window.close()


def test_project_paste() -> None:
    print("项目模式粘贴：")
    application = QApplication.instance() or QApplication([])
    design.install(application, "dark")
    with tempfile.TemporaryDirectory(prefix="lt-paste-") as tmp:
        root = Path(tmp)
        project = Project.create(root / "house", "小屋")
        config = AppConfig()
        config.save = lambda path=None: root / "app.json"
        window = project_window.ProjectWindow(project, config, root)

        captured: dict = {}
        project_window.choose_snbt_source = lambda parent: ("paste", SAMPLE)
        window._run_snbt = lambda path, output_name="": captured.update(path=path)
        window._export_snbt()
        path = captured.get("path")
        check("粘贴文本落进项目的 inputs/snbt",
              isinstance(path, Path) and path.parent.name == "snbt"
              and "inputs" in str(path), str(path))
        check("内容一致",
              isinstance(path, Path) and path.read_text(encoding="utf-8") == SAMPLE)
        window.close()


def main() -> int:
    test_save_helper()
    test_quick_export()
    test_project_paste()
    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
