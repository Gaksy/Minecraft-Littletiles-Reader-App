"""中文（非 ASCII）路径自检：存档目录、素材包、输出目录、结构文件全用中文。

补这条是因为它曾经整条链路都崩过——Windows 上 ``std::filesystem::path(std::string)``
按 ANSI 码页解释字节，而库从 job JSON 里拿到的是 UTF-8：中文存档目录被判成
"不存在"，``chunks_found`` 直接是 0，输出的贴图目录还会变成乱码名（``ä¸­æ–‡``）。
这类问题"看一眼"(文件名对不对)就会发现，但只看退出码永远发现不了，所以落成自检。

不依赖 pytest，直接 ``python tests/test_unicode_paths.py``。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.job import (  # noqa: E402
    build_region_job,
    build_snbt_job,
    chunks_field,
    default_options,
    write_job,
)
from ltgen import paths  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name, "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def extract_region(source: Path, target: Path) -> Path | None:
    """把 region 测试数据（目录或 zip）复制成 ``target/region/*.mca``。

    刻意多包一层 ``region/``：这样库走的是"存档根目录 + 维度"那条规则，
    而不是"传进来的就是 region 目录"的兜底规则——前者才是用户实际选的东西。
    """
    region_dir = target / "region"
    region_dir.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        for mca in source.glob("*.mca"):
            shutil.copy2(mca, region_dir / mca.name)
    elif source.is_file() and source.suffix == ".zip":
        with tempfile.TemporaryDirectory(prefix="lt-cn-region-") as unpack:
            with zipfile.ZipFile(source) as archive:
                archive.extractall(unpack)
            for mca in Path(unpack).rglob("*.mca"):
                shutil.copy2(mca, region_dir / mca.name)
    if not any(region_dir.glob("*.mca")):
        return None
    return target


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


def run_job(executable: Path, job_path: Path) -> tuple[int, dict, dict]:
    """跑一次库 CLI，返回 (退出码, done 事件, start 事件)。"""
    result = subprocess.run(
        [str(executable), "--job", str(job_path), "--progress", "json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    events = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    done = next((e for e in events if e.get("event") == "done"), {})
    start = next((e for e in events if e.get("event") == "start"), {})
    return result.returncode, done, start


def check_products(out_dir: Path, name: str, label: str) -> None:
    """输出目录里应当是"干净"的中文名，而不是乱码或丢文件。"""
    obj = out_dir / ("%s.obj" % name)
    texture_dir = out_dir / ("%s_textures" % name)
    mtl = out_dir / ("%s.mtl" % name)
    check("%s：OBJ 文件名正确" % label, obj.is_file(), str(obj))
    check(
        "%s：贴图目录名正确" % label,
        texture_dir.is_dir() and any(texture_dir.glob("*.png")),
        str(texture_dir),
    )
    check("%s：MTL 文件名正确" % label, mtl.is_file(), str(mtl))
    if not mtl.is_file():
        return
    # map_Kd 必须是相对路径：绝对路径写进 MTL，模型一挪地方就全断
    lines = [
        line.split(" ", 1)[1].strip()
        for line in mtl.read_text(encoding="utf-8").splitlines()
        if line.startswith("map_Kd ")
    ]
    check(
        "%s：map_Kd 是相对路径" % label,
        bool(lines) and all(":" not in line[:3] for line in lines),
        lines[0] if lines else "(没有 map_Kd)",
    )


def main() -> int:
    print("== 中文路径自检 ==")
    executable = paths.reader_executable()
    if not executable.is_file():
        print("  [跳过] 找不到库 CLI：%s" % executable)
        return 0
    data_root = paths.data_root()
    region_source = find_region_source(data_root)
    # pack_snbt 只有 1MB 出头：复制一份到中文目录当"中文素材包"足够便宜
    assets_source = data_root / "assets" / "pack_snbt"
    if region_source is None or not assets_source.is_dir():
        print("  [跳过] 缺少测试数据：%s / %s" % (region_source, assets_source))
        return 0

    with tempfile.TemporaryDirectory(prefix="lt-cn-") as temp:
        temp_dir = Path(temp)
        assets = temp_dir / "素材包·中文"
        shutil.copytree(assets_source, assets)

        print("中文存档目录 + 中文素材包 + 中文输出目录：")
        world = extract_region(region_source, temp_dir / "我的存档")
        check("准备好中文存档目录", world is not None, str(world))
        if world is None:
            print("失败 %d 项" % len(FAILURES))
            return 1

        out_dir = temp_dir / "导出输出" / "我的模型"
        job = build_region_job(
            world_root=str(world),
            dimension="overworld",
            chunks=chunks_field("center", x=0, z=0, radius=1),
            assets_package=str(assets),
            output_dir=str(out_dir),
            output_name="中文模型",
            options=default_options(),
        )
        job_path = write_job(job, temp_dir / "job" / "region.json")
        code, done, start = run_job(executable, job_path)
        check("子进程正常结束", code == 0, "exit=%d" % code)
        check("读到了存档里的区块", done.get("chunks_found", 0) > 0 and not done.get("chunks_missing", 1),
              "found=%s missing=%s" % (done.get("chunks_found"), done.get("chunks_missing")))
        check("素材包被认下来（有材质）", done.get("materials", 0) > 0, str(done.get("materials")))
        check("开始的 world 路径就是中文路径", start.get("world") == str(world), str(start.get("world")))
        check_products(out_dir, "中文模型", "存档导出")

        print("中文结构文件 + 中文输出目录：")
        snbt_dir = data_root / "snbt" / "test_snbt"
        snbt_file = snbt_dir / "CoronaSign.txt"
        if not snbt_file.is_file():
            print("  [跳过] 没有 %s" % snbt_file)
        else:
            structure_dir = temp_dir / "结构"
            structure_dir.mkdir(parents=True, exist_ok=True)
            structure = structure_dir / "中文结构.txt"
            shutil.copy2(snbt_file, structure)
            snbt_out = temp_dir / "结构输出"
            job = build_snbt_job(
                snbt_path=str(structure),
                assets_package=str(assets),
                output_dir=str(snbt_out),
                output_name="中文结构",
                options=default_options(),
            )
            job_path = write_job(job, temp_dir / "job" / "snbt.json")
            code, done, _ = run_job(executable, job_path)
            check("子进程正常结束", code == 0, "exit=%d" % code)
            check("结构被解析出了网格", done.get("meshes", 0) > 0, str(done.get("meshes")))
            check_products(snbt_out, "中文结构", "结构导出")

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
