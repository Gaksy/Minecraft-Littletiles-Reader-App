"""M2 项目界面：数据层 + 离屏界面 + 一次真实的项目导出。

不依赖 pytest，直接 `python tests/test_project_ui.py`。
真实导出那一段需要 `data/regions` 与 `data/assets/pack_snbt`（没有就跳过），
用离屏 Qt（`QT_QPA_PLATFORM=offscreen`），不需要显示器。

重点验的不是"窗口能建出来"，而是这条链：

    项目导出 → 产物写进 outputs/<时间戳>_<名字> → job.json 留在产物目录
    → 贴图按哈希收进 <项目>/textures → MTL 的 map_Kd 指过去 → 记录进 records/
    → 查区块能查到"已导出"，存档改过之后变"可能已过期"
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.job import build_region_job, chunks_field, default_options, expand_chunks  # noqa: E402
from app.library import Library, Source  # noqa: E402
from app.project import Project  # noqa: E402
from app.project_assets import bound_library  # noqa: E402
from app.compose import order_fingerprint  # noqa: E402
from app.records import (  # noqa: E402
    ExportRecord,
    RecordStore,
    mca_stamp,
    region_file,
)
from app.retention import plan as retention_plan  # noqa: E402
from app.storage import categories, dir_size, human_size  # noqa: E402
from app.texture_library import absorb, library_path, orphans, prune  # noqa: E402
from app.ui import project_window as pwin  # noqa: E402
from app.ui.project_window import ProjectWindow  # noqa: E402
from ltgen import paths  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name, "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


# ---- 1. 记录与区块索引 ------------------------------------------------------


def test_records(tmp: Path) -> None:
    print("导出记录与区块索引：")
    project = Project.create(tmp / "records-demo", "记录演示")
    store = RecordStore(project.path)
    world = tmp / "世界"
    (world / "region").mkdir(parents=True)
    mca = world / "region" / "r.0.0.mca"
    mca.write_bytes(b"region" * 100)

    record = ExportRecord(
        id="2026-09-14_0100_c0_0",
        kind="region",
        name="c0_0",
        created_at="2026-09-14 01:00:00",
        output_dir="outputs/2026-09-14_0100_c0_0",
        world=str(world),
        dimension="overworld",
        chunks=[[0, 0]],
        mca_stamps={"r.0.0.mca": mca_stamp(mca)},
    )
    store.add(record)
    store.save()

    reloaded = RecordStore(project.path)
    check("记录能读回来", len(reloaded.records) == 1 and reloaded.by_id(record.id) is not None)
    check("单条记录文件也写了", (project.path / "records" / ("%s.json" % record.id)).is_file())

    state, found = reloaded.chunk_state(world, "overworld", 0, 0)
    check("刚导出过 → 已导出", state == "fresh" and found is not None, state)
    check("没导过的区块 → 未导出", reloaded.chunk_state(world, "overworld", 5, 5)[0] == "missing")
    check("别的世界不算同一个区块",
          reloaded.chunk_state(tmp / "另一个世界", "overworld", 0, 0)[0] == "missing")

    # 存档被改过（mtime 变了）→ 可能已过期
    time.sleep(0.01)
    mca.write_bytes(b"region" * 200)
    os.utime(mca, (time.time() + 5, time.time() + 5))
    state, _ = reloaded.chunk_state(world, "overworld", 0, 0)
    check("存档改过 → 可能已过期", state == "stale", state)
    check("区域文件的算法对得上", region_file(world, "overworld", 33, 1).name == "r.1.0.mca")

    # 删记录：只删记录本身，产物目录要留下来
    output = project.path / record.output_dir
    output.mkdir(parents=True, exist_ok=True)
    (output / "house.obj").write_text("v 0 0 0\n", encoding="utf-8")
    reloaded.remove([record.id])
    check("删掉记录后查不到了", RecordStore(project.path).records == [])
    check("产物目录没被动", output.is_dir())


# ---- 2. 体积统计 ------------------------------------------------------------


def test_storage(tmp: Path) -> None:
    print("体积统计：")
    project = Project.create(tmp / "storage-demo", "体积演示")
    (project.path / "outputs" / "a").mkdir(parents=True)
    (project.path / "outputs" / "a" / "model.obj").write_bytes(b"x" * 3000)
    (project.path / "textures" / "ab").mkdir(parents=True)
    (project.path / "textures" / "ab" / "abcdef.png").write_bytes(b"p" * 1000)
    (project.path / "inputs" / "saves").mkdir(parents=True, exist_ok=True)
    (project.path / "inputs" / "saves" / "b.zip").write_bytes(b"z" * 2000)

    items = categories(project.path)
    by_key = {item.key: item.size for item in items}
    check("导出目录统计到了", by_key.get("outputs") == 3000, str(by_key.get("outputs")))
    check("贴图库统计到了", by_key.get("textures") == 1000)
    check("存档备份统计到了", by_key.get("backups") == 2000)
    check("顺序按大小降序", [i.size for i in items] == sorted([i.size for i in items], reverse=True))
    check("空类别不出现", all(item.size > 0 for item in items))
    check("单位换算", human_size(1536) == "1.5 KB" and human_size(2048) == "2.0 KB")
    check("目录大小 == 文件大小之和", dir_size(project.path / "outputs") == 3000)


# ---- 3. 贴图库（按哈希收、去重、改写 map_Kd） --------------------------------


def test_texture_library(tmp: Path) -> None:
    print("项目贴图库：")
    project = Project.create(tmp / "tex-demo", "贴图演示")
    out_dir = project.path / "outputs" / "2026-09-14_0100_house"
    staging = out_dir / "house_textures"
    staging.mkdir(parents=True)
    (staging / "blocks_stone.png").write_bytes(b"PNG-A" * 100)
    (staging / "blocks_dirt.png").write_bytes(b"PNG-B" * 50)
    # 第二次导出写出的同名内容（哈希一样 → 应当被丢弃而不是再存一份）
    (staging / "blocks_stone_copy.png").write_bytes(b"PNG-A" * 100)
    obj = out_dir / "house.obj"
    obj.write_text("mtllib house.mtl\nv 0 0 0\n", encoding="utf-8")
    mtl = out_dir / "house.mtl"
    mtl.write_text(
        "newmtl blocks_stone\nmap_Kd house_textures/blocks_stone.png\n"
        "newmtl blocks_dirt\nmap_Kd house_textures/blocks_dirt.png\n",
        encoding="utf-8",
    )

    digests = absorb(project.path, obj)
    check("内容相同的贴图只留一份", len(digests) == 2, str(digests))
    check("贴图按哈希进了库", all(library_path(project.path, d).is_file() for d in digests))
    check("临时目录已清掉", not staging.exists())

    text = mtl.read_text(encoding="utf-8")
    check("map_Kd 指到贴图库", "../../textures/" in text, text.splitlines()[1])
    check("map_Kd 不再指向已删掉的临时目录", "house_textures/" not in text)

    store = RecordStore(project.path)
    store.add(
        ExportRecord(
            id=out_dir.name, kind="region", name="house",
            created_at="2026-09-14 01:00:00",
            output_dir="outputs/2026-09-14_0100_house",
            textures=digests,       # 记录必须列全 MTL 用到的贴图，否则"清理孤儿"会删错
        )
    )
    check("被引用的贴图不算孤儿", orphans(project.path, store.records) == [])
    check("没有记录就等于全都算孤儿", len(orphans(project.path, [])) == 2)
    # 手动塞一张没有任何记录引用的贴图
    stray = library_path(project.path, "f" * 40)
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"stray")
    check("没人引用的那张算孤儿", len(orphans(project.path, store.records)) == 1)
    removed, freed = prune(project.path, store.records)
    check("清理只删没人引用的那张", removed == 1 and freed == 5, "removed=%d freed=%d" % (removed, freed))
    check("被引用的还在", all(library_path(project.path, d).is_file() for d in digests))


# ---- 4. 离屏界面结构 --------------------------------------------------------


def test_retention(tmp: Path) -> None:
    print("保留策略：")
    from datetime import datetime

    records = [
        ExportRecord(
            id="r%d" % i, kind="region", name="r%d" % i,
            created_at="2026-09-%02d 01:00:00" % (10 + i), output_dir="outputs/r%d" % i,
        )
        for i in range(4)
    ]
    sizes = {"r0": 100, "r1": 200, "r2": 300, "r3": 400}

    check("默认什么都不清", retention_plan(records, sizes=sizes).is_empty)

    plan = retention_plan(records, keep=2, sizes=sizes)
    check("只保留最近 2 次 → 删最旧的两个", plan.victims == ["r0", "r1"], str(plan.victims))
    check("算出能释放多少", plan.freed == 300, str(plan.freed))
    check("理由写得出来", "只保留最近 2 次" in plan.render())

    plan = retention_plan(
        records, max_days=5, sizes=sizes, now=datetime(2026, 9, 16, 12, 0, 0)
    )
    check("超过 5 天 → 删更早的那两次",
          plan.victims == ["r0", "r1"], str(plan.victims))
    plan = retention_plan(
        records, max_days=30, sizes=sizes, now=datetime(2026, 9, 20, 12, 0, 0)
    )
    check("都在期限内 → 不删", plan.is_empty)

    megabyte = 1024 * 1024
    plan = retention_plan(records, max_size_mb=3, sizes={k: megabyte for k in sizes})
    check("4 MB 限 3 MB → 从最旧的腾一个", plan.victims == ["r0"], str(plan.victims))
    plan = retention_plan(records, max_size_mb=2, sizes={k: megabyte for k in sizes})
    check("4 MB 限 2 MB → 腾两个才够", plan.victims == ["r0", "r1"], str(plan.victims))

    plan = retention_plan(records, keep=3, max_size_mb=2, sizes={k: megabyte for k in sizes})
    check("多条规则一起命中不会重复计",
          sorted(plan.victims) == ["r0", "r1"], str(plan.victims))


def test_export_dialog_grid(tmp: Path) -> None:
    """导出对话框里的预览网格：哪些区块导过，导出那一刻就该看见（§6）。"""
    print("导出对话框的区块预览：")
    from app.ui.export_dialog import ExportRegionDialog

    world = tmp / "世界"
    (world / "region").mkdir(parents=True)
    (world / "region" / "r.0.0.mca").write_bytes(b"x" * 100)
    config = AppConfig()
    config.save = lambda path=None: tmp / "app.json"

    def provider(_world, _dimension, x, z):
        if (x, z) == (0, 0):
            return "fresh", "导出于 2026-09-14 01:00:00"
        return "missing", ""

    dialog = ExportRegionDialog(
        config, None, initial_save=str(world), state_provider=provider
    )
    dialog.mode.setCurrentIndex(2)      # center
    dialog.radius.setValue(1)
    dialog.show()
    QApplication.instance().processEvents()
    grid = dialog.state_grid
    check("预览网格显示出来了", grid.isVisible())
    check("对话框认得出这是个合法存档", dialog.save_status.text().startswith("✓"),
          dialog.save_status.text())
    check("中心那块是已导出", grid.cells.get((0, 0), ("", ""))[0] == "fresh",
          str(grid.cells.get((0, 0))))
    check("旁边的块是未导出", grid.cells.get((1, 1), ("", ""))[0] == "missing")
    check("3×3 的范围没被截断", grid.truncated is False)
    dialog.radius.setValue(40)          # 81×81 → 只画左上角
    dialog._sync()
    check("范围过大时标注被截断", grid.truncated is True)
    dialog.close()

    plain = ExportRegionDialog(config)
    plain.show()
    QApplication.instance().processEvents()
    check("快速导出不画网格（没有索引可用）", not plain.state_grid.isVisible())
    check("并说明原因", "项目模式" in plain.grid_legend.text())
    plain.close()


def test_save_inspection(tmp: Path) -> None:
    """选错存档目录的表现是"导出 0 个区块"，很难自查——所以要当场说清楚。"""
    print("存档目录检查：")
    from app.savefolder import inspect

    good = tmp / "存档A"
    (good / "region").mkdir(parents=True)
    (good / "level.dat").write_bytes(b"x")
    for name in ("r.0.0.mca", "r.0.1.mca"):
        (good / "region" / name).write_bytes(b"x")
    result = inspect(good)
    check("正常存档 → 认下来", result.ok and result.mca_count == 2, result.message)
    check("说清楚有几个 .mca", "2 个 .mca" in result.message)

    inner = inspect(good / "region")
    check("选到 region/ 里面 → 提示往上退一层",
          not inner.ok and "往上退一层" in inner.hint, inner.hint)

    saves = tmp / "saves"
    (saves / "存档B" / "region").mkdir(parents=True)
    (saves / "存档B" / "level.dat").write_bytes(b"x")
    outer = inspect(saves)
    check("选到 saves/ 这一层 → 指出大概想选哪个",
          not outer.ok and "存档B" in outer.hint, outer.hint)

    check("空目录 → 不算存档", not inspect(tmp).ok)
    check("不存在的路径 → 直接说", not inspect(tmp / "没有这个").ok)
    check("维度对不上就没区块", inspect(good, "nether").mca_count == 0)


def test_retention_ui(tmp: Path) -> None:
    print("按策略清理（离屏）：")
    project = Project.create(tmp / "retention-demo", "保留演示")
    store = RecordStore(project.path)
    for index in range(4):
        out_dir = project.path / "outputs" / ("2026-09-1%d_0100_r%d" % (index, index))
        out_dir.mkdir(parents=True)
        (out_dir / "a.obj").write_bytes(b"x" * 1000)
        store.add(
            ExportRecord(
                id=out_dir.name, kind="region", name="r%d" % index,
                created_at="2026-09-%02d 01:00:00" % (10 + index),
                output_dir="outputs/%s" % out_dir.name,
            )
        )
    project.keep_exports = 2
    project.save()

    config = AppConfig()
    config.save = lambda path=None: tmp / "app.json"
    window = ProjectWindow(project, config, tmp, None)
    window.show()
    QApplication.instance().processEvents()

    plan = window._retention_plan()
    check("策略算出要清两次", len(plan.victims) == 2, str(plan.victims))
    check("界面上提示了可清理", "可清理 2 次" in window.retention_label.text(),
          window.retention_label.text())

    window._apply_retention(plan)
    survivors = RecordStore(project.path).records
    check("记录只剩 2 条", len(survivors) == 2, str(len(survivors)))
    check("最旧的两个产物目录被删了",
          not (project.path / "outputs" / "2026-09-10_0100_r0").exists()
          and not (project.path / "outputs" / "2026-09-11_0100_r1").exists())
    check("新的两个还在",
          (project.path / "outputs" / "2026-09-12_0100_r2").is_dir()
          and (project.path / "outputs" / "2026-09-13_0100_r3").is_dir())
    check("历史表跟着刷新了", window.history.rowCount() == 2)
    window.close()


def test_window(tmp: Path) -> None:
    print("项目界面（离屏）：")
    project = Project.create(tmp / "window-demo", "界面演示")
    project.description = "看看长什么样"
    project.save()
    # 造一份备份，验证"管理备份"能看到它
    save_root = tmp / "某个存档"
    save_root.mkdir(parents=True, exist_ok=True)
    (save_root / "level.dat").write_bytes(b"level")
    project.backup_save(save_root, note="演示")
    config = AppConfig()
    config.save = lambda path=None: tmp / "app.json"      # 别写进仓库
    window = ProjectWindow(project, config, tmp, None)
    window.resize(1000, 820)
    window.show()
    QApplication.instance().processEvents()

    for name in ("btn_export_region", "btn_export_snbt", "btn_backup", "btn_query",
                 "btn_recompose", "btn_backups", "btn_rebuild", "btn_retention",
                 "storage_bar", "storage_legend", "history"):
        check("有 %s" % name, hasattr(window, name))
    check("备份被列出来了", "已备份 1 次" in window.backup_label.text(),
          window.backup_label.text())
    check("存档备份打进 zip 了", len(project.backups()) == 1 and project.backups()[0].is_file())
    check("没有素材时提示白模", "白模" in window.package_status.text(),
          window.package_status.text())
    check("内容没有溢出（不出现整页横向滚动）",
          window.minimumSizeHint().width() < 900, str(window.minimumSizeHint().width()))
    check("没有素材时不给「重新组合」", window.btn_recompose.isEnabled() is False)
    window.close()


# ---- 5. 真实导出（需要测试数据 + 库 CLI） ------------------------------------


class _FakeRegionDialog:
    """替掉导出对话框：测试要的是它返回的那份 job，不是对话框本身。"""

    DialogCode = QDialog.DialogCode
    world = ""          # 由测试在调用前设好（真实对话框这里是用户选的存档）

    def __init__(self, *_args, **kwargs) -> None:
        from PySide6.QtWidgets import QLineEdit

        self.save_edit = QLineEdit(kwargs.get("initial_save") or self.world)

    def exec(self) -> int:
        return QDialog.DialogCode.Accepted

    def selection(self):
        return expand_chunks("center", x=0, z=0, radius=1)

    def output_name(self) -> str:
        return "c0_0_r1"

    def result_job(self, *, assets_package: str, output_dir: str) -> dict:
        return build_region_job(
            world_root=self.save_edit.text().strip(),
            dimension="overworld",
            chunks=chunks_field("center", x=0, z=0, radius=1),
            assets_package=assets_package,
            output_dir=output_dir,
            output_name="c0_0_r1",
            options=default_options(),
        )


def find_region_source(data_root: Path) -> Path | None:
    regions = data_root / "regions"
    if not regions.is_dir():
        return None
    for entry in sorted(regions.iterdir()):
        if entry.is_dir() and any(entry.glob("*.mca")):
            return entry
    for entry in sorted(regions.glob("*.zip")):
        return entry
    return None


def test_real_export(tmp: Path, seen: list[tuple[str, str, str]]) -> None:
    print("项目里真实导出一遍：")
    executable = paths.reader_executable()
    data_root = paths.data_root()
    region_source = find_region_source(data_root)
    package_source = data_root / "assets" / "pack_snbt"
    if not executable.is_file() or region_source is None or not package_source.is_dir():
        print("  [跳过] 缺少库 CLI 或测试数据（%s）" % executable)
        return

    # 世界（存档根目录 + region/）
    world = tmp / "我的世界"
    (world / "region").mkdir(parents=True)
    if region_source.is_dir():
        for mca in region_source.glob("*.mca"):
            shutil.copy2(mca, world / "region" / mca.name)
    else:
        with zipfile.ZipFile(region_source) as archive:
            archive.extractall(tmp / "unpacked")
        for mca in (tmp / "unpacked").rglob("*.mca"):
            shutil.copy2(mca, world / "region" / mca.name)

    # 素材库：放一条"原版"登记（内容不真用，组合结果直接放进项目里，走复用那条路）
    app_dir = tmp / "app"
    (app_dir / "resources").mkdir(parents=True)
    fake_source_dir = app_dir / "resources" / "sources" / "testvanilla"
    fake_source_dir.mkdir(parents=True)
    library = Library(
        sources=[
            Source(id="testvanilla", name="测试原版", kind="vanilla", path=str(fake_source_dir))
        ],
        enabled=["testvanilla"],
    )
    library.save(app_dir)

    project = Project.create(tmp / "项目·导出", "导出演示")
    (project.path / "package").mkdir(parents=True, exist_ok=True)
    shutil.copytree(package_source, project.path / "package", dirs_exist_ok=True)
    project.materials = ["testvanilla"]
    project.save_root = str(world)
    bound = bound_library(project, library)
    project.package_fingerprint = order_fingerprint(bound)   # 让 ensure_package 复用项目里这份
    project.save()

    config = AppConfig()
    config.save = lambda path=None: tmp / "app.json"
    config.ask_open_output = False        # 离屏模式下那个对话框会等人点
    window = ProjectWindow(project, config, app_dir, None)
    window.resize(1000, 820)
    window.show()
    QApplication.instance().processEvents()

    _FakeRegionDialog.world = str(world)
    pwin.ExportRegionDialog = _FakeRegionDialog     # type: ignore[assignment]
    try:
        window._export_region()
    finally:
        pwin.ExportRegionDialog = __import__(
            "app.ui.export_dialog", fromlist=["ExportRegionDialog"]
        ).ExportRegionDialog

    loop = QEventLoop()
    window.panel.finished_ok.connect(lambda *_: loop.quit())
    QTimer.singleShot(120_000, loop.quit)      # 兜底：别把测试永远挂着
    if window.panel.runner.is_running:
        loop.exec()
    QApplication.instance().processEvents()

    store = RecordStore(project.path)
    check("写了记录", len(store.records) == 1, str(len(store.records)))
    if not store.records:
        window.close()
        return
    record = store.records[0]
    out_dir = project.path / record.output_dir
    check("产物目录按时间戳建的", out_dir.is_dir() and record.id == out_dir.name, record.id)
    check("OBJ 在", (project.path / record.obj).is_file() if record.obj else False, record.obj)
    check("job.json 留在产物目录", (out_dir / "job.json").is_file())
    check("贴图进了项目贴图库",
          bool(record.textures) and all(library_path(project.path, d).is_file() for d in record.textures),
          "%d 张" % len(record.textures))
    check("临时贴图目录没留下", not any(out_dir.glob("*_textures")))
    mtl = (project.path / record.obj).with_suffix(".mtl")
    text = mtl.read_text(encoding="utf-8") if mtl.is_file() else ""
    check("MTL 的 map_Kd 指向贴图库", "../../textures/" in text)
    check("记了 9 个区块", len(record.chunks) == 9, str(len(record.chunks)))

    state, found = store.chunk_state(world, "overworld", 0, 0)
    check("查 (0,0) → 已导出", state == "fresh" and found is not None, state)
    state, _ = store.chunk_state(world, "overworld", 8, 8)
    check("查没导的区块 → 未导出", state == "missing", state)

    # 存档被改过 → 可能已过期
    target = region_file(world, "overworld", 0, 0)
    with target.open("ab") as handle:
        handle.write(b"\0" * 4096)
    state, _ = store.chunk_state(world, "overworld", 0, 0)
    check("存档改过 → 可能已过期", state == "stale", state)

    keys = [c.key for c in categories(project.path)]
    check("体积统计里有导出与贴图", "outputs" in keys and "textures" in keys, str(keys))

    # ---- 贴图丢了能不能重建（§7.6：清理是安全的，丢的是算力能买回来的东西）----
    print("重建贴图：")
    victim = record.textures[0]
    library_path(project.path, victim).unlink()
    check("先弄丢一张贴图", not library_path(project.path, victim).is_file())
    window.history.selectRow(0)
    window._rebuild_selected()
    rebuild_loop = QEventLoop()
    window.panel.finished_ok.connect(lambda *_: rebuild_loop.quit())
    QTimer.singleShot(120_000, rebuild_loop.quit)
    if window.panel.runner.is_running:
        rebuild_loop.exec()
    QApplication.instance().processEvents()

    check("重建后贴图回到库里", library_path(project.path, victim).is_file())
    rebuilt = RecordStore(project.path).by_id(record.id)
    check("记录还在", rebuilt is not None)
    check("记录里的贴图清单没缺",
          rebuilt is not None
          and all(library_path(project.path, d).is_file() for d in rebuilt.textures),
          str(len(rebuilt.textures) if rebuilt else 0))
    tmp_dir = project.path / "tmp"
    check("重建的临时目录没留下",
          not tmp_dir.exists() or not any(tmp_dir.iterdir()))
    window.close()


def install_modal_guards() -> list[tuple[str, str, str]]:
    """离屏模式下模态框会一直等人点——换成替身，顺便记录问了什么。

    没有这一层，测试遇到一个意料之外的弹窗就会**永远挂着**（不是失败），
    排查起来比报错费劲得多。
    """
    from PySide6.QtWidgets import QMessageBox

    seen: list[tuple[str, str, str]] = []

    def record(kind: str):
        def _handler(_parent, title, text, *_args, **_kwargs):
            seen.append((kind, str(title), str(text)))
            return {
                "warning": QMessageBox.StandardButton.Ok,
                "information": QMessageBox.StandardButton.Ok,
                "question": QMessageBox.StandardButton.Yes,
            }[kind]

        return staticmethod(_handler)

    QMessageBox.warning = record("warning")
    QMessageBox.information = record("information")
    QMessageBox.question = record("question")
    return seen


def main() -> int:
    print("== M2 项目界面自检 ==")
    QApplication([])
    seen = install_modal_guards()
    with tempfile.TemporaryDirectory(prefix="lt-projui-") as tmp:
        root = Path(tmp)
        test_records(root / "t1")
        test_storage(root / "t2")
        test_texture_library(root / "t3")
        test_retention(root / "t4a")
        test_retention_ui(root / "t4b")
        test_export_dialog_grid(root / "t4c")
        test_save_inspection(root / "t4d")
        test_window(root / "t4")
        test_real_export(root / "t5", seen)
    print("弹窗：")
    warnings = [item for item in seen if item[0] == "warning"]
    check("真实导出过程中没有弹警告", not warnings, str(warnings))
    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
