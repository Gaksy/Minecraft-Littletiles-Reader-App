# 打包方案（M5）· 评审稿

> 状态（2026-09-14 更新）：**方案已落地一部分**——
> ✅ 可写数据目录（`data_dir()` + `LTR_HOME`，§2.1）、
> ✅ 两个生成脚本改为进程内调用（§2.2，打包后不再 fork Python）、
> ✅ 构建信息（`app/_buildinfo.py`，冻结后"关于"里能看到提交号，§2.4）、
> ✅ 构建脚手架（`tools/build_app.py` + `packaging/`，§7 的命令已固化）。
> ⏳ 仍待办：图标（`packaging/app.ico` / `app.icns`）、第一次真机构建、
> CI（可选）、以及表末"待你拍板"的 5 项（形态 / 安装模式 / 平台 / 签名 / 图标）。

## 1. 目标

- 产出**两个可下载的包**：`windows-x64` 与 `macos-arm64`（与服务器
  `lt_read_download` 里预置的两个平台键一一对应）；
- 用户下载 → 解压 → 双击就能用（不要求装 Python、不要求命令行）；
- 与已做好的「检查更新 / 反馈问题」衔接：构建产物上传后，后台填版本号与地址即可。

暂不做：Linux、自动安装更新（只提示 + 跳下载页）、商店上架（Microsoft Store / Mac App Store）。

## 2. 先说四个**阻塞项**：动手前必须解决

### 2.1 运行时数据目录（最关键）

现在配置、日志、产物、素材库都写在 `APP_DIR`——即**代码目录**
（`app/config.py` 的 `APP_DIR = Path(__file__).resolve().parents[1]`）。
冻结成应用后，这个目录会变成：

| 打包形态 | `APP_DIR` 实际指向 | 结果 |
|---|---|---|
| PyInstaller **onedir** + 用户解压到任意可写目录 | 解压出来的文件夹 | ✅ 便携可用 |
| PyInstaller onedir 装到 `Program Files` / `/Applications` | 安装目录 | ❌ 无写权限（日志、配置、产物全写不进去） |
| PyInstaller **onefile** | 临时解包目录 | ❌ 更糟：配置与日志每次运行都丢 |

**方案**：引入"数据目录"概念，优先级

1. 命令行 `--home <dir>`（给高级用户/多份并存）；
2. 环境变量 `LTR_HOME`；
3. 默认可写就用 **exe 所在目录**（便携模式，和现在行为一致）；
4. 不可写则退到用户目录：Windows `%LOCALAPPDATA%\LittleTilesReader`、
   macOS `~/Library/Application Support/LittleTilesReader`，首次启动时提示一句
   "数据放在 <路径>"。

改动范围：`APP_DIR` 变成启动时解析一次的函数（`app/paths.py`），
其余 20 多处引用跟着换；`appdata.clear()` 的边界也随之明确（只清数据目录，不碰安装目录）。

### 2.2 两个"调用自己解释器跑脚本"的地方，冻结后会失效

```
app/vanilla.py:104   sys.executable tools/build_assets_from_pack.py   ← 资源包 → 素材包
app/mods.py:81       sys.executable tools/add_mod_textures.py        ← 模组 → 素材包
```

冻结后 `sys.executable` 是**应用自己**（不是 Python），再拿它去跑 `.py` 只会把 GUI 又启动一遍。
两条路：

| 方案 | 做法 | 代价 |
|---|---|---|
| **A（推荐）改成进程内调用** | 把这两个脚本的 `main()` 抽成 `ltgen/` 里的函数，应用直接 import 调用（和 `compose` 一样） | 一次小重构（两个脚本，各约 100–200 行），顺带去掉"解析 stdout 文本"的脆弱耦合 |
| B 保留子进程 | 给应用加一个隐藏入口（`LittleTilesReaderApp --run-tool build_assets_from_pack ...`），冻结时用 `sys.executable` 自己调自己 | 改动小，但要维护隐藏 CLI；参数透传与错误上报仍走 stdout |

`app/sources.py` 里用 `unar`/`unrar` 解 **rar** 的那条路是查 `PATH` 的外部命令，
冻结后依旧"找不到就没有 rar 支持"（现在已有的提示会照旧显示）——
方案：发布说明里写明"rar 支持需要系统装了 unar/unrar"，不为此打包额外二进制。

### 2.3 reader 的位置与授权

- 现在找 CLI 的顺序在 `ltgen/paths.py:reader_executable()`：`LTR_LIBRARY` 环境变量 →
  同级 `../minecraft-littletiles-reader/cmake-build-debug/LittleTilesReader`；
- 冻结后没有"同级仓库"，必须显式：**先在 exe 同目录找 `LittleTilesReader(.exe)`，再退回配置里的 `library_cli`**；
- **授权**：一旦把 reader 打进包，整包按 GPL-3.0-or-later 合规（见
  [`licenses.md`](licenses.md)）；不打包（reader 留服务器）则应用仍是 MIT。
  这条直接决定下面第 3 节的形态选择。

