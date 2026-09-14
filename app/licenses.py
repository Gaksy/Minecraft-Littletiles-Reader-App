"""许可协议：应用自身是 MIT，但**分发包里还有别人的代码**，用户必须知情并同意。

第一次启动（打包版）会让用户在看完清单与全文之后点「同意并继续」，不同意就直接退出。
同意过一次就不再打扰；但**协议集合变了要重新问**——所以有一个
`LICENSE_SET_VERSION`，改动组件或许可时把它加一。

为什么放在首次启动而不是"安装时"：macOS 的 .app 是拖拽安装，根本没有安装器；
Windows 的便携 zip 同理。首次启动是这个分发包唯一能拦住用户、让他确实读到的时机。

文本来源优先级（都能读就都列出来）：

1. 随包的 `licenses/*.txt`、`LICENSE`、`THIRD-PARTY.md`（打包脚本会拷进包）；
2. 开发环境里就是仓库根的那几份文件（同一批文件，路径不同而已）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import bundle_root

#: 协议集合的版本：**改动组件或许可文本时加一**，用户会重新看到同意弹窗
LICENSE_SET_VERSION = 1


@dataclass(frozen=True)
class Component:
    """一个需要用户知情的组件。"""

    name: str
    license_name: str
    scope: str        # 应用本体 / 只在使用"含库的完整包"时
    notice: str       # 一句话：它是什么、我们来干什么用的


#: 清单（顺序即界面顺序：先自己的，再第三方的）
COMPONENTS: tuple[Component, ...] = (
    Component("LittleTiles Reader（本应用自身代码）", "MIT", "app",
              "应用与生成端由本项目独立开发，源码在 GitHub 上公开。"),
    Component("PySide6 / Qt 6", "LGPL-3.0", "app",
              "桌面界面框架，动态链接使用；你有权替换 Qt 库。"),
    Component("Fusion Pixel 字体", "SIL OFL-1.1", "app",
              "界面像素字体，随包分发（保留字体名，未做修改）。"),
    Component("CGAL", "GPL-3.0-or-later", "reader",
              "几何计算库——因为编译进了导出器，**这个分发包整体按 GPL-3.0 分发**。"),
    Component("libnbt++", "LGPL-3.0-or-later", "reader",
              "读写 Minecraft NBT 数据，动态链接使用。"),
    Component("Boost", "BSL-1.0", "reader",
              "C++ 基础库（文件流、JSON）。"),
    Component("zlib", "zlib License", "reader",
              "解压存档与素材包里的压缩数据。"),
)

#: 全文文件（相对包根；缺失的会被跳过）
TEXT_FILES: tuple[tuple[str, str], ...] = (
    ("LICENSE", "LittleTiles Reader · MIT"),
    ("THIRD-PARTY.md", "第三方组件总览"),
    ("licenses/GPL-3.0.txt", "GNU GPL v3"),
    ("licenses/LGPL-3.0.txt", "GNU LGPL v3"),
    ("licenses/BSL-1.0.txt", "Boost Software License 1.0"),
    ("licenses/zlib.txt", "zlib License"),
    # 字体许可跟着字体走（app/resources 会随包），根目录那份是拷贝给用户看的
    ("app/resources/fonts/OFL.txt", "SIL Open Font License 1.1"),
)


def texts() -> list[tuple[str, str]]:
    """可展示的全文：`[(标题, 内容)]`，找不到的文件自动跳过。"""

    roots = [bundle_root()]
    # macOS 的 .app 里，Frameworks（= 解包目录）与 Resources 是兄弟目录；
    # 打包脚本把许可放在 Contents/Resources/，所以两边都要找。
    sibling = bundle_root().parent / "Resources"
    if sibling.is_dir():
        roots.append(sibling)
    found: list[tuple[str, str]] = []
    for relative, title in TEXT_FILES:
        for root in roots:
            path = root / relative
            if not path.is_file():
                path = root / "packaging" / relative   # 开发环境：仓库里的同一份
            if not path.is_file():
                continue
            try:
                found.append((title, path.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
            break
    return found


def summary() -> str:
    """清单的纯文本版（日志与"关于"里也能用）。"""

    lines = ["本应用自身以 MIT 发布；同时包含下列第三方组件：", ""]
    for item in COMPONENTS:
        lines.append("· %s —— %s" % (item.name, item.license_name))
        lines.append("    %s" % item.notice)
    lines.append("")
    lines.append("完整许可文本见应用目录下的 LICENSE / THIRD-PARTY.md / licenses/。")
    return "\n".join(lines)


def accepted(config) -> bool:
    """用户是否已经同意**当前这一版**协议集合。"""

    return int(getattr(config, "licenses_version", 0) or 0) >= LICENSE_SET_VERSION


def accept(config) -> None:
    """记下同意（版本 + 时间），并落盘。"""

    config.licenses_version = LICENSE_SET_VERSION
    config.licenses_accepted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config.save()
