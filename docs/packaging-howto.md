# 打包流程（照着做）

目标产物：**一个压缩包**，解压后 `LittleTilesReader.app`（或 Windows 上的
`LittleTilesReader.exe`）与 `LittleTilesReader`（C++ 库编出来的 CLI）**放在一起**，
用户打开就能用——不需要装 Python，也不需要配任何路径。

> 形态说明：把库一起打进去 → 分发包整体按 **GPL-3.0-or-later**（因为库里编译了
> CGAL 的 GPL 包，见 [`licenses.md`](licenses.md)）；脚本会自动把 `LICENSE`、
> `THIRD-PARTY.md`、`GPL-3.0.txt`、`LGPL-3.0.txt`、`OFL.txt` 一起放进包里。

当前只做 **macOS ARM**（不签名）；Windows 步骤照写，等你要发再跑。

---

## 0. 一次性准备（两个平台都要）

```sh
# ① Python 环境（已有就用现有的），只多装一个打包器
conda activate minecraft-littletiles-reader
pip install pyinstaller

# ② 库依赖（macOS）
brew install cmake boost zlib cgal

# ② 库依赖（Windows，用 vcpkg）
#   vcpkg install cgal boost-iostreams boost-json zlib
#   （CMake 配置时把 toolchain 指到 vcpkg.cmake，见库仓库 README）
```

---

## 1. 克隆/更新三个仓库（库、应用、可选的数据仓库）

```sh
cd ~/Development
git -C minecraft-littletiles-reader        pull      # 库（C++）
git -C minecraft-littletiles-reader-app    pull      # 应用（Python）
```

两个目录要是**兄弟关系**（`~/Development/minecraft-littletiles-reader-app` 与
`~/Development/minecraft-littletiles-reader`），这样 `ltgen/paths.py` 能自动找到库。
不在一起就设环境变量：

```sh
export LTR_LIBRARY=~/某个位置/minecraft-littletiles-reader
```

---

## 2. 先构建库（得到 CLI）——**这一步在哪个平台打包就在哪个平台做**

### macOS（Apple 芯片）

**推荐用 Ninja + 显式 `DEVELOPER_DIR`**（真机验过；直接 `cmake -S . -B build` 在这台机器上会挂，
原因见下面那条注）：

```sh
cd ~/Development/minecraft-littletiles-reader
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer   # 见下方"Xcode Bata 坑"
cmake -S . -B cmake-build-release-ninja -G Ninja \
      -DCMAKE_MAKE_PROGRAM=/Applications/CLion.app/Contents/bin/ninja/mac/aarch64/ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_TOOLCHAIN_FILE=$HOME/vcpkg/scripts/buildsystems/vcpkg.cmake
cmake --build cmake-build-release-ninja -j 8

# 产物位置
ls cmake-build-release-ninja/LittleTilesReader
```

不用 CLion 自带 cmake/ninja 的话，`brew install cmake ninja` 后把路径换掉即可，
其余参数不变（`-G Ninja` 与 `-DCMAKE_MAKE_PROGRAM` 是关键）。

<details>
<summary>Xcode Bata 坑（真机踩到）</summary>

本机 `xcode-select -p` 指向 `/Applications/Xcode Bata.app/...`，而**路径里有空格**：
CMake 调 `make` 时会把 `/Applications/Xcode` 切开，报
`make: /Applications/Xcode: No such file or directory`。
两条出路，任选其一：

* 用 `-G Ninja`（推荐，Ninja 不经过 make，路径空格不再是问题）；
* 或先 `export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`
  把工具链指回没空格的那份 Xcode。

两个都做最稳。
</details>

（备选，工具链干净时可用：）

```sh
cd ~/Development/minecraft-littletiles-reader
cmake -S . -B cmake-build-release -DCMAKE_BUILD_TYPE=Release
cmake --build cmake-build-release -j

# 产物位置（打包脚本默认就找这里）
ls cmake-build-release/LittleTilesReader
```

> 脚本默认只认 `cmake-build-debug`（开发时的目录）。用 Release 目录时，
> 打包时显式指过去：`--reader cmake-build-release/LittleTilesReader`（见第 3 步）。

### Windows（x64）

```powershell
cd $HOME\Development\minecraft-littletiles-reader
cmake -S . -B build-release -G "Visual Studio 17 2022" -A x64 `
      -DCMAKE_BUILD_TYPE=Release `
      -DCMAKE_TOOLCHAIN_FILE=$env:VCPKG_ROOT\scripts\buildsystems\vcpkg.cmake
cmake --build build-release --config Release

# 产物（注意 .exe，以及它旁边会被自动拷过去的 nbt++.dll）
dir build-release\Release\LittleTilesReader.exe
dir build-release\Release\nbt++.dll
```