### 2.4 版本与提交号

冻结后没有 `.git`，`_git_revision()` 只会返回"未知"（`app/ui/main_window.py:131`，已有兜底不会崩）。
方案：构建时写一个 `app/_buildinfo.py`（`BUILD_COMMIT` / `BUILD_TIME` / `BUILD_PLATFORM`），
"关于"对话框优先读它——出问题时能一眼对上"用户装的是哪一次构建"。

## 3. 两种发布形态（**请你选一个**）

| | 形态 A：瘦客户端（推荐） | 形态 B：离线一体包 |
|---|---|---|
| 包内容 | 只有 Python 应用 | 应用 **+** `LittleTilesReader` |
| 导出怎么算 | 请求服务器（或用户自己指定 CLI 路径） | 本地算 |
| 授权 | MIT（+ Qt 的 LGPL 声明） | **整包 GPL-3.0-or-later**（附 GPL 全文 + 源码链接） |
| 体积 | ~90 MB | +3–8 MB（reader 本体）+ 依赖 |
| 离线可用 | ❌ | ✅ |
| 与网站的关系 | 完全吻合"在线解析 + 3D 展示"的方向 | 适合"我想本地批量导"的用户 |

> 也可以**两个都发**：官网给"在线版（瘦客户端）"和"离线版（含 reader，GPL）"两个下载按钮，
> 后者在发布说明里写清 GPL。服务器两张下载卡片正好两个平台键，但**每个平台只能配一条**，
> 所以若都要发布，建议再加两个平台键（`windows-offline` / `macos-arm-offline`）——
> 这是服务端一行配置的事（`PLATFORM_NAMES`）。

## 4. 工具选型

| 工具 | 适配 PySide6 | 产物 | 启动速度 | 结论 |
|---|---|---|---|---|
| **PyInstaller（onedir）** | Qt 官方文档承认的组合，hook 成熟 | 文件夹 + 可执行 | 快 | **推荐**：排除项可控、CI 简单、onedir 便于"便携 + 可写数据目录" |
| PyInstaller（onefile） | 同样成熟 | 单文件 | 每次解包，慢 1–3 s | ❌ 不推荐：数据目录会落在临时目录（见 2.1），AV 误报也更多 |
| Nuitka | 支持，但要编译 C，构建慢 | 文件夹/单文件 | 最快 | 备选：将来想再压体积/防反编译时再上 |
| briefcase | 能直接出安装包（MSI/DMG） | 安装包 | 同 PyInstaller | 备选：想要"安装向导"体验时考虑 |
| cx_Freeze | 一般 | 文件夹 | 快 | 不优先（PySide6 hook 不如 PyInstaller） |

## 5. 产物布局（形态 A，Windows 便携 zip 为例）

```
LittleTilesReader-0.2.0-windows-x64/
├── LittleTilesReader.exe          # 入口（无控制台窗口）
├── _internal/                     # PyInstaller 运行时：Qt 的 dll、python311.dll、字体…
├── data/                          # 数据目录（便携模式就写在这里）
│   ├── config/app.json            #   设置、项目登记、检查更新时间
│   ├── logs/                      #   会话日志 + logs/reports/ 反馈留档
│   ├── outputs/                   #   快速导出产物
│   ├── resources/sources/         #   导入的素材包
│   └── cache/
├── LICENSE                        # 你的 MIT
└── THIRD-PARTY.md                 # 第三方声明（Qt LGPL / 字体 OFL；形态 B 还要 GPL）
```

macOS 是同样的结构包在 `LittleTilesReader.app/Contents/` 里，`data/` 放 `Contents/Resources/data`
并在首次启动提示"数据在 ~/Library/Application Support/LittleTilesReader"（.app 内不可写）。

## 6. 体积估算（按实测数字推）

| 项 | 体积 |
|---|---|
| QtCore + QtGui + QtWidgets | 41 MB（12 + 17 + 12） |
| Qt 插件（platforms 2.3 + imageformats 4.2 + iconengines/styles ~0.4） | ~7 MB |
| shiboken6 | 1.4 MB |
| Python 3.11 运行时 + 用到的标准库 | ~20 MB |
| 字体（Fusion Pixel ×2） | 13 MB |
| 应用代码（`app/` + `ltgen/`） | <1 MB |
| **合计（onedir，未压缩）** | **约 85–95 MB** |
| zip 压缩后 | 约 35–45 MB |

**必须排除的大件**（不排除就是几百 MB）：
`QtWebEngineCore`（**598 MB**）、`QtMultimedia` + `libavcodec*.dylib`（27 MB ×2）、
`QtQuick`/`QtQml`、`Qt3D*`、`QtCharts`、`QtPdf`（15 MB）、`QtSql`、`QtTest`、
`QtDesigner`、`Assistant.app`/`Designer.app`、`*.pyi` 存根。
应用只 import 了 `QtCore / QtGui / QtWidgets`（已用 grep 全仓确认），排除是安全的。

