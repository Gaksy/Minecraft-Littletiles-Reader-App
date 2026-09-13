# 交接：LittleTiles Reader（桌面应用）

> 写给下一个接手的人（AI 或人）。**这份文件是临时的**，处理完待办之后请删掉，
> 别留在仓库里（用户上次就删过一份同类文件）。
>
> 写完时间：2026-09-14。当前提交：`faf8468`（app 仓库），`b831ba4`（库仓库）。

---

## 0. 一句话状态

库（C++）与应用（Python/PySide6）之间的 job 契约、素材组合、白模、中文路径、
项目模式（列表 / 素材副本 / 历史记录 / 贴图库 / 区块索引 / 保留策略 / 重建贴图）
都已经跑通并有自检。**剩下的是"打磨与交付"**：素材重命名、默认输出目录设置、
打包分发（M5）、以及两个性能/体验优化。详见 §4。

---

## 1. 仓库与数据

```
D:\DevelopmentProject\
├── minecraft-littletiles-reader        C++ 库 + CLI（唯一 C++ 侧）
│                                       远程 https://github.com/Gaksy/Minecraft-Littletiles-Reader.git
│                                       分支 v2ForLLM
├── minecraft-littletiles-reader-app    本仓库：Python 界面 + 生成端
│                                       远程 https://github.com/Gaksy/Minecraft-Littletiles-Reader-App.git
│                                       分支 main
├── minecraft-littletiles-reader-data   测试数据（不是仓库）
└── minecraft-littletiles-reader-*-backup.zip  历史归档
```

两个仓库的 origin 都配好了，**push 由用户自己来**（他只让提交，不让推）。

用户机器上的真实素材（自检会用到，读不到就跳过）：

* 客户端 jar：`B:\Game\Minecraft for Windows\InceptionGN\.minecraft\versions\1.12.2\1.12.2.jar`
* 资源包：`...\.minecraft\resourcepacks\INCEPTION texture V1.4.zip`
* 模组：`D:\DevelopmentProject\minecraft-littletiles-reader-data\data\assets\mods\{kirosblocks-1.2.2.jar, LittleTiles_v1.5.66_mc1.12.2.jar}`
* 测试数据：`data\regions\{base,escalator,subway}.zip`、`data\snbt\test_snbt\*.txt`、
  素材包 `data\assets\{pack_v14,pack_snbt}`

应用目录布局（便携式，运行时生成、已在 .gitignore 里）：

```
config/app.json      库 CLI 路径、默认输出目录、最近存档、项目登记表、UI 偏好
resources/sources/   导入后解压出来的素材（按内容指纹命名）
cache/packages/      组合好的素材包（按启用顺序指纹命名）
logs/<时间戳>.log    每次启动一个会话日志（含 job 原文）
tmp/                 临时 job 文件
outputs/             快速导出的默认落点
```

项目目录（用户自选位置，`app/project.py` 的 `LAYOUT_DIRS`）：

```
project.json  cover.png  packs/  mods/  inputs/snbt/  inputs/saves/
textures/<哈希前2位>/<sha1>.png   package/（组合结果副本）  outputs/<时间戳>_<名字>/
records/index.json + records/<导出 id>.json
```

---

## 2. 怎么跑、怎么测

**解释器**：`A:\Application\Anaconda\envs\minecraft-littletiles-reader\python.exe`
（PySide6 6.11.2 已装）。启动应用：`python -m app`（或 PyCharm 跑 `app/__main__.py`）。

**库 CLI**：应用不编译库，只调用 `ltgen.paths.reader_executable()` 找到的
`<库仓库>/cmake-build-debug/LittleTilesReader.exe`。**改了库源码就要重建**：

```
cmd /c "call ""A:\Application\VisualStudio\2022\VC\Auxiliary\Build\vcvars64.bat"" >nul 2>&1 && ""A:\Application\CMake\bin\cmake.exe"" --build cmake-build-debug"
```

**自检**（都不是 pytest，直接跑脚本；离屏，不需要显示器）：