> `nbt++.dll` 是库的 CMake 在 POST_BUILD 里自动拷过去的（`CMakeLists.txt` 里的
> `if(WIN32)` 那段），不用手工放。打包脚本会把 exe 同目录的 `*.dll` 一起收走。

**自检**：直接跑一下 CLI，确认它能自己起来（打包前必须过这一关，别把坏的塞进包）：

```sh
./cmake-build-release-ninja/LittleTilesReader --version
.\build-release\Release\LittleTilesReader.exe --version     # Windows
# 期望打印两行：LittleTiles Reader x.y.z（...） 与 x.y.z
```

---

## 3. 打包应用

```sh
cd ~/Development/minecraft-littletiles-reader-app

# macOS（ARM，不签名，含库）
python tools/build_app.py --with-reader --reader ../minecraft-littletiles-reader/cmake-build-release-ninja/LittleTilesReader

# Windows（含库；--reader 指向 Release 目录里的 exe）
python tools\build_app.py --with-reader --reader ..\minecraft-littletiles-reader\build-release\Release\LittleTilesReader.exe
```

脚本会依次做这些事（每一步都会打印）：

1. 写 `app/_buildinfo.py`（提交号 / 构建时间 / 平台）——冻结后"关于"里能看到；
2. 跑 PyInstaller（**onedir**，排除 43 个大件 Qt 模块，见脚本里的 `EXCLUDES`），
   产物先落到 `build/app/dist/`；
3. **挑一份搬进最终目录**：macOS 上 PyInstaller 会同时产出 `LittleTilesReader.app`
   （自包含，用户双击的就是它）和 `LittleTilesReader/`（裸 onedir，`.app` 就是从它拼出来的）。
   两份内容是重复的，都发出去 = Qt 打两遍、体积翻倍，所以只搬 `.app`；
4. 把 CLI 拷进包根，**并修好它的动态库依赖**（见下方"动态库为什么要改"）；
5. 显式收集"运行时才 import"的模块（`--collect-submodules ltgen` +
   扫 `tools/` 那几个运行时脚本的依赖），见下方"为什么会有这一步"；
6. 拷 `LICENSE`、`THIRD-PARTY.md`、`README-unsigned.md`、
   `GPL-3.0.txt`、`LGPL-3.0.txt`、`OFL.txt`；
7. 做一次 ad-hoc 签名（macOS，改过 Mach-O 之后必须重签，否则 arm64 上直接被杀）；
8. 打 zip（macOS 用 `ditto`）并打印 **SHA-256**。

### 为什么会有"显式收集运行时模块"这一步

`app/generators.py` 是**按文件路径**加载 `tools/*.py` 的（`importlib`），
PyInstaller 顺着 import 图爬，爬不到那条边。于是那些脚本里 `from ltgen.console
import enable_utf8_output` 就成了漏网的依赖——真机上表现为
**构建一切正常、点「重新组合素材」才报 `No module named ltgen.console`**。

两道保险：

* `--collect-submodules ltgen` 把整个包收全（`console` / `manifest` / `tint` 都进来）；
* `tool_hidden_imports()` 扫 `app/generators.py::TOOL_NAMES` 里那几个脚本的所有
  import，转成 `--hidden-import`（以后脚本里加了 `numpy` 之类会自动跟上）。
  只扫这几个是有意的：`tools/` 下还有 `build_app.py` / `make_app_icon.py` 这种
  **只在打包机器上跑**的脚本，它们 import 的 PyInstaller 不能跟着进包。

验收靠第 4 节第 0 步的 `--self-check`：它会把 `ltgen.*` 全 import 一遍、
再把三个工具脚本按路径真加载一遍。缺哪个直接报名字。

### 动态库为什么要改（真机踩到）

库编出来的 `LittleTilesReader` 依赖 `@rpath/libnbt++.dylib`，而那个 LC_RPATH 是
**本机的绝对路径**（`…/cmake-build-release-ninja/_deps/libnbtplusplus-build`）。
原样拷进包 = 用户机器上一定 `Library not loaded`。脚本会自动：

1. 用 `otool -L` 找出依赖、按 LC_RPATH 解析成真实文件，拷到包根；
2. `install_name_tool -change @rpath/libnbt++.dylib @executable_path/libnbt++.dylib`
   （再 `-id` 改库自己的 install id），并删掉那些指向本机构建目录的旧 rpath；
