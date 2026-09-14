# 本次会话任务书（2026-09-14 夜）

> 用户睡前下达，要求**持续完成、不要中途提问**。本文件是防遗忘的任务清单，
> 用户验收后可以删掉（和 `HANDOFF.md` 一样属于临时文件）。

## 0. 用户原话要点（13 条）

1. 库仓库（`minecraft-littletiles-reader`）**现在只负责库的职责**；对接由
   应用仓库 `/Users/external_elliott/Development/minecraft-littletiles-reader-app` 负责。
2. 输出/测试文件的目录：`/Users/external_elliott/DevelopmentTestFolder`。
3. 我的世界客户端叫 **InceptionGN**。
4. 三个测试存档（客户端里能找到，文件夹名分别是 `base` / `escalator` / `subway`）：

   | 存档 | 说明 | 区块坐标 | 半径 | 材质 |
   |---|---|---|---|---|
   | base（基准存档） | 许多基础复杂偏移方块，基础测试 | 0,0 | 1 | 原版材质 |
   | escalator（扶梯存档） | 中等复杂度 | -136,49 | 5 | Inception V1.4 |
   | subway（地铁站存档） | 大量小方块，最大可测到 10 | -7,-26 | 5 | Inception V1.4 |

5. 上一台机器（Windows）的交接内容见 `HANDOFF.md`（246 行，临时文件）。
6. **重点：把 app 的风格改成与网站 `/Users/external_elliott/Development/inception-work`
   一致**；自选合适架构，做到跨平台、统一样式、与网站同款风格。
7. 先完善已有功能的测试；测通后再做后续功能，并继续测试。
8. **不要 push**，用户验收后自己 push。
9. Python 环境：**下一个 conda 并配置好，全程由我做**。
10. 用户睡觉，持续完成，不要问。
11. 除了项目文件夹与测试文件夹（可下载/保存/删除）之外，**不要动远程库，尽量别动其他文件**。
12. 把这些内容写进一个 md 防止遗忘（本文件）。
13. 有问题可以问（用户醒来后回答）。

## 1. 环境事实（macOS 本机）

- 应用仓库：`/Users/external_elliott/Development/minecraft-littletiles-reader-app`
  （Python 3 + **PySide6**，入口 `python -m app`；分支 `main`）
- 库仓库：`/Users/external_elliott/Development/minecraft-littletiles-reader`（分支 `v2ForLLM`，C++ CLI）
- 网站：`/Users/external_elliott/Development/inception-work`（Vue 3 + Vite）
- **组件库/设计系统**：`/Users/external_elliott/Development/mcpixel-craft-ui`
  （`src/assets/theme/mcpixel-craft-ui-color.css` 是调色板，`*-var.css` 是尺寸，
  `Sources/web/src/styles/backend.css` 是网站后台的语义主题映射）
- 测试目录：`/Users/external_elliott/DevelopmentTestFolder`
- 本机原先没有 conda（只有系统 python3.9）→ 需要安装（第 9 条）

## 2. 设计语言（从网站与组件库提取，全部为实测值）

**调色板 `--mc-core-*`**

| 名称 | 值 | 名称 | 值 |
|---|---|---|---|
| green-6 | `#2a641c` | grey-6 | `#262423` |
| green-5 | `#3c8527` | grey-5 | `#3d3938` |
| green-4 | `#52a535` | grey-4 | `#6b6562` |
| green-3 | `#6cc349` | grey-3 | `#aba09c` |
| green-2 | `#86d562` | grey-2 | `#d0c5c0` |
| green-1 | `#a0e081` | grey-1 | `#ede5e2` |
| off-black | `#171615` | off-white | `#fcf5f1` |

**语义主题（网站后台 `--bk-*`）**

| 语义 | 深色（默认） | 浅色 |
|---|---|---|
| 页面底 | `#171615` | `#ede5e2` |
| 侧栏/弹窗 | `#262423` | `#fcf5f1` |
| 表面（浮层） | `rgba(255,255,255,.04/.07/.12)` | `rgba(38,36,35,.04/.07/.12)` |
| 描边 | `#3d3938` / `rgba(255,255,255,.08)` | `#d0c5c0` / `rgba(38,36,35,.1)` |
| 文字 1/2/3/4 | `#fcf5f1` / `#d0c5c0` / `#aba09c` / `#6b6562` | `#262423` / `#3d3938` / `#6b6562` / `#aba09c` |
| 强调 / 强强调 | `#52a535` / `#3c8527` | `#3c8527` / `#2a641c` |
| hover | `#fffc70`（亮黄） | `#8a6d00` |
| ok / link | `#86d562` | `#2a641c` |
| info | `#6cb1d6` | `#2f6f9a` |
| amber | `#f5c677` | `#96601a` |
| danger | `#ff8a7a` | `#a03b30` |

**形态约定**：像素字体（Fusion Pixel，CN8/10/12）、**直角（无圆角）**、
深色石头底 + 草方块绿 + 亮黄 hover；控件统一高度 **32px**；
按钮尺寸档 large 258×48 / medium 129×32 / small 43×24（字号 17 / 15 / 11）。

## 3. 本次要交付的（按顺序）

