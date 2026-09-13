"""三个真实存档的端到端自检（应用契约 → 库 CLI → 产物）。

覆盖用户在客户端（InceptionGN）里指定的三份测试数据：

| 存档 | 区块坐标 | 半径 | 材质 |
|---|---|---|---|
| base（基准，复杂偏移方块） | 0, 0 | 1 | 原版材质 |
| escalator（扶梯，中等复杂度） | -136, 49 | 5 | Inception V1.4 |
| subway（地铁站，大量小方块） | -7, -26 | 5 | Inception V1.4 |

数据从 `ltgen.paths` 的数据根找（`LTR_DATA_ROOT` 或同级目录）：
`saves/<名字>` 或 `regions/<名字>.zip`；素材包在 `assets/pack_v14`（原版+资源包）。
缺数据就跳过，不判失败。

产物写到 `--out`（默认 `data/outputs/real_saves`），每个存档一份，带 job 与日志。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.job import build_region_job, chunks_field, default_options, write_job  # noqa: E402
from ltgen import paths  # noqa: E402

# 用户给的推荐参数
CASES = (
    ("base", 0, 0, 1),
    ("escalator", -136, 49, 5),
    ("subway", -7, -26, 5),
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def find_save(data_root: Path, name: str) -> Path | None:
    """找一份存档根（含 region/）；支持目录、`saves/<名字>` 与 `<名字>.zip`。"""

    for candidate in (
        data_root / "saves" / name,
        data_root / "regions" / name,
    ):
        if candidate.is_dir() and any(candidate.rglob("*.mca")):
            return candidate
    for candidate in (
        data_root / "regions" / (name + ".zip"),
        data_root / "saves" / (name + ".zip"),
    ):
        if candidate.is_file():
            return candidate
    return None


def materialise(source: Path, target: Path) -> Path | None:
    """把存档（目录或 zip）铺成 `target/region/*.mca`，返回存档根。"""

    region_dir = target / "region"
    region_dir.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        for mca in source.rglob("*.mca"):
            shutil.copy2(mca, region_dir / mca.name)
        level = source / "level.dat"
        if level.is_file():
            shutil.copy2(level, target / "level.dat")
    else:
        with tempfile.TemporaryDirectory(prefix="lt-save-") as unpack:
            with zipfile.ZipFile(source) as archive:
                archive.extractall(unpack)
            root = Path(unpack)
            for mca in root.rglob("*.mca"):
                shutil.copy2(mca, region_dir / mca.name)
            for level in root.rglob("level.dat"):
                shutil.copy2(level, target / "level.dat")
                break
    return target if any(region_dir.glob("*.mca")) else None


def run_case(name: str, chunk_x: int, chunk_z: int, radius: int,
             executable: Path, package: Path, out_root: Path, work: Path) -> None:
    print("\n%s（区块 %d,%d 半径 %d）：" % (name, chunk_x, chunk_z, radius))
    data_root = paths.data_root()
    source = find_save(data_root, name)
    if source is None:
        print("  [跳过] 找不到存档数据 %s" % name)
        return

    save_root = materialise(source, work / name)
    if save_root is None:
        check("%s：存档可用" % name, False, "铺开后没有 .mca")
        return
    check("%s：存档可用" % name, True, str(source))

    case_out = out_root / name
    case_out.mkdir(parents=True, exist_ok=True)
    job = build_region_job(
        world_root=str(save_root),
        dimension="overworld",
        chunks=chunks_field("center", x=chunk_x, z=chunk_z, radius=radius),
        assets_package=str(package),
        output_dir=str(case_out),
        output_name=name,
        options=default_options(),
    )
    job_path = work / ("%s.job.json" % name)
    write_job(job, job_path)

    started = time.monotonic()
    done = subprocess.run(
        # --progress json：与应用里的 runner 一样走 NDJSON，才能拿到 done 事件里的统计
        [str(executable), "--job", str(job_path), "--progress", "json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    seconds = time.monotonic() - started
    (case_out / "export.log").write_text(
        (done.stdout or "") + (done.stderr or ""), encoding="utf-8"
    )
    shutil.copy2(job_path, case_out / "job.json")

    check("%s：库正常结束" % name, done.returncode == 0, "exit=%s" % done.returncode)

    events = []
    for line in (done.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    summary = next((e for e in reversed(events) if e.get("event") == "done"), {})
    faces = summary.get("faces")
    obj = case_out / ("%s.obj" % name)
    check("%s：OBJ 写出来了" % name, obj.is_file(),
          "%.1f MB" % (obj.stat().st_size / 1024 / 1024) if obj.is_file() else "")
    if summary:
        print("      tile %s / 面 %s / 顶点 %s / 贴图 %s / 耗时 %.1f s"
              % (summary.get("tiles"), faces, summary.get("vertices"),
                 summary.get("textures_written"), seconds))
    check("%s：面数 > 0" % name, bool(faces))


def main() -> int:
    data_root = paths.data_root()
    package = data_root / "assets" / "pack_v14"
    executable = paths.reader_executable()
    out_root = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        data_root / "outputs" / "real_saves"
    )
    print("库 CLI: %s" % executable)
    print("素材包: %s" % package)
    print("产物  : %s" % out_root)
    if not executable.is_file() or not package.is_dir():
        print("[跳过] 缺库 CLI 或素材包")
        return 0

    with tempfile.TemporaryDirectory(prefix="lt-real-saves-") as work:
        for name, chunk_x, chunk_z, radius in CASES:
            run_case(name, chunk_x, chunk_z, radius, executable, package,
                     out_root, Path(work))

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
