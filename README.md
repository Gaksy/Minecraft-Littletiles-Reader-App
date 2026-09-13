# minecraft-littletiles-reader-app

**LittleTiles Reader 的桌面应用 + 生成端。** 一个仓库装两件事：

- `app/`（待建）—— 跨平台桌面应用：项目管理、素材/模组管理、导出与历史记录
- `ltgen/` + `tools/` + `python/` —— **生成端**：把素材组合成库能直接消费的素材包

> 状态：应用处于设计阶段（见 [`docs/design.md`](docs/design.md)），生成端已经可用。

## 两个仓库的分工

| 仓库 | 角色 |
|---|---|
| `minecraft-littletiles-reader` | **C++ 库**：读存档/NBT、几何、材质烘焙、写 OBJ/MTL/贴图 |
| `minecraft-littletiles-reader-app`（本仓库） | **Python 侧**：生成端 + 桌面应用 |

测试数据（regions / snbt / matlab / assets）在兄弟目录
`minecraft-littletiles-reader-data`，**不是仓库**，就是一份数据目录。

调用方式：应用**通过子进程**调用库编出来的 `LittleTilesReader`，
契约是库仓库的 [`docs/job.md`](../minecraft-littletiles-reader/docs/job.md)
（job JSON + NDJSON 进度）。生成端则被应用**进程内直接 import**——这正是两边放同一个
仓库的原因。

## 生成端与库的边界

这条边界是防雷关键，改代码前看一眼：

| | 生成端（本仓库） | 库（另一个仓库） |
|---|---|---|
| 职责 | 解 jar、解析 blockstate/models、抠纹理、归一化、去重、组合层级 | 读素材包，结合网格烘焙出 OBJ/PNG/MTL |
| 产出 | **素材包目录**：映射表 + 只读纹理源 +（可选）manifest / tint 表 | OBJ + MTL + 贴图产物 |
| 不做 | **不烘焙 PNG**（tile 颜色只有库合并网格时才知道） | 不读 jar、不解析 blockstate、不抠纹理 |

一句话：素材包是不可变的输入，烘焙永远在库那边。

## 素材包契约

库只认这一个目录布局：

```
<素材包>/
├── block_textures.tsv   必需：<block(+meta)> + 六面贴图 + 六面 tintindex
├── textures/<rel>.png   必需：纹理源，只读；<rel> 是不透明相对路径
├── manifest.json        可选：库只读 format_version，其余字段是给人看的
└── tint.tsv             可选：tint 覆盖表（缺省用库内默认色）
```

`block_textures.tsv` 的列（制表符分隔，`#` 开头是注释）：

```
<block 或 block:meta>  <down> <up> <north> <south> <west> <east>
                       <down_tint> ... <east_tint>      # 可省略，缺省 -1（不染色）
```

## 环境

```sh
conda activate minecraft-littletiles-reader     # Python 3.11
export PYTHONUTF8=1                             # Windows: $env:PYTHONUTF8=1
pip install PySide6                             # 只有应用需要；生成端只用标准库
```

生成端不需要 Pillow / numpy：PNG 读写走标准库 `zlib`。
`PYTHONUTF8=1` 是给输出重定向到管道/文件时用的——否则 Windows 上会用 locale
编码打印中文并直接崩（新代码里另有兜底，老脚本没有）。

### PyCharm

用**本仓库根**作为项目目录（不要再用已退休的 `-tools`）。

- **解释器**：conda 环境 `minecraft-littletiles-reader`
- **工作目录**：运行配置保持项目根——`python -m ltgen` 靠它找到包
- **环境变量**：加 `PYTHONUTF8=1`
- `.idea/`、`__pycache__/`、`data/`、`outputs/`、`tmp/` 都已在 `.gitignore` 里

## 快速开始（生成端）

