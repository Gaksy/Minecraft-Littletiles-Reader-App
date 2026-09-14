# packaging/

打包用到的**静态资源**放这里（脚本见 [`../tools/build_app.py`](../tools/build_app.py)，
方案与取舍见 [`../docs/packaging.md`](../docs/packaging.md)）。

| 文件 | 用途 | 现状 |
|---|---|---|
| `app.ico` | Windows 可执行文件图标（多尺寸） | **待补**（放进来自动生效） |
| `app.icns` | macOS `.app` 图标 | **待补** |

两个文件**都是可选的**：不存在时 `build_app.py` 会跳过图标并打印一句提示，构建不会失败。

## 图标怎么出（两条路）

1. **我按站点风格画一版**：`python tools/make_app_icon.py` 会用应用自己的
   设计令牌（草绿 + 石头灰 + 直角像素）画一张 1024×1024 的图标，
   再生成 `app.ico`（16/32/48/64/128/256）与 `app.icns`（16…512@2x）。
   想改风格就改那个脚本里的颜色/形状，不用开设计软件。
2. **你自己出图**：准备一张 1024×1024 的 PNG，放成 `packaging/app.png`，
   再跑 `python tools/make_app_icon.py --from-png`，它会转成 ico/icns。

> ⚠️ 别直接拿模组的 logo（`littletiles.png`）或 Mojang 的素材当应用图标——
> 那是别人的标识，随包分发要注意授权（`docs/licenses.md` 里提过）。

## 图标生成脚本还没写？

`tools/make_app_icon.py` 属于"下一步"（见本文末）；在此之前，
把现成的 `app.ico` / `app.icns` 丢进本目录即可，构建脚本认得。
