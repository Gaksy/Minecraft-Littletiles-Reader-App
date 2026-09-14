"""M1 自检：核心逻辑 + 离屏跑一次真实导出。

不依赖 pytest，直接 `python tests/test_m1.py`。
真实导出的部分用 `QT_QPA_PLATFORM=offscreen`，所以不需要显示器。
"""

from __future__ import annotations

import os
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# 数据目录指到临时目录：自检绝不能碰用户真实的 config/ 与 logs/
# （`data_dir()` 每次调用重新解析 LTR_HOME，所以在这里设就够了）
_LTR_HOME = tempfile.mkdtemp(prefix="lt-home-")
os.environ["LTR_HOME"] = _LTR_HOME

from app.job import (  # noqa: E402
    ExportProgress,
    build_region_job,
    chunks_field,
    default_options,
    expand_chunks,
    parse_event,
)
from ltgen import paths  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name, "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def find_region_data(data_root: Path) -> Path | None:
    """找一个能用的 region 目录。

    测试数据可能解压成目录，也可能打包成 zip 存放（现在的 `regions/` 就是
    base/escalator/subway 三个 zip），两种都支持；zip 里可能是**完整存档**
    （`.mca` 在 `region/` 子目录下）也可能只装了 region 文件，所以用 rglob 找。
    """
    regions = data_root / "regions"
    if not regions.is_dir():
        return None
    for entry in sorted(regions.iterdir()):
        if entry.is_dir() and any(entry.rglob("*.mca")):
            return entry
    for entry in sorted(regions.glob("*.zip")):
        target = Path(tempfile.mkdtemp(prefix="lt-region-")) / entry.stem
        with zipfile.ZipFile(entry) as archive:
            archive.extractall(target)
        # 完整存档：返回存档根（库会自己拼 region/）；只有 region 文件：返回它本身
        if any((target / "region").glob("*.mca")):
            return target
        if any(target.glob("*.mca")):
            return target
    return None


def test_chunk_expansion() -> None:
    print("区块选择三种模式：")
    single = expand_chunks("single", x=3, z=-5)
    check("single -> 1 格", single.total == 1 and single.cells() == [(3, -5)])

    center = expand_chunks("center", x=0, z=0, radius=1)
    check("center r=1 -> 3x3", center.total == 9 and center.min_x == -1)

    ranged = expand_chunks("range", x1=1, z1=2, x2=1, z2=4)
    check("range 1x3（非正方）", (ranged.count_x, ranged.count_z, ranged.total) == (1, 3, 3))

    flipped = expand_chunks("range", x1=5, z1=5, x2=2, z2=3)
    check("range 端点倒着给也对", (flipped.min_x, flipped.min_z, flipped.count_x, flipped.count_z) == (2, 3, 4, 3))


def test_event_parsing() -> None:
    print("进度事件解析：")
    check("空行忽略", parse_event("   ") is None)
    check("非 JSON 忽略", parse_event("chunks: 9 found") is None)
    check("缺 event 字段忽略", parse_event('{"foo":1}') is None)
    event = parse_event('{"event":"chunk","index":2,"total":9,"x":0,"z":-1}')
    check("正常事件", event is not None and event["index"] == 2)

    progress = ExportProgress()
    for line in (
        '{"event":"assets","blocks":455,"textures":301,"missing":0}',
        '{"event":"start","mode":"region","chunks":9}',
        '{"event":"chunk","index":1,"total":9}',
        '{"event":"warning","message":"素材包缺少 1 张贴图"}',
        '{"event":"done","faces":4940,"obj":"x.obj"}',
    ):
        progress.apply(parse_event(line))
    check("折叠出总数与进度", progress.total == 9 and progress.percent == 100)
    check("保留素材统计", progress.assets.get("blocks") == 455)
    check("收集警告", progress.warnings == ["素材包缺少 1 张贴图"])
    check("保留结果", progress.result.get("faces") == 4940)


def test_gui_export() -> None:
    """真的起一次子进程：这是 M1 的闭环，不能只测逻辑。"""
    print("离屏跑一次真实导出：")
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from app.config import AppConfig
    from app.ui.main_window import MainWindow

    data_root = paths.data_root()
    assets = data_root / "assets" / "pack_v14"
    region = find_region_data(data_root)
    if not assets.is_dir() or region is None:
        check("找到测试数据", False, "跳过：素材包 %s 或 region 数据缺失" % assets)
        return
    check("找到测试数据", True, "%s / %s" % (assets.name, region.name))

    application = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="lt-m1-") as tmp:
        config = AppConfig(
            library_cli=str(paths.reader_executable()),
            default_assets=str(assets),
            # 关掉"导出完成后询问是否打开目录"：离屏模式下那个对话框会真的等人点，
            # 测试就会一直挂着。
            ask_open_output=False,
        )
        window = MainWindow(config)
        out_dir = Path(tmp) / "out"
        job = build_region_job(
            world_root=str(region),           # 测试数据没有 level.dat，走"root 即 region 目录"
            dimension="overworld",
            chunks=chunks_field("center", x=0, z=0, radius=1),
            assets_package=str(assets),
            output_dir=str(out_dir),
            output_name="m1_smoke",
            options=default_options(),
        )
        loop = QEventLoop()
        outcome: dict = {}

        def finished(ok: bool, code: int) -> None:
            outcome["ok"] = ok
            outcome["code"] = code
            loop.quit()

        window.runner.finished.connect(finished)
        window._run(job)
        QTimer.singleShot(180_000, loop.quit)   # 兜底：别把测试挂死
        loop.exec()

        check("子进程正常结束", outcome.get("ok") is True, "exit=%s" % outcome.get("code"))
        obj = out_dir / "m1_smoke.obj"
        check("OBJ 写出来了", obj.is_file(), str(obj))
        check(
            "面数与基线一致（4940）",
            window.progress.result.get("faces") == 4940,
            str(window.progress.result.get("faces")),
        )
        check(
            "贴图写出来了",
            (out_dir / "m1_smoke_textures").is_dir(),
            str(out_dir / "m1_smoke_textures"),
        )
    del application


def main() -> int:
    print("== M1 自检 ==")
    test_chunk_expansion()
    test_event_parsing()
    test_gui_export()
    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
