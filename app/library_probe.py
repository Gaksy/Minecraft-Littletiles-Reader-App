"""问库要版本号——启动时直接问，不必先导出一次。

以前版本号只能从导出的 `start` 事件里拿到，所以没导出过就一直显示
"（本次还没导出过）"。其实库自己有 `--version`（输出两行：一行带名字的、
一行纯版本号），问一次几十毫秒，顺手还能确认"这个 CLI 真的能跑起来"。

拿的是**最后一行**（纯版本号 `0.2.0-beta`），和导出时 `start` 事件里的
`library` 字段是同一个值——两条路径不能让界面显示两种写法。

失败（文件不在、跑不起来、超时）一律返回空串，绝不让界面起不来。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .applog import logger

TIMEOUT = 10          # 版本号而已；十秒还没回来就当它不可用


def parse_version(output: str) -> str:
    """从 `--version` 的输出里取版本号：最后一行非空文本。"""

    lines = [line.strip() for line in (output or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def probe(cli: Path | str) -> str:
    """跑 `--version` 并返回版本号；问不到就返回空串。"""

    path = Path(cli)
    if not path.is_file():
        return ""
    try:
        done = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            timeout=TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger().warning("问库版本失败：%s（%s）", path, error)
        return ""
    text = (done.stdout or b"").decode("utf-8", "replace")
    if done.returncode != 0 or not text.strip():
        # 有的 CLI 会往 stderr 里说话；还是拿不到就当没有
        text = (done.stderr or b"").decode("utf-8", "replace")
    version = parse_version(text)
    if version:
        logger().info("库版本：%s（%s）", version, path)
    return version
