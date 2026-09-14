# 第三方组件与许可（随包分发时带上这份）

本应用（LittleTiles Reader 桌面端）自身代码以 MIT 发布；它用到的第三方组件与
各自的许可如下。**发布前请按你选择的形态补齐对应许可文本**（见
[`docs/licenses.md`](docs/licenses.md) 的"三种发布形态"）。

## 应用本体（现在就要带上）

| 组件 | 许可 | 你要做的 |
|---|---|---|
| PySide6 / Qt 6 | LGPL-3.0（Qt 另有 GPL / 商业双授权） | 保持**动态链接**（pip wheel 与 PyInstaller 打包都是动态的）；随包附 LGPL-3.0 文本；说明用户可以替换 Qt 库 |
| Fusion Pixel 字体（`app/resources/fonts/`） | SIL OFL-1.1 | 随字体一起分发 `OFL.txt`（已在本仓库内，别删）；不得用其保留字体名 "Fusion Pixel" 发布改版字体 |

Qt 源码获取地址（LGPL 要求可获取）：<https://download.qt.io/official_releases/qt/>

## 只在你把 reader 一起打包时（形态 B）才需要

reader 那个可执行文件编译进了 CGAL 的 GPL 包，因此**分发包整体按
GPL-3.0-or-later 合规**，需要追加：

| 组件 | 许可 | 你要做的 |
|---|---|---|
| CGAL 6.2.1（`Surface_mesh` / `Polygon_mesh_processing` / `Point_set_3`） | **GPL-3.0-or-later**（另有商业许可） | 附 GPL-3.0 全文；提供源码（指向你的公开仓库即可）；下载页写清"含 GPL-3.0 组件" |
| CGAL 6.2.1（Kernel / `Vector_3`） | LGPL-3.0-or-later | 附 LGPL-3.0 文本 |
| libnbt++（PrismLauncher 分支 `687e4303`） | **LGPL-3.0-or-later** | 保持**动态链接**（现在是 `.dylib` / `.dll`）；附 LGPL-3.0 文本 |
| Boost（1.85 / 1.92） | BSL-1.0 | 附许可文本（宽松，无其它义务） |
| zlib | zlib license | 附许可文本（宽松，无其它义务） |

CGAL 源码与许可：<https://github.com/CGAL/cgal> ·
libnbt++：<https://github.com/PrismLauncher/libnbtplusplus> ·
Boost：<https://www.boost.org/LICENSE_1_0.txt> ·
zlib：<https://zlib.net/zlib_license.html>

## 不随包分发的东西（因此不需要在这里列）

- Minecraft 原版贴图 / 模型 / 客户端 jar：版权归 Mojang，本工具**不附带**，由用户自备；
- LittleTiles 模组本体：LGPL-3.0，本工具只是读取它产生的数据；
- 用户自己的存档与素材包。