3. 重新做 ad-hoc 签名。

验证（解压后必须是这样）：

```sh
otool -L dist/app/LittleTilesReader-*/LittleTilesReader
#   @executable_path/libnbt++.dylib   ← 必须是这个，不能是 @rpath 或绝对路径
```

### 为什么 zip 用 ditto 而不是 Python 的 zipfile

Python 的 `zipfile` **不认软链**，会把 `.app` 里 `Frameworks` ↔ `Resources` 之间的软链
展开成实体文件：zip 从 38 MB 涨到 101 MB，而且解压出来的 `.app` 签名对不上
（Gatekeeper 直接判"已损坏"）。`ditto -c -k --sequesterRsrc --keepParent` 是 macOS
打 `.app` 的标准做法，软链、扩展属性都保留。

### 启动器为什么不是 `app/__main__.py`

`app/__main__.py` 是给 `python -m app` 用的、通篇相对导入；PyInstaller 把入口当**脚本**
跑，`__package__` 是空的，相对导入直接 `ImportError: attempted relative import with no
known parent package` ——**构建能过、双击起不来**。所以入口用 `packaging/entry.py`，
里面做绝对导入 `from app.__main__ import main`。别把入口改回去。

<details>
<summary>旧版第 3~5 步（保留原文，便于对照）</summary>

3. 把 CLI（与 macOS 上的 `.dylib` / Windows 上的 `nbt++.dll`）拷进包根；
4. 拷 `LICENSE`、`THIRD-PARTY.md`、`README-unsigned.md`、
   `GPL-3.0.txt`、`LGPL-3.0.txt`、`OFL.txt`；
5. 打 zip 并打印 **SHA-256**。

</details>

产物：

```
dist/app/LittleTilesReader-<版本>-<平台>/
├── LittleTilesReader.app          # macOS：双击启动（Windows 上是 LittleTilesReader.exe + _internal/）
├── LittleTilesReader              # ← 库的 CLI，与客户端同目录
├── libnbt++.dylib                 # macOS：CLI 的依赖，已改成 @executable_path 引用
├── LICENSE / THIRD-PARTY.md / README-unsigned.md / OFL.txt
├── licenses/                      # LGPL-3.0 + （含库时）GPL-3.0 / BSL-1.0 / zlib
└── （首次运行后自动生成）config/ logs/ outputs/ tmp/
dist/app/LittleTilesReader-<版本>-<平台>.zip   ← 上传这个
```

> macOS 的包**只有 `.app`**，没有裸 onedir（原因见上一节）。`LittleTilesReader`
> 与 `.app` 同级不是随手放的：`app/reader.py` 就是去 `.app` 所在文件夹找它。

Windows 的同一层结构（名字不一样，位置一样）：

```
dist/app/LittleTilesReader-<版本>-windows-x64/
├── LittleTilesReader\                 # PyInstaller onedir：应用自己
│   ├── LittleTilesReader.exe
│   └── _internal\                     # 只读资源（tools/、字体、图标）
├── LittleTilesReader.exe              # ← 库的 CLI，在**上一层**
├── nbt++.dll                          # ← CLI 的依赖，与 CLI 同目录
└── LICENSE / THIRD-PARTY.md / README-unsigned.md / OFL.txt / licenses\
```