> 体积还能再降：字体换成子集（现在 13 MB 是全字符集），或者只带中英两套常用字。
> 这是"要不要为了 10 MB 做字形子集"的取舍，先不折腾。

## 7. 构建脚本草案（**待确认后执行**）

```bash
# Windows（在装了 conda 环境的机器上）
pyinstaller --noconfirm --clean --windowed --onedir ^
  --name LittleTilesReader ^
  --icon packaging/app.ico ^
  --add-data "app/resources;app/resources" ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtMultimedia ^
  --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtCharts ^
  --exclude-module PySide6.QtPdf --exclude-module PySide6.QtSql ^
  --exclude-module tkinter --exclude-module unittest --exclude-module pydoc ^
  app/__main__.py

# macOS：同样参数（--target-arch arm64），图标用 app.icns，产物 .app
# 压缩：Windows→zip（保留可执行权限无需处理）；macOS→ditto -c -k --keepParent
```

配套要写的小东西（都在本仓库，不动别的仓库）：

1. `packaging/` 目录：`app.ico`、`app.icns`、`version_info.txt`（Windows 版本资源）、
   `LittleTilesReader.spec`（把上面的参数固化下来，避免每次手打）；
2. `tools/build_app.py`：一条命令完成"写 `_buildinfo.py` → 调 PyInstaller → 裁剪多余 Qt 模块
   → 生成 zip → 算 SHA-256 并打印"；
3. CI（可选，你确认要做我再动）：GitHub Actions 两个 runner（`windows-latest`、`macos-14`）
   各跑一次，产物作为 Release asset。

## 8. 签名与告警（**不签名会发生什么**）

| 平台 | 不签名的后果 | 缓解 | 成本 |
|---|---|---|---|
| macOS | 用户下载后双击提示"无法打开，因为 Apple 无法检查其是否包含恶意软件"；需要右键→打开，或 `xattr -dr com.apple.quarantine` | 官网写清绕过步骤（三行图文） | 不花钱 |
| macOS（签名 + 公证） | 双击直接开 | 需要 Apple Developer Program（**$99/年**）+ `codesign`/`notarytool` | $99/年 |
| Windows | SmartScreen 弹"Windows 已保护你的电脑"（用户点"仍要运行"可过） | 发布页写清；或先小范围发 | 不花钱 |
| Windows（代码签名） | 不再弹 | 需要 OV/EV 证书（**约 $200–400/年**） | 数百美元/年 |

**建议**：第一版走"不签名 + 官网写清绕过"，等下载量上来再买证书。

## 9. 应用图标从哪来（授权提醒）

- 不能直接用网站 `recourse-temp/littletiles/littletiles.png`（那是模组/项目标识，
  商用分发要留意授权）或 `minecraft.ico`（Mojang 标识）；
- 建议用**你自己的图形**（和你网站同一套像素风格），我可以按现有设计系统画一版
  （`.ico` 多尺寸 + `.icns`），也顺手配上应用内标题栏图标。

## 10. 打包后必须回归的功能（你测的时候照这个单子走）

1. 首次启动：能起来、无控制台窗口、字体是像素字体、数据目录位置提示正确；
2. 主题切换（深/浅）× 语言切换（7 种）各点一遍；
3. 「帮助 → 检查更新」：能连上服务器（服务器没填版本时显示"还没发布"）；
4. 「帮助 → 反馈问题」：预览里有诊断与日志尾部、能提交拿到编号与数据码；
5. 快速导出：选一个存档 → 选区块 → 导出 OBJ（需要 CLI 在 exe 旁或配置里）；
6. 项目模式：新建项目向导（存档目录必填）→ 导出 → 导出概览 → 打包成 zip；
7. 素材导入：**资源包 zip**（这条会踩到 2.2 的两个脚本调用，务必测）、模组 jar；
8. 中文路径：把包放在含中文的目录、导出到含中文的路径；
9. 清空所有数据：只清数据目录、项目目录不动；
10. 退出：进程干净退出（任务管理器 / 活动监视器里没有残留）。

## 11. 待你拍板

1. **形态**：A 瘦客户端 / B 含 reader 的 GPL 一体包 / **两个都发**？
2. **数据目录**：只做"便携模式（exe 同目录）"，还是同时支持安装到 `Program Files`
   并退到用户目录？（后者多半天工作量）
3. **平台**：只做 `windows-x64` + `macos-arm64`？要不要补 `macos-x64`（Intel Mac）？
4. **签名**：第一版不签名（我写绕过说明），还是现在就买证书？
5. **图标**：我按你网站风格画一版，还是你自己出图？

## 12. 明确不做的事

- 不执行任何构建、不装 PyInstaller、不往 GitHub 传产物；
- 不动 `inception-work`（除非你确认要加平台键/填版本号）；
- 不改库仓库的构建（形态 B 只是把已有的 `LittleTilesReader` 产物拷进包）。
