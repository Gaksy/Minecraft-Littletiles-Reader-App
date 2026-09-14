# 许可证审计（发布前必读）

> 结论先放这儿：**你自己的代码可以继续用 MIT，但只要发布那个"读了 CGAL"的
> 可执行文件，它就必须按 GPL-3.0-or-later 发布**（或者买 CGAL 商业许可）。
> 只发 Python 应用、把 reader 留在服务器上跑，则不受这条约束。
> 下面是逐项证据。

## 1. 实际用了什么（按证据，不按印象）

| 组件 | 版本 | 许可证 | 证据 |
|---|---|---|---|
| 应用自身代码（`app/` `ltgen/` `tools/`） | — | **MIT** | `LICENSE` |
| 库自身代码（`Galib/` `main.cpp`） | — | **MIT** | `LICENSE`（另一个仓库） |
| PySide6 / Qt | 6.11（pip wheel） | **LGPL-3.0**（另有 GPL/商业） | pip 包元数据；动态链接 |
| Fusion Pixel 字体 | 12px mono | **OFL-1.1** | `app/resources/fonts/OFL.txt`（已随包） |
| CGAL · Kernel / `Vector_3.h` | 6.2.1 | LGPL-3.0-or-later OR 商业 | 头文件 SPDX：`LGPL-3.0-or-later OR LicenseRef-Commercial` |
| **CGAL · `Surface_mesh` / `Polygon_mesh_processing` / `Point_set_3`** | 6.2.1 | **GPL-3.0-or-later** OR 商业 | 头文件 SPDX：`GPL-3.0-or-later OR LicenseRef-Commercial` |
| libnbt++（PrismLauncher 分支，commit `687e4303`） | — | **LGPL-3.0-or-later** | 上游 `README.md` 的 SPDX 行 + `COPYING.LESSER`；本项目**动态链接**（`otool -L` 里是 `libnbt++.dylib`） |
| Boost | 1.85 / 1.92 | BSL-1.0（宽松） | 头文件为主；实测二进制未链接 Boost 库 |
| zlib | 1.3.x | zlib license（宽松） | 静态链接进二进制 |
| GMP / MPFR | — | 未使用 | `otool -L` 里没有（用的是不精确内核） |
| Minecraft 原版贴图 / 模型 / jar | — | 版权归 Mojang，**不可分发** | 仓库内没有任何 `.jar` / 原版贴图；由用户自备 |
| LittleTiles 模组本体 | — | LGPL-3.0 | 只**读取**它产生的数据；仓库内不含模组 jar |

关键的一行是加粗那条：库里的
`Galib/include/Minecraft/CgalSupport/CgalTypeDef.h` 直接
`#include <CGAL/Surface_mesh/Surface_mesh.h>` 与 `<CGAL/Point_set_3.h>`，
`CgalLtSupport.cpp` 又 include 了 `<CGAL/Polygon_mesh_processing/repair.h>`——
这三个包在 CGAL 6.2.1 里是 **GPL-3.0-or-later**（不是 LGPL）。
头文件被编译进二进制 = 该二进制是 GPL 代码的衍生作品。

## 2. 三种发布形态，各自要做什么

### 形态 A：只发 Python 应用，reader 在服务器上跑（**推荐，也是你现在的方向**）

- 分发给用户的是 MIT 应用 + PySide6（LGPL，动态链接）；
- 用户请求你的服务器，服务器内部跑那个 GPL 的 reader，**只把 OBJ/GLB 结果还回去**；
- GPL 的义务是"**分发二进制**"时触发，**提供服务不触发**（AGPL 才会管网络服务，
  而你本来就是版权方，不存在"要求你开源"的问题）；
- 需要做的：随包附 `THIRD-PARTY.md`（本仓库已加）、应用里保留 Qt 的 LGPL 声明、
  别把 reader 二进制塞进安装包。

### 形态 B：把 reader 一起打包下载（M5 现在的设想）

- 整个**分发包**必须按 GPL-3.0-or-later 合规：
  - 附 GPL-3.0 全文（`LICENSE-GPL-3.0.txt`）；
  - 提供 reader 的**完整源码**（或书面要约），指向你的公开仓库即可——你现在就是开源的，这一条几乎零成本；
  - 保留 CGAL / libnbt++ / Boost / zlib 的声明与许可文本；
  - **不能**声明"本软件整体为 MIT"；你自己的文件仍是 MIT（MIT 与 GPL 兼容），
    但分发包整体按 GPLv3 走，且不得对 GPL 部分附加额外限制；
  - libnbt++ 保持**动态链接**（现在是 `.dylib`/`.dll`，符合 LGPL 的可替换要求）。