> **Windows 上这两个 `LittleTilesReader.exe` 不是同一个东西**，别混：
> 应用自己那个在 `LittleTilesReader\` 里，库的 CLI 在上一层。`app/reader.py`
> 会显式跳过"正在运行的自己"，再去上一层找（`tests/test_reader_locate.py`
> 钉住了这条）。定位错的症状是：**每点一次导出就多开一个客户端窗口**。

常用开关：

| 开关 | 作用 |
|---|---|
| `--with-reader` | 把 CLI 打进包（**不加就是瘦客户端**，导出要靠服务器或用户自己指路径） |
| `--reader PATH` | 显式指定 CLI 位置（Release 目录、别的机器上编的产物） |
| `--no-zip` | 只出目录，方便本地直接双击调试 |

---

## 3.5 首次启动的许可协议（用户必须同意）

打包版第一次启动会先弹**许可协议**：左边列出组件与许可（应用自身 MIT、Qt LGPL、
字体 OFL、CGAL GPL、libnbt++ LGPL、Boost BSL、zlib），右边可翻阅全文，
勾选「我已阅读并同意」之后「同意并继续」才可点；点「不同意并退出」或直接关窗口 = 拒绝，
进程直接退出（不会进主界面）。

- 同意结果写进 `config/app.json`（`licenses_version` + `licenses_accepted_at`），
  之后不再打扰；**协议集合变了**（改 `app/licenses.py` 的 `LICENSE_SET_VERSION`）会重新问一次；
- 随包必须带全文（脚本已经处理）：`LICENSE`、`THIRD-PARTY.md`、`licenses/LGPL-3.0.txt`
  总是带；含库的完整包再加 `licenses/GPL-3.0.txt`、`BSL-1.0.txt`、`zlib.txt`；
  字体许可 `OFL.txt` 与字体放在一起；
- 自检请务必验一条：**首次启动确实弹了、不勾选点不动同意、拒绝后进程退出**。

## 4. 打包后必须过的自检（别跳）

**第 0 步，先跑这条**（打包后立刻，不用开界面）：

```sh
dist/app/LittleTilesReader-<版本>-<平台>/LittleTilesReader.app/Contents/MacOS/LittleTilesReader --self-check
# 期望最后一行：结果：全部通过，可以发（退出码 0）
```

它验的是"**运行时才 import** 的东西"——`app/generators.py` 按路径加载
`tools/*.py`，那些脚本又 import `ltgen.console` 等，PyInstaller 的静态分析看不见
这一层，漏一个模块照样构建成功、点下去才报错（v0.1.0 的「重新组合素材」就这么坏过）。
Windows 上同理：`...\LittleTilesReader\LittleTilesReader.exe --self-check`。

**在真机上**解压 zip、把 `.app` 拖进「应用程序」，然后按顺序点：

1. 首次打开（macOS 会拦一次，照 `README-unsigned.md` 放行）→ **接着应弹出许可协议**，
   勾选后才能继续；再启动一次**不应**重复弹；
2. 界面上「帮助 → 检查更新」能连上服务器（没配版本号时显示"还没发布"）；
3. 快速导出：选一个存档 → 选区块 → 导出 OBJ（**这一步就是验证"库随包、开箱即用"**）；
4. 项目模式：新建项目向导（存档目录必填）→ 导出 → 导出概览 → 打包成 zip；
5. 素材导入：资源包 zip 与模组 jar 各来一次（这两个走的是进程内调用，打包后最容易坏）；
6. 语言：主界面与项目界面都能切（重启后生效）；
7. 数据目录：确认就在应用旁边（`logs/`、`config/` 出现在同级目录）；
8. 「帮助 → 关于」里的**提交号**是这次构建的那个；
9. 退出后活动监视器里没有残留进程。

Windows 上同理（少了"右键打开"那一步）。

### 4.1 不用手点的自动版（可在真机上直接跑）

上面 9 条里，能命令化的部分都在这一节。**在打包机上新开一个目录**，
模拟"用户下载解压"，能把"库随包、开箱即用"这件事验到根上：

```sh
APP=/Users/external_elliott/Development/minecraft-littletiles-reader-app
SIM=/tmp/ltr-user-sim2 && mkdir -p "$SIM" && cd "$SIM"

# ① 解压（用 ditto，跟 Finder 行为一致）
ditto -x -k "$APP/dist/app/LittleTilesReader-0.1.0-macos-arm64.zip" .
PKG="$SIM/LittleTilesReader-0.1.0-macos-arm64"

# ② 软链有没有被压坏 + 签名还完好吗（两条都必须过）
ls -la "$PKG/LittleTilesReader.app/Contents/Resources/" | head
codesign --verify --deep --strict "$PKG/LittleTilesReader.app"

# ③ 依赖是不是 @executable_path（不能是 @rpath，也不能是绝对路径）
otool -L "$PKG/LittleTilesReader"

# ④ 最狠的一条：清空环境变量、假 HOME、只留包内 PATH，跑一次真实导出
env -i HOME="$SIM/fakehome" PATH=/usr/bin:/bin:"$PKG" \
    "$PKG/LittleTilesReader" --job "$SIM/job-base.json" --progress json

# ⑤ GUI：用 open 启动（launchd 接管，不会随终端退出）
open -n "$PKG/LittleTilesReader.app"
tail -12 "$PKG/logs/$(ls -t "$PKG/logs" | head -1)"
```

**真机验收记录（2026-09-14，macOS 26.6.2 / arm64）**：

* ④ 的输出：`{"event":"done","ok":true,"tiles":236,"vertices":12975,"faces":4940,...}`
  （base 存档，区块 0,0，半径 1）——全程没碰开发仓库，说明包内自洽；
* ⑤ 的日志：`应用目录: …`、`像素字体已加载`、`库版本：0.2.0-beta（…/LittleTilesReader）`、
  `库 CLI: …（存在=True）` —— 客户端确实找到并调起了同目录的 CLI；
* 首次启动的许可弹窗确认"不勾选点不动同意"（按钮初值是 `setEnabled(False)`）；
* 体积：目录 **113.2 MB**、zip **39.6 MB**；
* 脚本自检：`tests/` 下 23 个脚本全过。

---

## 5. 发布（把包挂到网站上）

1. 把 zip 传到发布位置（GitHub Release / 对象存储 / 服务器 `/uploads`），拿到直链；
2. 后台「网页内容管理 → LT 读取器 → 客户端下载」里填：
   - 平台：`windows` 或 `macos-arm`（**服务器只认这两个键**，见 `lt_read_download`）；
   - 版本号：与包里 `app/__init__.py` 的 `__version__` **保持一致**
     （客户端的"检查更新"就是拿它比大小的）；
   - 下载地址：直链；备注里写大小 + **SHA-256 前 8 位**；
3. 前台 `/littletiles` 的下载弹窗会自动显示；客户端点「检查更新」也会提示新版。

> 形态 B 的包，发布说明里要写清"含 GPL-3.0-or-later 组件，源码见 <仓库>"，
> 包内已经有 `GPL-3.0.txt` 与 `THIRD-PARTY.md`。

---

## 6. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 导出报"找不到 LittleTilesReader"，而路径里出现 `…/LittleTilesReader.app/Contents/minecraft-littletiles-reader/…` | 有代码绕过 `app/reader.py` 直接用了 `ltgen.paths.reader_executable()`。它是拿 `__file__` 反推仓库根的（`PROJECT_ROOT.parent / "minecraft-littletiles-reader"`），冻结后 `__file__` 在 `.app` 里，于是"库仓库"被算成 `.app/Contents/minecraft-littletiles-reader`。**定位 CLI 一律走 `reader.locate()`**（顺序：配置 → 应用旁边 → 仓库构建产物）。回归用例：`tests/test_reader_locate.py` |
| 打包版点「导入素材 / 重新组合素材」报 `No module named ltgen.xxx` | 漏收集：`tools/*.py` 是运行时按路径加载的，静态分析看不到它们的 import。`tools/build_app.py` 现在用 `--collect-submodules ltgen` + `tool_hidden_imports()` 扫 `app/generators.py::TOOL_NAMES` 里那几个脚本的依赖。**加新工具脚本就同步 TOOL_NAMES**，然后跑 `--self-check` 复验 |
| 启动就退、日志里 `ImportError: attempted relative import with no known parent package` | 入口被改回 `app/__main__.py` 了。入口必须是 `packaging/entry.py`（见上一节） |
| 启动就退、日志里 `ModuleNotFoundError` | PyInstaller 没收集到某个模块：把它加进 `--hidden-import`（改 `tools/build_app.py` 的 `command`），或先在本机 `python -m app` 跑一遍确认不是代码问题 |
| 构建早期报 `Unable to find '…/build/app/app/resources'` | `--add-data` 的源路径写成相对路径了：`--specpath` 指向 `build/app`，相对路径会被当成相对它解析。脚本里已改成绝对路径 |
| CLI 报 `Library not loaded: @rpath/libnbt++.dylib` | 动态库没随包 / rpath 还是本机绝对路径，见"动态库为什么要改"；`otool -L` 一查就知道 |
| `cmake` 报 `make: /Applications/Xcode: No such file or directory` | 本机 `xcode-select` 指向带空格的 `Xcode Bata.app`。用 `-G Ninja`，或 `export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` |
| 解压出来的 `.app` 打不开、提示"已损坏" | zip 没用 `ditto` 打：zipfile 把软链展开成实体文件，签名就废了。重打一次（脚本已在 macOS 上走 `ditto`） |
| 界面能开，但导出报"找不到 LittleTilesReader" | 第 2 步没编库 / `--with-reader` 没加；确认 CLI 就在 `.app` 同级（macOS）或 exe 同级（Windows） |
| 中文变方框 | 字体没随包：确认 `app/resources/fonts/` 在 `_internal` 里（`--add-data` 已包含） |
| 双击没反应（macOS） | 未签名被拦，照 `README-unsigned.md`；或直接跑 `.app/Contents/MacOS/LittleTilesReader` 看终端输出（**最快的排查手段**） |
| 导出产物找不到 | 数据目录就在应用文件夹（首次运行后出现 `outputs/`）；也看「关于」与日志里写的路径 |
| 想知道包多大 | 真机实测（macOS ARM，形态 B）：目录 **113 MB**、zip **39.6 MB**；明显更大先看有没有把裸 onedir 也发了（应该只有 `.app`），再查 `EXCLUDES` |
| 每点一次导出就多开一个客户端窗口（Windows） | 把"应用自己"当成库的 CLI 了。Windows 上两个 `LittleTilesReader.exe` 同名，一个在 `LittleTilesReader\` 里（应用），一个在上一层（CLI）。见 §8 第 5 条 |

---

## 7. 一键复现（两条命令）

```sh
# macOS（Apple 芯片）
cd ../minecraft-littletiles-reader && cmake -S . -B cmake-build-release -DCMAKE_BUILD_TYPE=Release && cmake --build cmake-build-release -j
cd ../minecraft-littletiles-reader-app && python tools/build_app.py --with-reader --reader ../minecraft-littletiles-reader/cmake-build-release-ninja/LittleTilesReader
```

```powershell
# Windows（x64）
cd ..\minecraft-littletiles-reader; cmake -S . -B build-release -A x64 -DCMAKE_TOOLCHAIN_FILE="$env:VCPKG_ROOT\scripts\buildsystems\vcpkg.cmake"; cmake --build build-release --config Release
cd ..\minecraft-littletiles-reader-app; python tools\build_app.py --with-reader --reader ..\minecraft-littletiles-reader\build-release\Release\LittleTilesReader.exe
```

---

## 8. 换平台构建前：照单核对（真机已踩过的坑）

2026-09-14 在 macOS ARM 真机上第一次真跑，**同一个包连爆四次**，共同点是
"构建成功 ≠ 能用"。换平台（尤其 Windows）之前，按这张表逐条核对：

| # | 症状（用户视角） | 真因 | 现在怎么挡住 |
|---|---|---|---|
| 1 | 双击没反应 | 入口 `app/__main__.py` 通篇相对导入，被 PyInstaller 当脚本跑，`__package__` 为空 | 入口改成 `packaging/entry.py`（绝对导入）；**别改回去** |
| 2 | 双击没反应 / 依赖报错 | CLI 的 `libnbt++.dylib` 引用是 `@rpath/...`，而 LC_RPATH 是**本机绝对路径** | 打包时 `install_name_tool` 改写成 `@executable_path/...` |
| 3 | 点「重新组合素材」报 `No module named ltgen.console` | `tools/*.py` 是运行时按路径加载的，PyInstaller 静态分析看不到它们的 import | `--collect-submodules ltgen` + `tool_hidden_imports()`；**加新工具脚本同步 `app/generators.py::TOOL_NAMES`** |
| 4 | 项目导出报"找不到 LittleTilesReader"，路径里出现 `.app/Contents/minecraft-littletiles-reader/…` | 有代码绕过 `app/reader.py` 直接用了 `ltgen.paths.*`（它靠 `__file__` 反推仓库根，冻结后算进 `.app` 里） | 定位 CLI **一律**走 `reader.locate()` |

Windows 上还要额外留意第 5 条（macOS 上不成立、容易漏掉）：

| # | 症状 | 真因 | 现在怎么挡住 |
|---|---|---|---|
| 5 | 每点一次导出就**多开一个客户端窗口** | Windows 包结构里 `<包>\LittleTilesReader\LittleTilesReader.exe` 是**应用自己**，而库的 CLI 在上一层，名字一样；不排掉就会把自己当 CLI 去执行 | `bundled_reader()` 显式跳过 `sys.executable`、并往上一层找；`tests/test_reader_locate.py` 覆盖 |

### 每个平台都跑这三条（别跳）

```sh
# ① 冻包自检（不开界面，一秒出结果）
.../LittleTilesReader.app/Contents/MacOS/LittleTilesReader --self-check      # macOS
...\LittleTilesReader\LittleTilesReader.exe --self-check                     # Windows

# ② 全套脚本自检（当前 25 个）
python tests/test_<名字>.py     # 或按 §2 的清单逐个跑

# ③ 真机点一遍：首次许可 → 快速导出 → 项目模式导出 → 导入素材/重新组合素材
```

第 ①②条能挡住第 1（部分）、3、4、5 类；**第 2 类只有 ③ 能挡**（依赖是在启动时才解析的）。
