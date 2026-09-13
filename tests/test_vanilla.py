"""从真实的 1.12.2 客户端 jar 生成素材包，并用库校验它能不能吃。

这是"用户第一次用"的主路径：他手上只有游戏，没有我们的素材包格式。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.vanilla import BUNDLED_BLOCK_IDS, build_package_from_vanilla  # noqa: E402
from ltgen.lint import lint_package  # noqa: E402

JAR = Path(
    r"B:\Game\Minecraft for Windows\InceptionGN\.minecraft\versions\1.12.2\1.12.2.jar"
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name, "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    print("== 从客户端 jar 生成素材包 ==")
    check("随应用带的 block_ids.tsv 在", BUNDLED_BLOCK_IDS.is_file(), str(BUNDLED_BLOCK_IDS))
    if not JAR.is_file():
        check("真实 1.12.2 jar 存在", False, "跳过：%s" % JAR)
        return 1

    with tempfile.TemporaryDirectory(prefix="lt-vanilla-") as tmp:
        work = Path(tmp) / "work"
        out = Path(tmp) / "package"
        result = build_package_from_vanilla(JAR, work, out)

        report = lint_package(result.package_dir)
        check("素材包能通过库的 lint", report.ok, report.errors[0] if report.errors else "")
        check("方块数 455（与原版一致）", report.block_count == 455, str(report.block_count))
        check("贴图引用 301 张", report.texture_ref_count == 301, str(report.texture_ref_count))
        check("贴图缺失 0 张", not report.missing_textures)
        check(
            "block_ids.tsv 已补上（普通方块才能带贴图）",
            (result.package_dir / "block_ids.tsv").is_file(),
        )
        check(
            "不再有缺 block_ids 的告警",
            not any("block_ids" in w for w in report.warnings),
            "; ".join(report.warnings[:1]),
        )
        check(
            "block_ids 与本应用自带的一致",
            (result.package_dir / "block_ids.tsv").read_bytes()
            == BUNDLED_BLOCK_IDS.read_bytes(),
        )

        # 真的拿它跑一次导出：这是这条路的终点，必须能出图
        region_zip = sorted((ROOT.parent / "minecraft-littletiles-reader-data" / "data" / "regions").glob("*.zip"))
        if region_zip:
            region = Path(tmp) / "region"
            region.mkdir()
            import zipfile

            with zipfile.ZipFile(region_zip[0]) as zf:
                zf.extractall(region)
            job = {
                "schema": 1,
                "mode": "region",
                "input": {
                    "world": {"root": str(region), "dimension": "overworld"},
                    "chunks": {"mode": "center", "x": 0, "z": 0, "radius": 1},
                },
                "assets": {"package": str(result.package_dir)},
                "output": {"dir": str(Path(tmp) / "out"), "name": "t"},
                "options": {"plain_blocks": True, "cull_hidden_faces": True},
            }
            job_path = Path(tmp) / "job.json"
            import json

            job_path.write_text(json.dumps(job), encoding="utf-8")
            exe = ROOT.parent / "minecraft-littletiles-reader" / "cmake-build-debug" / "LittleTilesReader.exe"
            if exe.is_file():
                done = subprocess.run(
                    [str(exe), "--job", str(job_path), "--progress", "json"],
                    capture_output=True,
                    text=True,
                )
                last = (done.stdout or "").strip().splitlines()[-1]
                check("用它导出成功", done.returncode == 0, last)
                check(
                    "贴图真的写出来了（不是白模）",
                    "textures_written" in last and '"textures_written":0' not in last,
                    last,
                )
                check(
                    "普通方块也带上了贴图（block_ids 起作用）",
                    "materials" in last and '"materials":0' not in last,
                    last,
                )

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
