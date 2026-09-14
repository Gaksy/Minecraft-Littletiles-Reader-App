"""打包成 zip：OBJ + MTL + 这次真正用到的贴图，解压出来要能直接用。

要验的三件事：

1. 贴图进包、其它无关文件不进包（job.json 是本机路径，带出去没意义）；
2. MTL 里的 `map_Kd` 被改写成**包内**相对路径（`textures/<名字>`），
   所以在别处解压不用改任何东西；
3. 贴图文件丢了要如实报告缺哪张，而不是悄悄打一个用不了的包。
"""

from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.packaging import pack  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    print("== 打包成 zip ==")
    with tempfile.TemporaryDirectory(prefix="lt-pack-") as tmp:
        project = Path(tmp) / "项目"
        out = project / "outputs" / "2026-09-14_0000_c0_0_r1"
        library = project / "textures" / "ab"
        out.mkdir(parents=True)
        library.mkdir(parents=True)
        (library / "aaaa1111.png").write_bytes(b"png-a" * 32)
        (library / "bbbb2222.png").write_bytes(b"png-b" * 32)

        (out / "c0_0_r1.mtl").write_text(
            "newmtl m1\nmap_Kd ../../textures/ab/aaaa1111.png\n"
            "newmtl m2\nmap_Kd ../../textures/ab/bbbb2222.png\n"
            "newmtl m3\n",                       # 不贴图的材质：不该被算成缺图
            encoding="utf-8",
        )
        (out / "c0_0_r1.obj").write_text(
            "mtllib c0_0_r1.mtl\no cube\nv 0 0 0\nusemtl m1\nf 1 1 1\n",
            encoding="utf-8",
        )
        (out / "job.json").write_text('{"world": "D:/本机路径"}', encoding="utf-8")

        result = pack(out / "c0_0_r1.obj")
        check("zip 落在产物目录里",
              result.zip_path.parent == out and result.zip_path.suffix == ".zip",
              str(result.zip_path))
        check("包里有两个材质 / 两张贴图",
              result.materials == 1 and result.textures == 2,
              "%s / %s" % (result.materials, result.textures))
        check("没有缺图", result.missing == [], str(result.missing))

        with zipfile.ZipFile(result.zip_path) as archive:
            names = sorted(archive.namelist())
            check("包里是模型 + MTL + textures/",
                  names == ["c0_0_r1.mtl", "c0_0_r1.obj",
                            "textures/aaaa1111.png", "textures/bbbb2222.png"],
                  str(names))
            check("job.json 没进包", "job.json" not in names)
            mtl = archive.read("c0_0_r1.mtl").decode("utf-8")
            check("map_Kd 改成包内相对路径",
                  "map_Kd textures/aaaa1111.png" in mtl
                  and "../../textures" not in mtl,
                  mtl.replace("\n", " | "))
            obj = archive.read("c0_0_r1.obj").decode("utf-8")
            check("mtllib 指向包内的 MTL", "mtllib c0_0_r1.mtl" in obj)

        # 解包到别处（模拟"拷给别人"）：贴图要在包内找得到
        elsewhere = Path(tmp) / "别人的电脑"
        with zipfile.ZipFile(result.zip_path) as archive:
            archive.extractall(elsewhere)
        check("解压后贴图就在模型旁边",
              (elsewhere / "textures" / "aaaa1111.png").is_file())

        # 丢一张贴图：如实报告，而不是打一个用不了的包
        (library / "bbbb2222.png").unlink()
        broken = pack(out / "c0_0_r1.obj", zip_path=out / "缺图.zip")
        check("缺图会报出来", len(broken.missing) == 1 and "bbbb2222" in broken.missing[0],
              str(broken.missing))
        check("缺图时其余贴图照打", broken.textures == 1, str(broken.textures))

        # 模型不存在时报错清楚
        try:
            pack(out / "没有这个.obj")
            raised = ""
        except FileNotFoundError as error:
            raised = str(error)
        check("模型不在时说清楚", "找不到要打包的模型" in raised, raised)

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
