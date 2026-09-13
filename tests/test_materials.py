"""素材内容检视 + 自定义命名（P0 需求）。

不依赖 pytest，直接跑：
    python tests/test_materials.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.library import Library, import_source  # noqa: E402
from app.materials import inspect_source  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def make_source(root: Path, namespace: str = "demo") -> Path:
    """造一个资源包布局的来源：2 个 blockstate、2 个模型、1 张贴图（另 1 张缺失）。"""

    base = root / "assets" / namespace
    (base / "blockstates").mkdir(parents=True)
    (base / "models" / "block").mkdir(parents=True)
    (base / "textures" / "blocks").mkdir(parents=True)
    (base / "blockstates" / "stone.json").write_text(
        json.dumps({"variants": {"normal": {"model": "%s:stone" % namespace}}}),
        encoding="utf-8",
    )
    (base / "blockstates" / "dirt.json").write_text(
        json.dumps({"variants": {"normal": {"model": "%s:dirt" % namespace}}}),
        encoding="utf-8",
    )
    (base / "models" / "block" / "stone.json").write_text(
        json.dumps({"parent": "block/cube_all",
                    "textures": {"all": "%s:blocks/stone" % namespace}}),
        encoding="utf-8",
    )
    # 这个模型的贴图故意不落盘 —— 摘要里应算作 1 张缺失
    (base / "models" / "block" / "dirt.json").write_text(
        json.dumps({"parent": "block/cube_all",
                    "textures": {"all": "%s:blocks/dirt" % namespace}}),
        encoding="utf-8",
    )
    (base / "textures" / "blocks" / "stone.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return root


def test_inspect() -> None:
    print("内容摘要：")
    with tempfile.TemporaryDirectory(prefix="lt-mat-") as tmp:
        root = make_source(Path(tmp))
        summary = inspect_source(root)
        check("命名空间读到了", summary.namespaces == ("demo",), str(summary.namespaces))
        check("方块数 = 2（blockstates）", summary.blocks == 2, str(summary.blocks))
        check("模型数 = 2", summary.models == 2, str(summary.models))
        check("贴图数 = 1", summary.textures == 1, str(summary.textures))
        check("缺失 = 1（dirt）", summary.missing == ("demo:blocks/dirt",),
              str(summary.missing))
        text = summary.render()
        check("摘要里带缺失数量", "缺失 1" in text, text)

        empty = inspect_source(Path(tmp) / "nope")
        check("没有 assets/ 时是空的", empty.empty and "assets/" in empty.render())


def test_import_name() -> None:
    print("导入时自定义命名：")
    with tempfile.TemporaryDirectory(prefix="lt-mat-") as tmp:
        work = Path(tmp)
        archive = work / "SomePack_v1.4.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("pack.mcmeta", json.dumps({"pack": {"pack_format": 3}}))
            z.writestr("assets/demo/blockstates/stone.json", "{}")
            z.writestr("assets/demo/textures/blocks/stone.png", b"\x89PNG")

        app_dir = work / "app"
        (app_dir / "cache" / "sources").mkdir(parents=True)
        source = import_source(archive, app_dir, app_dir / "cache" / "sources",
                               name="我的材质包")
        check("用了自定义名字", source.name == "我的材质包", source.name)
        check("解压目录存在", Path(source.path).is_dir(), source.path)
        check("识别成资源包", source.kind == "resourcepack", source.kind)

        again = import_source(archive, app_dir, app_dir / "cache" / "sources")
        check("不给名字时退回文件名", again.name == "SomePack_v1.4", again.name)
        check("同一个文件指纹相同", again.id == source.id)


def test_manager_details() -> None:
    print("材质管理里显示内容摘要：")
    from PySide6.QtWidgets import QApplication

    from app.ui import design
    from app.ui.material_manager import MaterialManagerDialog

    application = QApplication.instance() or QApplication([])
    design.install(application, "dark")
    with tempfile.TemporaryDirectory(prefix="lt-mat-") as tmp:
        app_dir = Path(tmp) / "app"
        (app_dir / "resources" / "sources").mkdir(parents=True)
        # 把一个造好的来源直接登记进库，省掉解压
        source_dir = make_source(app_dir / "resources" / "sources" / "abc", "demo")
        library = Library.load(app_dir)
        from app.library import Source

        library.add(Source(id="abc", name="演示包", kind="resourcepack",
                           path=str(source_dir)))
        library.save(app_dir)

        dialog = MaterialManagerDialog(app_dir)
        check("列表里有一项", dialog.available.count() == 1)
        dialog.available.setCurrentRow(0)
        details = dialog.details.text()
        check("选中后给出了摘要",
              "方块 2" in details and "缺失 1" in details, details)
        dialog.close()


def main() -> int:
    test_inspect()
    test_import_name()
    test_manager_details()
    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
