# minecraft-littletiles-reader-app

**LittleTiles Reader 的桌面应用**：把"素材组合 → 选存档 → 选区块 → 导出 OBJ/贴图"
从命令行搬到图形界面，并加上素材、模组、项目与导出记录的管理。

> 状态：**设计阶段**，尚无代码。设计文档见 [`docs/design.md`](docs/design.md)。

## 四个仓库的分工

| 仓库 | 角色 |
|---|---|
| `minecraft-littletiles-reader` | **库**（C++ 核心 + CLI）：读存档/NBT、几何、材质烘焙、写 OBJ/MTL/贴图 |
| `minecraft-littletiles-reader-tools` | **生成端**（Python）：素材包组合、映射表、manifest、tint、基准与校验 |
| `minecraft-littletiles-reader-data` | **测试数据**：regions / snbt / matlab / assets |
| `minecraft-littletiles-reader-app`（本仓库） | **桌面应用**（Python + PySide6）：界面、项目管理、记录与查询 |

## 技术选型

**Python 3.11 + PySide6（Qt Widgets）**，库以**子进程 + job JSON** 方式调用。

选它的决定性理由是：素材组合、jar 解析、映射表归一化这些活**生成端已经用 Python 写好了**，
UI 可以直接复用；而库目前不是线程安全的、会往 stdout 打印，放进子进程刚好隔离。

详细取舍见 [`docs/design.md`](docs/design.md) §2。

## 依赖

```sh
conda activate minecraft-littletiles-reader   # 或自建 venv
pip install PySide6
```

应用跑起来还需要库编出来的 `LittleTilesReader`（sidecar），路径可在配置里指定。

## 现状

- [x] 需求整理与设计文档
- [ ] **M0（库侧）**：`--job` 非交互入口 + 结构化进度 —— **应用的前置依赖**
- [ ] M1 应用骨架：配置、子进程调用、进度、最小导出闭环
- [ ] M2 项目管理
- [ ] M3 素材与模组管理
- [ ] M4 导出记录与区块查询
- [ ] M5 打包分发

里程碑的依赖关系见 [`docs/design.md`](docs/design.md) §8。