```
set QT_QPA_PLATFORM=offscreen
python tests/test_project_ui.py      # 记录/三态、体积统计、贴图库、保留策略、对话框、真实导出、重建
python tests/test_m1.py              # 快速导出端到端（真实子进程）
python tests/test_options_flow.py    # 选项链路（会写仓库 tmp/）
python tests/test_output_prompt.py   # 导出完成后的"是否打开目录"
python tests/test_unicode_paths.py   # 中文路径端到端
python tests/test_project.py         # 项目数据层
python tests/test_sources.py tests/test_vanilla.py tests/test_clear.py   # 需要 LTR_VANILLA_JAR
python tests/render_theme_check.py <输出目录>   # 深浅色各渲染界面 PNG，人工核对
```

需要 jar 的三个用例：`set LTR_VANILLA_JAR=<客户端 jar 路径>`，否则它们打印"跳过"并返回 0。

**沙箱提醒**：本仓库在 `D:\DevelopmentProject\minecraft-littletiles-reader` 之外，
写文件（包括 `.git`）可能要提权（`sandbox_permissions: require_escalated`）；
`tests/test_options_flow.py` 之类会写仓库 `tmp/`，不提权会报 PermissionError。

---

## 3. 硬性约束（违反会被用户当场否掉）

1. **不提供、不链接任何素材下载**。贴图是 Mojang 的资源，工具只读用户自己的游戏/资源包。
2. **界面文案与注释用中文**（app 仓库）。库仓库相反：注释英文、源码无中文。
3. 界面避免"开发笔记式"文案；给用户的提示要像人话，能照着做。
4. 耗时的活必须放后台线程 + 嵌套事件循环（否则界面冻结，用户会以为卡死），
   已经有 `app/ui/project_window.py:run_in_background` 与 `_Importer`/`_Composer` 现成写法。
5. 任何删除操作都要先说清楚"删什么、释放多少"，默认**不自动删**用户的东西。
6. 交付要"一步到位"：整块做完、自己跑过自检，再交给用户；不要交半成品让他试。
7. 用户自己 push；不要替他 push/改远程。

---

## 4. 待办（按优先级）

### P0-1 素材包"自己命名" + 查看内容（用户原始需求，还没做）

用户原话："材质管理：允许用户导入材质包并自己命名"。
现在 `Source.name` 直接取压缩包文件名（`app/library.py:import_source`），
材质管理界面（`app/ui/material_manager.py`）没有改名入口。

* 做法：左列加「重命名…」（`QInputDialog.getText`，默认当前名），改 `Source.name`
  后 `library.save(APP_DIR)`；名字是显示名，不影响按 id（内容指纹）判重。
* 顺带把设计文档 §5 里的"查看内容"补上：选中素材时在状态行显示
  `ltgen.lint.lint_package()` 的结果（方块数 / 贴图数 / 缺失）。注意只有"素材包目录"
  才有 `block_textures.tsv`，原始客户端/资源包/模组解压目录不是包——那就显示
  "类型：原版/资源包/模组，含 N 张 PNG"这样的粗略统计即可。
* 验收：自检里加"改名后 index.json 里名字变了、按 id 仍是同一条"。

### P0-2 设置界面：默认输出目录（用户原始需求"输出目录管理"）

`AppConfig.output_dir` 存在但**没有任何界面能改它**（只有状态栏显示、菜单里能打开）。

* 做法：菜单「输出」里加「设置输出目录…」+「恢复默认（应用目录/outputs）」，
  改完写 `config.save()` 并刷新状态栏。也可以顺带把"以后不再询问打开输出目录"
  与"区块说明是否已自动弹过"这两个开关放进同一个设置对话框。

### P0-3 快速导出也要能"粘贴文本"（用户原话：导出 SNBT 提供 txt 文件 / 粘贴文本）

项目模式已经有了（`project_window._PasteSnbtDialog` → 落成
`<项目>/inputs/snbt/<时间戳>_paste.txt` 再导出），但**启动页的快速导出只开了文件对话框**
（`main_window._export_snbt`）。快速导出没有项目，粘贴的文本该落到哪需要选一个：
建议落 `APP_DIR/tmp/snbt_<时间戳>.txt`（或让用户在设置里指定一个"粘贴暂存目录"）。