- 一句话：**能发，但下载页要写清"含 GPL-3.0 组件"并给出源码链接**。

### 形态 C：坚持整个产品 MIT（不想要 GPL 义务）

只有两条路：

1. **买 CGAL 商业许可**（GeometryFactory）——之后 CGAL 部分不再触发 GPL；
2. **把 CGAL 从 reader 里拿掉**：
   - `Surface_mesh` → 换成自己的网格容器（你已经在用半空间裁剪做交集，
     几何核心其实不依赖 CGAL 的布尔）；
   - `Polygon_mesh_processing::remove_degenerate_faces` / `remove_isolated_vertices`
     → 这两个规则很简单，自己写几十行；
   - `Point_set_3` → 看用途（采样/点云），多半可以去掉；
   - 只留 LGPL 的内核头文件时，二进制就不再被 GPL 传染（LGPL 允许用于闭源/其它许可，
     条件是保留声明、且可替换）。

## 3. 发布前清单

- [ ] 仓库里**没有**原版贴图 / 原版模型 / 客户端 jar（已确认：两个仓库都没有）
- [ ] 仓库里**没有** LittleTiles 模组 jar（已确认没有；如果将来为了方便用户而内置，要按 LGPL 附源码链接）
- [ ] 应用里保留 `app/resources/fonts/OFL.txt`（OFL 要求随字体一起分发许可文本）
- [ ] 分发包里放 `THIRD-PARTY.md`（本仓库已加，含 Qt/CGAL/libnbt++/Boost/zlib 的声明模板）
- [ ] 按发布形态决定：形态 A 只需上面的；形态 B 追加 GPL-3.0 全文 + 源码链接
- [ ] 下载页 / 关于对话框里写清授权（形态 B 时**不要**写"整体 MIT"）
- [ ] 如果以后把 reader 静态链接 libnbt++，要额外满足 LGPL 的"可重新链接"要求
      （提供目标文件或可重链接形式）——现在没这个负担

## 4. 与网站（inception-work）相关的两点

- 站点上"客户端下载"如果放的是形态 B 的打包，发布说明里要带上 GPL 声明与源码链接；
- 素材仓库（`recourse-temp/`）现在只有图标，没有原版资源，不动它就没问题；
  将来若在站内存放原版贴图或客户端 jar，那是**另一套**授权问题（Mojang EULA），
  与本次审计无关，但别混在一起发。

## 5. 这条结论与平台无关（ARM / x86 / Windows 都一样）

GPL 的触发点是**源码 include 了哪些 CGAL 包**，不是 CPU 架构，也不是包管理器：

- `Galib/CMakeLists.txt:47` 在**所有平台**都链 `CGAL::CGAL`（没有 `TARGET CGAL::CGAL`
  时退到 `${CGAL_LIBRARIES}`）；
- 被 include 的是 `Surface_mesh` / `Polygon_mesh_processing` / `Point_set_3`
  —— 这三个在 CGAL 6.2.1 里都是 `GPL-3.0-or-later`；
- CGAL 在这里是**头文件为主**（macOS 上 `otool -L` 看不到任何 CGAL dylib），
  也就是说 GPL 代码是**编进二进制**的——这正是"二进制必须 GPL"的原因，
  换成 Windows + vcpkg + MSVC 也是同一回事。

所以：**Apple 芯片 / x86 / Windows 三个包，授权结论完全一致**，要么 GPL-3.0-or-later，
要么买 CGAL 商业许可，要么把 CGAL 拿掉。网站上的两个下载平台（`windows` /
`macos-arm`）在这一点上不需要区别对待。

### 换成平台**会**变的只有这些（都不影响上面的结论）

| 事项 | macOS（已验证） | Windows（建议自查一次） |
|---|---|---|
| libnbt++ | 动态链 `libnbt++.dylib`（`otool -L` 确认）→ LGPL 无碍 | `CMakeLists.txt:79-84` 会把 `nbt++.dll` 拷到 exe 旁边 → 也是动态，同样无碍；**别改成静态链** |
| GMP / MPFR | 没链（`otool -L` 里没有）——因为用的是不精确内核 | vcpkg 的 CGAL 端口依赖 gmp/mpfr；若它们被**静态**链进 exe，就要额外满足 LGPL 的声明与"可重新链接"要求。自查：`dumpbin /dependents LittleTilesReader.exe`，看到 `gmp*.dll` / `mpfr*.dll` 就是动态（省事），没看到就可能是静态链入 |
| Qt（PySide6） | `.app` 里是动态 framework | 打包后是 Qt 的 `.dll`；两者都满足 LGPL，但**分发包里要带 LGPL 文本**，且不要静态链接 Qt |
