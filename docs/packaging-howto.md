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
```

**自检**：直接跑一下 CLI，确认它能自己起来（打包前必须过这一关，别把坏的塞进包）：

```sh
./cmake-build-release/LittleTilesReader --version
# 期望打印两行：LittleTiles Reader x.y.z（...） 与 x.y.z
```

---

## 3. 打包应用

```sh
cd ~/Development/minecraft-littletiles-reader-app

# macOS（ARM，不签名，含库）
python tools/build_app.py --with-reader --reader ../minecraft-littletiles-reader/cmake-build-release/LittleTilesReader

# Windows（含库；--reader 指向 Release 目录里的 exe）
python tools\build_app.py --with-reader --reader ..\minecraft-littletiles-reader\build-release\Release\LittleTilesReader.exe
```

脚本会依次做这些事（每一步都会打印）：

1. 写 `app/_buildinfo.py`（提交号 / 构建时间 / 平台）——冻结后"关于"里能看到；
2. 跑 PyInstaller（**onedir**，排除 43 个大件 Qt 模块，见脚本里的 `EXCLUDES`）；
3. 把 CLI（与 macOS 上的 `.dylib` / Windows 上的 `nbt++.dll`）拷进包根；
4. 拷 `LICENSE`、`THIRD-PARTY.md`、`README-unsigned.md`、
   `GPL-3.0.txt`、`LGPL-3.0.txt`、`OFL.txt`；
5. 打 zip 并打印 **SHA-256**。

产物：

```
dist/app/LittleTilesReader-<版本>-<平台>/
├── LittleTilesReader.app          # macOS（Windows 上是 LittleTilesReader.exe + _internal/）
├── LittleTilesReader              # ← 库的 CLI，与客户端同目录
├── LICENSE / THIRD-PARTY.md / README-unsigned.md / GPL-3.0.txt / LGPL-3.0.txt / OFL.txt
└── （首次运行后自动生成）config/ logs/ outputs/ tmp/
dist/app/LittleTilesReader-<版本>-<平台>.zip   ← 上传这个
```

常用开关：

| 开关 | 作用 |
|---|---|
| `--with-reader` | 把 CLI 打进包（**不加就是瘦客户端**，导出要靠服务器或用户自己指路径） |
| `--reader PATH` | 显式指定 CLI 位置（Release 目录、别的机器上编的产物） |
| `--no-zip` | 只出目录，方便本地直接双击调试 |

---

## 4. 打包后必须过的自检（别跳）

**在真机上**解压 zip、把 `.app` 拖进「应用程序」，然后按顺序点：

1. 首次打开（macOS 会拦一次，照 `README-unsigned.md` 放行）；
2. 界面上「帮助 → 检查更新」能连上服务器（没配版本号时显示"还没发布"）；
3. 快速导出：选一个存档 → 选区块 → 导出 OBJ（**这一步就是验证"库随包、开箱即用"**）；
4. 项目模式：新建项目向导（存档目录必填）→ 导出 → 导出概览 → 打包成 zip；
5. 素材导入：资源包 zip 与模组 jar 各来一次（这两个走的是进程内调用，打包后最容易坏）；
6. 语言：主界面与项目界面都能切（重启后生效）；
7. 数据目录：确认就在应用旁边（`logs/`、`config/` 出现在同级目录）；
8. 「帮助 → 关于」里的**提交号**是这次构建的那个；
9. 退出后活动监视器里没有残留进程。

Windows 上同理（少了"右键打开"那一步）。

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
| 启动就退、日志里 `ModuleNotFoundError` | PyInstaller 没收集到某个模块：把它加进 `--hidden-import`（改 `tools/build_app.py` 的 `command`），或先在本机 `python -m app` 跑一遍确认不是代码问题 |
| 界面能开，但导出报"找不到 LittleTilesReader" | 第 2 步没编库 / `--with-reader` 没加；确认 CLI 就在 `.app` 同级（macOS）或 exe 同级（Windows） |
| 中文变方框 | 字体没随包：确认 `app/resources/fonts/` 在 `_internal` 里（`--add-data` 已包含） |
| 双击没反应（macOS） | 未签名被拦，照 `README-unsigned.md`；或先 `cd` 到目录用 `./LittleTilesReader` 看终端输出 |
| 导出产物找不到 | 数据目录就在应用文件夹（首次运行后出现 `outputs/`）；也看「关于」与日志里写的路径 |
| 想知道包多大 | 正常范围：onedir 约 90–110 MB、zip 约 35–50 MB；明显更大说明有 Qt 模块被带进去了，检查 `EXCLUDES` 是否被改动 |

---

## 7. 一键复现（两条命令）

```sh
# macOS（Apple 芯片）
cd ../minecraft-littletiles-reader && cmake -S . -B cmake-build-release -DCMAKE_BUILD_TYPE=Release && cmake --build cmake-build-release -j
cd ../minecraft-littletiles-reader-app && python tools/build_app.py --with-reader --reader ../minecraft-littletiles-reader/cmake-build-release/LittleTilesReader
```

```powershell
# Windows（x64）
cd ..\minecraft-littletiles-reader; cmake -S . -B build-release -A x64 -DCMAKE_TOOLCHAIN_FILE="$env:VCPKG_ROOT\scripts\buildsystems\vcpkg.cmake"; cmake --build build-release --config Release
cd ..\minecraft-littletiles-reader-app; python tools\build_app.py --with-reader --reader ..\minecraft-littletiles-reader\build-release\Release\LittleTilesReader.exe
```