1. **本文件**（任务书）✔
2. **conda 环境**：安装 conda（miniconda），建环境 `minecraft-littletiles-reader`，
   装 PySide6 等依赖，并让仓库里的测试能在该环境下跑。
3. **设计系统落地**（第 6 条的重点）：在 app 里建 `app/ui/design/`
   （tokens / fonts / qss / components / theme manager），全局套 QSS，
   深浅色跟随网站那两套语义色；自定义绘制（区块格子等）也改用同一套令牌。
4. **把现有界面按新风格改造**：主窗口、项目列表/项目窗口、导出对话框、
   素材/模组管理、进度条与日志面板、对话框与提示。
5. **完善并跑通测试**：`tests/` 下全部脚本（离屏）、配色渲染自检、
   以及用第 4 条那三个真实存档（base / escalator / subway）做端到端导出验证，
   产物写到 `/Users/external_elliott/DevelopmentTestFolder`。
6. **后续功能**（`HANDOFF.md` 的 P0，做完各自补测试）：
   - 材质包**自定义命名** + 选中时查看内容（方块数/贴图数/缺失）
   - **输出目录管理**（`AppConfig.output_dir` 目前没有界面）
   - 快速导出支持**粘贴文本导出 SNBT**
7. 需要用户拍板的三件事（醒来后回答，不阻塞前面的工作）：
   - 打包目标形态（onedir zip？应用名/图标？只 Windows 还是也要 macOS？）
   - 快速导出粘贴的 SNBT 落哪个目录
   - 贴图"需求指纹"缓存是否改库（不改只是慢一点）

## 4. 硬性约束

- **不 push**；只提交到本地。
- 不改库仓库的职责边界（库只做库的事）；应用侧改动为主。
- 不动远程仓库；除项目文件夹与测试文件夹外尽量不动其他文件。
- 提交信息用中文，写清"改了什么 + 实测结果"。
- 测试数据（三个存档）在客户端 InceptionGN 的 saves 目录里，名称 base/escalator/subway。

## 5. 进度记录（边做边更新）

- [x] 读完网站/组件库的设计令牌，形成 §2
- [x] 应用仓库结构摸清（PySide6 + `app/ui/*`，现有 `theme.py` 只按系统调色板取语义色）
- [x] conda 安装与环境（Miniforge3 → `~/miniforge3`，环境 `minecraft-littletiles-reader`＝Python 3.11.16 + PySide6 6.11.2）
- [x] 库仓库补依赖并重建（boost-json 装进 vcpkg；`--job` 才生效）
- [x] 素材包重建（`data/assets/{1.12.2,pack_v14,pack_snbt}`，ltgen lint 2/2 通过）
- [x] 设计系统（`app/ui/design/`：tokens/fonts/qss/components/theme）+ `docs/design-system.md`
- [x] 界面改造（主界面 / 项目界面 / 导出对话框 / 素材管理 / 项目卡片 / 区块格子 / 容量条；主题切换）
- [x] 测试：原有 13 个脚本全部通过 + 新增 `test_real_saves.py`（base/escalator/subway 端到端）
- [x] P0-1 素材自定义命名 + 选中查看内容（`app/materials.py`，`test_materials.py`）
- [x] P0-2 默认输出目录管理（菜单 + `test_output_dir.py`）
- [x] P0-3 快速导出粘贴 SNBT（`app/ui/snbt_source.py` + `test_snbt_paste.py`）
- [x] P1-4 打包分发：形态 B（库 + 客户端一个包、同目录、开箱即用）、macOS ARM、不签名、
      附带自签名说明 + 首次启动许可协议。**真机（macOS 26.6.2 / arm64）已跑通**：
      `dist/app/LittleTilesReader-0.1.0-macos-arm64.zip`（39.6 MB，目录 113.2 MB），
      解压后 `env -i` 隔离环境真实导出 base 存档成功（236 tiles / 12975 顶点 / 4940 面）
- [ ] P1-5 贴图"需求指纹"缓存（需要用户拍板是否改库）
- [ ] P2 封面缩略图缓存 / rar 解压兜底 / 素材管理显示"被哪些项目绑定"

## 6. 需要用户回答的三件事（醒来后）

1. 打包目标形态：onedir zip？应用名/图标？只 Windows 还是也要 macOS？
2. 快速导出粘贴的 SNBT 落哪个目录？——**我暂时选定：应用的 `tmp/`**
   （`tmp/<时间戳>_paste.txt`，与 job 临时文件同处，随时可删）
3. 贴图缓存要不要动库（改 `MaterialManager`）？不动只是每次重烘、慢一点

## 7. 环境变量（跑测试/脚本要用）

```sh
export LTR_DATA_ROOT=/Users/external_elliott/DevelopmentTestFolder/MinecraftLittleTIlesReader/data
export LTR_LIBRARY=/Users/external_elliott/Development/minecraft-littletiles-reader
export LTR_VANILLA_JAR=/Users/external_elliott/DevelopmentTestFolder/MinecraftLittleTIlesReader/InceptionGN/.minecraft/versions/1.12.2/1.12.2.jar
export QT_QPA_PLATFORM=offscreen PYTHONUTF8=1
PY=$HOME/miniforge3/envs/minecraft-littletiles-reader/bin/python
```

`$PY -m app` 启动应用；`$PY tests/test_<名字>.py` 跑单个自检。
