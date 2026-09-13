"""来源解析：目录 / zip / jar 三种真实文件各测一遍。

jar 那条用你机器上真实的 1.12.2 客户端 jar —— 它就是"用户从自己游戏里
提取原版素材"的入口，必须能认出来。
"""

from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.sources import is_archive, resolve_source  # noqa: E402
from ltgen import paths  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name, "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    print("== 来源解析 ==")
    data = paths.data_root()
    with tempfile.TemporaryDirectory(prefix="lt-src-") as tmp:
        work = Path(tmp) / "work"
        work.mkdir()

        # 1) 目录直接可用
        plain = Path(tmp) / "plain"
        (plain / "sub").mkdir(parents=True)
        (plain / "sub" / "r.0.0.mca").write_bytes(b"x")
        result = resolve_source(plain, work, marker="*.mca")
        check("目录：穿过嵌套找到含 .mca 的那层", result.path == plain / "sub", str(result.path))
        check("目录：没有被标记为解压", result.extracted is False)

        # 2) zip（用你测试数据里的真实 zip，里面是多层结构）
        region_zip = next(iter(sorted((data / "regions").glob("*.zip"))), None)
        if region_zip is not None:
            result = resolve_source(region_zip, work, marker="*.mca")
            count = len(list(result.path.glob("*.mca")))
            check("zip：解压并定位到 .mca 所在目录", count > 0, "%s（%d 个 .mca）" % (result.path.name, count))
            check("zip：被标记为解压", result.extracted is True)
            check("zip：说明文字可用于日志", "解压" in result.note, result.note)

        # 3) 自制：包内多套一层文件夹
        nested_zip = Path(tmp) / "nested.zip"
        with zipfile.ZipFile(nested_zip, "w") as zf:
            zf.writestr("wrapper/inner/block_textures.tsv", "x")
        result = resolve_source(nested_zip, work, marker="block_textures.tsv")
        check(
            "zip：多套一层也能找到 marker",
            result.path.name == "inner",
            str(result.path),
        )

        # 4) 越界路径必须拒绝（zip slip）
        evil = Path(tmp) / "evil.zip"
        with zipfile.ZipFile(evil, "w") as zf:
            zf.writestr("../escaped.txt", "x")
        try:
            resolve_source(evil, work)
            check("zip：拒绝越界路径", False, "居然没报错")
        except ValueError as error:
            check("zip：拒绝越界路径", "越界" in str(error))

        # 5) 不支持的类型要明确报错
        txt = Path(tmp) / "note.txt"
        txt.write_text("x", encoding="utf-8")
        try:
            resolve_source(txt, work)
            check("非压缩包给出明确错误", False)
        except ValueError as error:
            check("非压缩包给出明确错误", "只认" in str(error), str(error))

        # 6) 真实的 1.12.2 客户端 jar —— 原版素材的入口
        jar = Path(r"B:\Game\Minecraft for Windows\InceptionGN\.minecraft\versions\1.12.2\1.12.2.jar")
        if jar.is_file():
            check("is_archive 认得 .jar", is_archive(jar))
            result = resolve_source(jar, work, marker="assets/minecraft")
            blocks = result.path / "assets" / "minecraft" / "textures" / "blocks"
            count = len(list(blocks.glob("*.png"))) if blocks.is_dir() else 0
            # 目标根 = "含 assets/minecraft 的那层"，也就是 jar 的根
            check(
                "jar：定位到含 assets/minecraft 的那层",
                blocks.is_dir(),
                str(result.path),
            )
            check(
                "jar：方块贴图可用",
                count > 400,
                "%d 张 PNG（jar 的 500 个条目里含目录项，去掉后是这些）" % count,
            )
        else:
            check("真实 1.12.2 jar 存在", False, "跳过：%s" % jar)

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