```sh
python -m ltgen paths                  # 先看数据根 / 库路径解析到哪
python -m ltgen lint  <素材包> [...]    # 校验：库能不能吃、缺哪些贴图
python -m ltgen manifest <素材包> --layer vanilla --layer mods \
    --pack "vanilla@1.12.2:minecraft" --pack "kirosblocks@1.2.2:kirosblocks"
python -m ltgen tint  <素材包>          # 把库内默认 tint 色写进素材包
```

`lint` 是自检入口：它按库的解析规则重读一遍素材包，报出**库会静默忽略**的问题
（列数不足的行、重复的方块键、引用了但磁盘上没有的贴图）。

### 典型流程

```sh
# 1) 原版素材（从 1.12.2 客户端 jar 解出 assets/minecraft）
python tools/resolve_block_textures.py <素材包根>/1.12.2 \
    --table <素材包根>/1.12.2/block_textures.tsv

# 2) 叠加资源包
python tools/build_assets_from_pack.py --pack "texture/MyPack.zip" \
    --out <素材包根>/pack_v14

# 3) 叠加模组（SNBT 结构需要）
python tools/add_mod_textures.py \
    --mod-root <素材包根>/littletiles_1.5.66 --namespace littletiles \
    --mod-root <素材包根>/kirosblocks_1.2.2 --namespace kirosblocks \
    --base <素材包根>/1.12.2 --out <素材包根>/pack_snbt

# 4) 补契约文件并自检
python -m ltgen manifest <素材包根>/pack_v14 --layer vanilla --layer resourcepack \
    --pack "vanilla@1.12.2:minecraft" --pack "INCEPTION texture V1.4@1.4:minecraft"
python -m ltgen tint <素材包根>/pack_v14
python -m ltgen lint <素材包根>/pack_v14
```

## 路径从哪来

这些脚本原先住在库仓库里，默认路径写死成 `<仓库>/data/assets/...`。现在独立成仓库，
数据与库都在别处，统一由 `ltgen/paths.py` 解析：

| 顺序 | 数据根 | 库仓库 |
|---|---|---|
| 1 | 环境变量 `LTR_DATA_ROOT` | 环境变量 `LTR_LIBRARY` |
| 2 | 同级目录 `../minecraft-littletiles-reader-data/data` | 同级目录 `../minecraft-littletiles-reader` |
| 3 | 本仓库内的 `data/`（老布局） | — |

## 目录结构

```
app/                       桌面应用（待建）
ltgen/                     素材包契约工具
├── contract.py            映射表 / manifest / tint 的读写（规则与库侧一致）
├── lint.py                素材包校验
├── manifest.py            manifest.json 生成
├── tint.py                tint.tsv 生成
├── paths.py               数据根 / 库路径解析
└── console.py             输出编码兜底

tools/                     素材生成脚本
├── resolve_block_textures.py   原版 block:meta → 六面贴图 + tintindex
├── add_mod_textures.py         原版 + 模组 → pack_snbt
├── build_assets_from_pack.py   原版 + 资源包 → pack_v14
├── generate_block_id_table.py  数字 ID → 方块名表
├── make_uv_test_model.py       UV 人工核对用的测试模型
├── check_obj_textures.py       检查 OBJ 引用的贴图是否都在
└── benchmark.py                导出基准（跑库的 CLI）

python/                   MATLAB 辅助
└── IntArrayInterpreter.py      盒子数组 → MATLAB 代码

docs/
├── design.md              应用的需求与设计
└── chunk-selection-modes.svg  三种区块选择模式示意图
```

## 现状与里程碑

应用侧的里程碑见 [`docs/design.md`](docs/design.md) §8：
**M0（库侧 job 接口）已完成**，接下来是 M1 应用骨架 → M2 项目管理 →
M3 素材与模组管理 → M4 记录与查询 → M5 打包。

## 已知限制

- 材质包里的 MCPatcher/CTM 连接纹理不支持，用的是连接纹理的基础贴图。
- 多层模型（草方块、带 overlay 的 LT 方块）只导出基础层。
- `tint.tsv` 的键是 `(方块, tintindex)`，"非树叶一律按草色"仍是近似——
  红石的 tintindex 0 不是草色。要精确区分得引入具名色槽。
