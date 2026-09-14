"""删项目（项目卡片上的「删除项目」）：

* 仅从列表移除 → 登记没了、目录还在；
* 删除项目目录 → 目录连同产物一起没了，登记也没了；
* 目录里没有 project.json 时**不许递归删**（防手滑把别的目录删了）。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.project import Project  # noqa: E402
from app.ui import design, project_list  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


class _FakeDialog:
    """替身：直接给出用户在那个弹窗里选的模式。"""

    DialogCode = QDialog.DialogCode
    mode = "forget"

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def exec(self) -> int:
        return QDialog.DialogCode.Accepted


def main() -> int:
    print("== 删除项目 ==")
    application = QApplication.instance() or QApplication([])
    design.install(application, "dark")

    with tempfile.TemporaryDirectory(prefix="lt-delproj-") as tmp:
        root = Path(tmp)
        config = AppConfig()
        config.save = lambda path=None: root / "app.json"
        real_dialog = project_list._DeleteProjectDialog

        house = Project.create(root / "house", "海滨小屋")
        (house.path / "outputs" / "2026-09-14_0000_x").mkdir(parents=True)
        (house.path / "outputs" / "2026-09-14_0000_x" / "house.obj").write_bytes(b"v" * 4096)
        config.register_project(house.path)

        widget = project_list.ProjectListWidget(config, None)
        check("卡片上写着删除项目",
              any(card.btn_delete.text() == "删除项目"
                  for card in widget.findChildren(project_list.ProjectCard)))

        # 1) 仅从列表移除
        _FakeDialog.mode = "forget"
        project_list._DeleteProjectDialog = _FakeDialog
        widget._delete_project(str(house.path))
        check("登记删掉了", str(house.path) not in config.project_paths())
        check("目录还在", house.path.is_dir() and (house.path / "project.json").is_file())
        check("项目里的产物还在",
              (house.path / "outputs" / "2026-09-14_0000_x" / "house.obj").is_file())

        # 2) 连目录一起删
        config.register_project(house.path)
        widget.refresh()
        _FakeDialog.mode = "purge"
        widget._delete_project(str(house.path))
        check("目录被删了", not house.path.exists())
        check("登记也删了", str(house.path) not in config.project_paths())

        # 3) 目录里没有 project.json → 不递归删
        plain = root / "别的东西"
        plain.mkdir()
        (plain / "重要文件.txt").write_text("不能删", encoding="utf-8")
        config.register_project(plain)
        widget.refresh()
        project_list.QMessageBox.warning = staticmethod(lambda *a, **k: None)
        widget._delete_project(str(plain))
        check("不是项目目录就不删", (plain / "重要文件.txt").is_file())
        # 什么都没做，登记也不动：不然会出现"列表里没了、目录还在"的悬空状态
        check("拒绝删除时登记也不动", str(plain) in config.project_paths())

        # 4) 目录已经不在：弹窗里只能选"从列表移除"，不会去想删不存在的目录
        gone = root / "gone"
        gone.mkdir()
        dialog = real_dialog(str(gone), None)
        check("目录还在时默认只移除登记", dialog.mode == "forget")
        check("目录还在时能选删目录", dialog.opt_purge.isEnabled())
        gone.rmdir()
        missing = real_dialog(str(gone), None)
        check("目录不在时删目录选项是禁用的", not missing.opt_purge.isEnabled())
        check("目录不在时确定键可用（只移除登记）", missing.btn_ok.isEnabled())

        # 5) 删除目录那条要额外勾一个确认框才让按
        fresh = Project.create(root / "fresh", "新房子")
        gate = real_dialog(str(fresh.path), None)
        check("默认只移除登记：确定可用", gate.btn_ok.isEnabled())
        gate.opt_purge.setChecked(True)
        check("选了删目录但没勾确认：确定禁用", not gate.btn_ok.isEnabled())
        gate.confirm.setChecked(True)
        check("勾了确认才能按删除", gate.btn_ok.isEnabled())
        gate.accept()
        check("确定后模式是删目录", gate.mode == "purge")
        gate.close()
        dialog.close()
        missing.close()
        widget.close()

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