* 做法：把 `_PasteSnbtDialog` 挪到一个共用模块（例如 `app/ui/snbt_dialog.py`），
  两边都 import；快速导出先弹一个"选择文件 / 粘贴文本 / 取消"的三选一，
  粘贴走同一个落盘再导出的流程。

### P1 M5 打包分发（网站下载那一步的前提）

* 目标：一个能在 Windows 上直接跑的目录（macOS 之后再说），里面包含应用 + 库 CLI。
* 做法建议：PyInstaller（onedir，别用 onefile，启动慢且杀软爱报毒）；
  `ltgen.paths.reader_executable()` 已经会找 `<应用目录>/LittleTilesReader.exe` 之类，
  所以把库 CLI 放进 `sidecar/` 或应用根目录，并在打包后设 `AppConfig.library_cli`。
* 打包前要确认：`app/__init__.py` 里的 `__version__`（现在是 `0.1.0`）、库版本显示
  （`--version` 输出 `x.y.z-beta`）、关于对话框里的提交号在打包环境拿不到 git 时的兜底
  （现在显示"未知"，可以改成写进构建时间的常量）。
* 注意：conda 环境直接打包会把整个环境塞进去（很大）；用干净 venv 装 PySide6 再打。
  这条已写在 `docs/design.md` §2 的取舍里。

### P1 贴图"需求指纹"缓存（省掉每次导出都重烘）

现状：每次导出库都把所有材质烘一遍写进 `<obj 名>_textures/`，随后
`app/texture_library.absorb()` 按 sha1 收进库、同哈希的丢弃。
**磁盘不涨，但 CPU 每次都重算**（材质多时是几秒级）。

* 思路（设计 §7.6）：把"需求指纹 = 素材组合指纹 + 影响烘焙的导出参数"记进记录；
  导出前如果库里已经有这套指纹对应的贴图，就让库少烘——但库不支持"跳过烘焙"。
  可行的折中：给库加一个 `LITTLETILES_TEXTURE_CACHE=<dir>`（或 job 字段），
  让它在写出贴图前先查 `sha1` 是否已在缓存里，命中就只写引用/跳过烘焙。
  这需要动库（`MaterialManager::WriteTextures`），改完更新库仓库的自检与 `docs/job.md`。
* 如果用户不想动库：这条可以不做，收益只是时间。

### P2 封面缩略图缓存

设计 §4.1 说封面缩略图放 `cache/covers/`。现在卡片与项目页都是每次
`QPixmap(...).scaled()` 直接读项目里的原图（几 MB 的原图在项目多时会有明显卡顿）。
做法：第一次读图时按指纹（路径+mtime+大小）生成 256px 缩略图存 `cache/covers/<指纹>.png`。

### P2 rar 解压的环境依赖

`app/sources.py:_extract_rar` 依次试 `unrar` / `tar`（Windows 10+ 的 bsdtar 能读 rar）
/ `unar`。机器上三个都没有时会失败，提示还算清楚（"可以手动解压后选那个目录"）。
可选改进：把 `7z.exe` 也加进候选，或在提示里给出"把 ComfyUI…"式的具体下载指引——
**注意不要给素材下载链接，给解压工具的链接是允许的，但最好先问用户**。

### P2 素材管理里显示"这个素材被哪些项目绑定"

项目是素材库的副本（`packs/`、`mods/`），删素材前应该能看到影响面。
`AppConfig.project_paths()` + `Project.load()` + `project.materials` 就够了。

---

## 5. 已经做完的（按模块速查）

**库侧（`minecraft-littletiles-reader`，提交到 `b831ba4`）**

* `--job <file.json>` + `--progress json`（NDJSON 事件流），契约见库仓库 `docs/job.md`
* `AssetsPackage` + `MaterialManager`：结构化去重（同纹理只解一次）、烘焙输出与素材目录分离
* 存档根目录解析（`SaveFolder`）、任意矩形区块、`Stats`、白模（无素材也能导普通方块）
* 版本号与发布通道：`Galib/include/Version.h`，默认 **beta**，`--version` 输出
* **中文路径全链路**：`File/Utf8Path.h`（UTF-8 ↔ 原生路径）、`wmain`（命令行参数也走 UTF-8）、
  所有 `ifstream/ofstream` 走 `Utf8Path`；顺带修掉 `map_Kd` 被降级成绝对路径的问题
  （`std::filesystem::relative` 在这套工具链上对任何路径都 ERROR_ACCESS_DENIED，改用
  `lexically_relative`）

