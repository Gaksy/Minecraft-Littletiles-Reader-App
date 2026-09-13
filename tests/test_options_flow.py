"""复选框 → job → 日志 这条链路。

起因：用户反馈"普通方块"开关没生效，但库与应用各自单测都正常。
这里把整条链路钉住，并且把选项写进日志，下次一眼能看出用的到底是什么。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.ui.export_dialog import ExportRegionDialog  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name, "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    print("== 选项链路 ==")
    QApplication([])

    # 1) 默认值：第一次打开都是"开"
    dialog = ExportRegionDialog(AppConfig())
    default_job = dialog.result_job(assets_package="A", output_dir="B")
    check("首次打开：普通方块默认开", default_job["options"]["plain_blocks"] is True)

    # 2) 全部关掉后，job 必须如实反映
    for box in (dialog.plain_blocks, dialog.cull, dialog.center):
        box.setChecked(False)
    dialog.normalize.setChecked(True)
    job = dialog.result_job(assets_package="A", output_dir="B")
    check("关掉普通方块 → job 里为 false", job["options"]["plain_blocks"] is False)
    check("关掉剔除 → job 里为 false", job["options"]["cull_hidden_faces"] is False)
    check("关掉居中 → job 里为 false", job["options"]["center"] is False)
    check("打开单位缩放 → job 里为 true", job["options"]["normalize_scale"] is True)

    # 3) 下次打开沿用上次的选择（而不是回到默认值）
    remembered = ExportRegionDialog(AppConfig(), initial=job["options"])
    check(
        "第二次打开沿用上次：普通方块仍是关",
        remembered.plain_blocks.isChecked() is False,
    )
    check("第二次打开沿用上次：单位缩放仍是开", remembered.normalize.isChecked() is True)

    # 4) 日志里能看到选项，用户自查用
    config = AppConfig(ask_open_output=False)
    window = MainWindow(config)
    window._run({"mode": "region", "output": {"dir": str(ROOT / "tmp"), "name": "x"}, "options": job["options"]})
    text = window.log.toPlainText()
    check("日志里写了选项", "选项:" in text, text.splitlines()[-1] if text else "")
    check(
        "日志里写明了普通方块=否",
        "普通方块=否" in text,
    )
    window.runner.cancel()

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
