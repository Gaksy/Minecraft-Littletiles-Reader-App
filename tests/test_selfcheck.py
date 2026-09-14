"""冻结版自检（`--self-check`）：它自己得是对的，否则打包验收就没有守门人。

验三件事：

1. 开发环境下自检全过、退出码 0；
2. 某个运行时模块缺失时，它**必须**报失败并返回 1
   （v0.1.0 打包版真实坏在这：`No module named ltgen.console`）；
3. `--self-check` 真的接在入口上（跑一次真子进程，而不是只看代码）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app import selfcheck  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    print("== 冻结版自检 ==")

    check("开发环境全过", selfcheck.run() == 0)

    # 把 ltgen.console 变成"不存在"，自检必须拦住（sys.modules 里放 None 会让
    # import 直接抛 ImportError，等价于 PyInstaller 没收集这个模块）。
    saved = sys.modules.get("ltgen.console", "__missing__")
    sys.modules["ltgen.console"] = None
    try:
        blocked = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.modules['ltgen.console'] = None;"
             "from app.selfcheck import run; raise SystemExit(run())"],
            cwd=str(ROOT), capture_output=True, text=True,
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
        )
    finally:
        if saved == "__missing__":
            sys.modules.pop("ltgen.console", None)
        else:
            sys.modules["ltgen.console"] = saved

    check("缺模块时返回 1", blocked.returncode == 1, "退出码=%d" % blocked.returncode)
    check("缺模块时指出是谁", "ltgen.console" in (blocked.stdout + blocked.stderr))

    entry = subprocess.run(
        [sys.executable, "-m", "app", "--self-check"],
        cwd=str(ROOT), capture_output=True, text=True,
        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
    )
    check("入口 --self-check 可用", entry.returncode == 0,
          "退出码=%d" % entry.returncode)

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