**应用侧（本仓库）**

* 生成端：`tools/`、`ltgen/`（素材包 lint、manifest、tint、contract）
* 素材库 `app/library.py`（两列启用/排序、图标、指纹判重）、资源包叠加 `app/compose.py`
  （资源包先并成一份再一次性合并；模组一次传多个 `--mod-root`，**不要链式传底**，会丢贴图）
* 快速导出（主界面两个大按钮）、导出对话框（三种区块模式 + 示意图 + 选项）
* 项目模式：`app/project.py`（数据层）、`app/project_assets.py`（组合结果复制进项目）、
  `app/records.py`（导出记录 + 区块索引 + 三态判定）、`app/texture_library.py`（按 sha1 收贴图、
  改写 `map_Kd`、孤儿回收）、`app/storage.py`（分类体积）、`app/retention.py`（保留策略）、
  `app/savefolder.py`（存档目录检查）
* 界面：`app/ui/` 下 `main_window.py`（启动页：两个大入口 + 项目卡片）、
  `project_window.py`（项目工作界面：导出、存档与备份管理、素材绑定、历史记录、
  区块查询网格、存储容量条、保留策略、重建贴图）、`export_panel.py`（进度+日志，两处共用）、
  `storage_bar.py`（一条分段容量条 + 图例）、`chunk_grid.py`、`project_list.py`、`widgets.py`
* 日志：`app/applog.py`，每次启动一个 `logs/<时间戳>.log`
* 自检：`tests/`（见 §2），`tests/render_theme_check.py` 出深浅色 PNG

---

## 6. 踩过的坑（别重犯）

* `subprocess.run(text=True)` 默认按系统 locale（cp1252）解码 → 中文输出直接崩；
  一律显式 `encoding="utf-8", errors="replace"`。
* 耗时活放主线程 = 界面冻结；组合素材、解压 jar、备份存档、收贴图都必须后台线程。
* **类型识别顺序**：不能先看 `pack.mcmeta`（模组 jar 也带它）；先判"是不是 jar"
  （有 `META-INF`/`net`），再看 `assets/minecraft/blockstates` 区分客户端/模组。
* PySide6 里给**实例**赋 `mouseReleaseEvent = lambda ...` 不一定被虚函数派发走到；
  用子类（`widgets.ClickableLabel`）或事件过滤器。
* 纯 `QWidget` 要画样式表背景/边框得开 `WA_StyledBackground`，选择器用 objectName。
* 自动换行的 `QLabel` 在中文下 `minimumSizeHint()` 会主张整句话那么宽，把整页撑出
  横向滚动条；统一用 `widgets.wrap()`（横向策略 `Ignored` + 最小宽度 80）。
* `QListWidget`/`QTableWidget` 的 sizeHint 是 256 起步，放进纵向布局会把页面拉很长；
  给它们设最大高度。
* 离屏渲染里中文显示成方框是环境没有中文字体（`QFontDatabase.families()` 返回 0），
  不是界面 bug。
* `tests/test_unicode_paths.py` 在整批连跑时**偶发**整体失败过一次（退出码非 0、
  没有产物），单跑和连跑三轮都复现不了；失败信息现在会带上 stderr，再撞见请顺手查。

---

## 7. 用户最近的关注点（语气/口味）

* 他要的是"能用的东西"，不喜欢半成品：一次做完、跑过自检、说清楚验证结果。
* 他会在自己的 PyCharm 里跑，所以启动方式要简单（`python -m app`）。
* 他对界面细节敏感：深色模式、文案、按钮该灰就灰、不要留着能点但没用的按钮。
* 他在写网站（说明、示例图、下载），所以**不要另写用户文档**，也别改 `docs/` 里的
  面向用户的说明——内部设计笔记在 `docs/design.md`，可以按需更新。
