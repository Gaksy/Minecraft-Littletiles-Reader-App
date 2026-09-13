"""项目数据层：建目录、存盘读回、时间戳产物目录、素材副本。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.project import CONFIG_NAME, LAYOUT_DIRS, Project  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name, "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    print("== 项目数据层 ==")
    with tempfile.TemporaryDirectory(prefix="lt-proj-") as tmp:
        root = Path(tmp)
        project = Project.create(root / "house", "海滨小屋")

        check("project.json 写出来了", (project.path / CONFIG_NAME).is_file())
        for child in LAYOUT_DIRS:
            check("目录 %s 在" % child, (project.path / child).is_dir())

        project.description = "给朋友看的版本"
        project.materials = ["aaa", "bbb"]
        project.save()
        loaded = Project.load(project.path)
        check("读回能对上", loaded is not None and loaded.name == "海滨小屋")
        check("描述与素材顺序都保住了",
              loaded.description == "给朋友看的版本" and loaded.materials == ["aaa", "bbb"])
        check("create 记了创建时间", bool(loaded.created_at))

        check("不是项目目录时返回 None", Project.load(root) is None)

        # 时间戳产物目录：同一分钟内连开三次不能互相覆盖
        first = project.next_output_dir("c0_0_r1")
        second = project.next_output_dir("c0_0_r1")
        third = project.next_output_dir("c0_0_r1")
        check("三次产物目录互不相同",
              len({first.name, second.name, third.name}) == 3,
              " / ".join(p.name for p in (first, second, third)))
        check("后两次带序号", second.name.endswith("_2") and third.name.endswith("_3"))
        check("都建出来了", all(p.is_dir() for p in (first, second, third)))

        # 名字里的非法字符要被换掉（英文名 + 中文名都不该产生非法目录）
        weird = project.next_output_dir("SHB_05 Contemporary/1.1")
        check("非法字符被替换", "/" not in weird.name and " " not in weird.name, weird.name)
        chinese = project.next_output_dir("结构:花盆")
        check("中文名也能生成目录", chinese.is_dir(), chinese.name)

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
