"""调用 `tools/` 下的生成脚本——**进程内**调用，不再 fork 一个 Python。

为什么必须改成进程内：打包成桌面应用后 `sys.executable` 是应用本身（不是解释器），
再拿它去跑 `.py` 只会把 GUI 又启动一遍——「导入资源包 / 模组」这两个功能在
打包版里会直接坏掉（`docs/packaging.md` §2.2 记的就是这条）。

两个脚本本身不用动逻辑：`tools/*.py` 会在导入时自己把仓库根与 `tools/` 塞进
`sys.path`，所以这里用 `importlib` 按文件路径加载即可；它们的命令行入口
（`main()` + argparse）保持原样，命令行用法完全不受影响。

输出处理：脚本是往 stdout 打中文进度的。应用是窗口程序（没有控制台），
所以这里把输出**收进日志**，出错时连同输出一起抛出来（和以前 subprocess
那版的行为一致：错误信息里带着脚本说了什么，方便定位）。
"""

from __future__ import annotations

import importlib.util
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from .applog import logger
from .config import bundle_root

_TOOLS = "tools"
_loaded: dict[str, object] = {}

#: 运行时会被加载的工具脚本（**单一事实来源**：自检与打包脚本都读这里）。
#: 打包时必须把这些脚本用到的模块显式收集，否则冻结版点下去才报
#: `No module named ltgen.console`（见 `app/selfcheck.py` 与 tools/build_app.py）。
TOOL_NAMES = ("add_mod_textures", "build_assets_from_pack", "resolve_block_textures")


def tool_path(name: str) -> Path:
    """`tools/<name>.py` 的实际位置（打包后在解包目录里）。"""

    return bundle_root() / _TOOLS / ("%s.py" % name)


def load_tool(name: str):
    """按文件路径加载一个脚本模块（缓存，避免重复执行模块级代码）。"""

    if name in _loaded:
        return _loaded[name]
    path = tool_path(name)
    if not path.is_file():
        raise FileNotFoundError(
            "找不到生成脚本 %s（打包时要把 tools/ 一起带上）" % path
        )
    spec = importlib.util.spec_from_file_location("ltr_tool_%s" % name, path)
    if spec is None or spec.loader is None:
        raise ImportError("加载不了 %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _loaded[name] = module
    return module


def _run(what: str, work):
    """跑一段生成逻辑，把脚本的输出收进日志；失败时带上输出一起抛。"""

    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer), redirect_stderr(buffer):
            result = work()
    except Exception as error:
        output = buffer.getvalue().strip()
        logger().error("%s失败：%s\n%s", what, error, output)
        raise RuntimeError("%s失败：\n%s\n%s" % (what, error, output)) from error
    for line in buffer.getvalue().splitlines():
        logger().info("[%s] %s", what, line)
    return result


def build_pack_assets(pack: str | Path, vanilla: str | Path, out: str | Path,
                      use_pack_models: bool = False) -> Path:
    """材质包 + 原版 → 可直接喂给 reader 的素材包目录。"""

    module = load_tool("build_assets_from_pack")
    _run(
        "生成素材包",
        lambda: module.build(pack, Path(vanilla), Path(out), use_pack_models),
    )
    return Path(out)


def build_pack_snbt(mod_roots, namespaces, base: str | Path, out: str | Path) -> Path:
    """原版 + 若干模组 → pack_snbt（SNBT 结构导出用）。"""

    module = load_tool("add_mod_textures")
    _run(
        "叠加模组素材",
        lambda: module.build_pack_snbt(
            [str(root) for root in mod_roots], list(namespaces), Path(base), Path(out)
        ),
    )
    return Path(out)
