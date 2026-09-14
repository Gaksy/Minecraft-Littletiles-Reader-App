"""多语言：机制要能用，数据要没写错。

三种错法都要挡住：

1. 语言表里的**键写错一个字**（键是中文原文，差了就永远匹配不上，界面看着像没翻）——
   所以建完真实窗口后统计"还剩多少中文没被换掉"，超了就报出来；
2. 表里有**空值**或没翻（值 == 键）——除了少量故意的（CLI、zip 这种）；
3. 切到未知语言代码要能**安全退回**简体中文。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QAbstractButton,
    QGroupBox,
    QLabel,
)

from app import i18n  # noqa: E402
from app.config import AppConfig  # noqa: E402
from app.project import Project  # noqa: E402
from app.ui import design  # noqa: E402
from app.ui.export_dialog import ExportRegionDialog  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.project_list import ProjectListWidget  # noqa: E402
from app.ui.project_window import (  # noqa: E402
    ProjectWindow,
    _BackupsDialog,
    _ChunkSearchDialog,
    _ProjectConfigDialog,
    _RetentionDialog,
)
from app.ui.material_manager import MaterialManagerDialog  # noqa: E402
from app.records import ExportRecord, RecordStore  # noqa: E402
from app.ui.delete_project import DeleteProjectDialog  # noqa: E402
from app.ui.project_wizard import NewProjectWizard  # noqa: E402
from app.ui.reset_dialog import ResetDataDialog  # noqa: E402

FAILURES: list[str] = []

#: 这些句子在中文和译文里本来就该长一样（专有名词、命令名）
ALLOW_SAME = {"CLI", "zip", "SNBT", "OBJ"}
#: 拉丁字母语言才要求"必须不一样"；繁体/日/韩里同形词本来就多（取消、半径…）
LATIN = ("en", "de", "fr")
#: 这些键一定要被替换掉才能算"界面真的换语言了"
MUST_TRANSLATE = ("快速导出", "新建项目", "添加已有项目", "删除项目", "重新定位")


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def visible_texts(widget) -> list[str]:
    texts: list[str] = []
    for child in widget.findChildren(QLabel):
        if child.text():
            texts.append(child.text())
    for child in widget.findChildren(QGroupBox):
        if child.title():
            texts.append(child.title())
    for child in widget.findChildren(QAbstractButton):
        if child.text():
            texts.append(child.text())
    return texts


def main() -> int:
    print("== 多语言 ==")
    application = QApplication.instance() or QApplication([])
    design.install(application, "dark")

    check("七种语言都在", len(i18n.LANGUAGES) == 7,
          str([code for code, _ in i18n.LANGUAGES]))
    check("默认是简体中文", i18n.current() == "zh-Hans", i18n.current())

    # 1) 每张表：没有空值、没有"抄了一遍中文"的偷懒
    for code in i18n.codes():
        if code == i18n.SOURCE:
            continue
        i18n.set_language(code)
        table = i18n.table()
        check("%s：有译文" % code, len(table) >= 60, str(len(table)))
        empty = [key for key, value in table.items() if not value.strip()]
        check("%s：没有空译文" % code, not empty, str(empty[:3]))
        if code in LATIN:
            same = [
                key
                for key, value in table.items()
                if value.strip() == key.strip() and key.strip() not in ALLOW_SAME
            ]
            check("%s：没有把中文抄一遍" % code, not same, str(same[:3]))
        else:
            # 汉字圈语言允许同形词，但"整张表都照抄"必须挡住
            copied = sum(1 for key, value in table.items() if value.strip() == key.strip())
            check("%s：同形词不超过三成" % code, copied < len(table) * 0.3,
                  "%d / %d" % (copied, len(table)))

    # 2) 真界面：菜单/按钮/标签要真的被换掉
    with tempfile.TemporaryDirectory(prefix="lt-i18n-") as tmp:
        root = Path(tmp)
        config = AppConfig()
        config.save = lambda path=None: root / "app.json"
        project = Project.create(root / "house", "海滨小屋")

        for code in ("en", "ja", "de", "fr", "ko", "zh-Hant"):
            i18n.set_language(code)
            window = MainWindow(config)
            window.resize(900, 600)
            window.show()
            application.processEvents()
            texts = visible_texts(window)
            leftover = [text for text in texts if text in MUST_TRANSLATE]
            check("%s：该换的都换了" % code, not leftover, str(leftover))
            check("%s：标题换成译文了" % code,
                  window.findChildren(QLabel)[0].text() != "快速导出")
            window.close()

        i18n.set_language("en")
        dialog = ExportRegionDialog(config)
        dialog.show()
        application.processEvents()
        texts = visible_texts(dialog)
        leftover = [text for text in texts if any("\u4e00" <= ch <= "\u9fff" for ch in text)]
        check("en：导出对话框里没有中文残留", not leftover, str(leftover[:3]))
        check("en：可选语言的下拉也是英文",
              dialog.mode.itemText(0) != "单区块",
              dialog.mode.itemText(0))
        check("en：本次范围摘要也是英文",
              "This export" in dialog.summary.text(), dialog.summary.text())
        dialog.close()

        # 项目界面与它那几个弹窗：这里最容易漏（分组标题不是 QLabel，
        # 早先 translate() 对 QGroupBox 先调 text() 直接抛异常，只有非中文界面才炸）
        project = Project.create(root / "house-en", "House")
        project.save_root = str(root)
        store = RecordStore(project.path)
        store.add(
            ExportRecord(
                id="2026-09-14_0000_c1_0_r1", kind="region", name="c1_0_r1",
                created_at="2026-09-14 00:00:00", output_dir="outputs/x",
                obj="outputs/x/m.obj", world="", dimension="overworld",
                chunks=[[1, 0]], faces=200, textures=[],
            )
        )
        cases = {
            "项目界面": lambda: ProjectWindow(project, config, root),
            "项目配置弹窗": lambda: _ProjectConfigDialog(project, lambda: None),
            "备份弹窗": lambda: _BackupsDialog(project),
            "保留策略弹窗": lambda: _RetentionDialog(project),
            "搜区块记录": lambda: _ChunkSearchDialog(project, store, None, (1, 0, "overworld")),
            "素材管理": lambda: MaterialManagerDialog(root),
            "清空数据": lambda: ResetDataDialog(root),
            "新建向导": lambda: NewProjectWizard(config, root / "np"),
            "删除项目": lambda: DeleteProjectDialog(str(project.path), project),
        }
        for label, factory in cases.items():
            try:
                widget = factory()
                widget.resize(900, 600)
                widget.show()
                application.processEvents()
                texts = visible_texts(widget)
                leftover = [
                    text for text in texts
                    if any("\u4e00" <= ch <= "\u9fff" for ch in text)
                ]
                widget.close()
                error = ""
            except Exception as boom:      # noqa: BLE001 - 自检要的就是"别抛"
                leftover, error = [], repr(boom)
            check("en：%s 没有中文残留" % label, not leftover, str(leftover[:3]))
            check("en：%s 能打开" % label, not error, error)

        # 3) 未知代码安全退回
        i18n.set_language("klingon")
        check("未知语言退回简体中文", i18n.current() == "zh-Hans", i18n.current())
        check("退回后不做替换", i18n.tr("要做什么？") == "要做什么？")

        # 4) 跟随系统：认不出来的地区也要给一个合法代码
        check("system_language 给的是合法代码",
              i18n.system_language() in i18n.codes(), i18n.system_language())

    i18n.set_language("zh-Hans")
    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
