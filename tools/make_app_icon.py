"""画应用图标：**像素风 3D 打印机**（导出器），并生成 .ico / .icns。

为什么用脚本画而不是开设计软件：

* 图标要跟应用同一套风格（草绿 + 石头灰 + 直角，和 `app/ui/design/tokens.py` 一致），
  画在代码里就永远对得上，改颜色改形状都是一行；
* 像素画的本质是"32×32 的格子"，脚本里就是一张色块表，比在 PS 里点像素好维护；
* 导出 ico/icns 不需要额外依赖：两种容器格式都是"头 + 若干 PNG"，这里手写（见文件下半部）。

用法：

```sh
python tools/make_app_icon.py              # 按内置像素表画，输出 png/ico/icns
python tools/make_app_icon.py --preview    # 只出一张 1024 的 png，先看效果
python tools/make_app_icon.py --from-png   # 用 packaging/app.png（自己出的图）转 ico/icns
```

产物都在 `packaging/`：`app.png`（预览用）、`app.ico`（Windows）、`app.icns`（macOS）。
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"
GRID = 32                      # 像素画分辨率：32×32 格

# ---- 调色（取自 app/ui/design/tokens.py 的组件库调色板）-----------------
GREEN_6 = "#2a641c"
GREEN_5 = "#3c8527"
GREEN_3 = "#6cc349"
GREY_6 = "#262423"
GREY_5 = "#3d3938"
GREY_4 = "#6b6562"
GREY_3 = "#aba09c"
GREY_2 = "#d0c5c0"
GREY_1 = "#ede5e2"
YELLOW = "#fffc70"

#: 像素表：(x, y, 宽, 高, 颜色)。坐标以左上角为原点，一格 = 1 像素。
PIXELS: list[tuple[int, int, int, int, str]] = [
    # 底：深灰石面 + 一圈浅一点的边（深浅系统背景上都站得住）
    (0, 0, GRID, GRID, GREY_6),
    (0, 0, GRID, 1, GREY_5),
    (0, GRID - 1, GRID, 1, GREY_5),
    (0, 0, 1, GRID, GREY_5),
    (GRID - 1, 0, 1, GRID, GREY_5),

    # ---- 框架：立柱 + 顶梁 + 底梁（占满画面，别留大块空白）----
    (4, 4, 2, 24, GREY_2),            # 左立柱
    (26, 4, 2, 24, GREY_2),           # 右立柱
    (4, 4, 24, 2, GREY_1),            # 顶梁
    (4, 27, 24, 1, GREY_4),           # 底梁
    (4, 28, 24, 1, GREY_5),

    # ---- Z 轴横梁（比框架暗一档，区分层次）----
    (6, 12, 20, 2, GREY_3),

    # ---- 耗材：从顶梁垂下来的一根亮黄 ----
    (15, 6, 2, 6, YELLOW),

    # ---- 挤出机：细长绿色头 + 深绿喷嘴 ----
    (14, 14, 4, 3, GREEN_5),
    (15, 17, 2, 1, GREEN_6),

    # ---- 正在打印的模型：立方体（顶面亮 / 正面中 / 侧面暗）----
    (12, 20, 7, 1, GREEN_3),          # 顶面
    (12, 21, 7, 4, GREEN_5),          # 正面
    (18, 21, 1, 4, GREEN_6),          # 右侧面（暗）
    (11, 25, 9, 1, GREEN_6),          # 已经打好的底座

    # ---- 打印平台（模型站在上面，别把模型切掉）----
    (6, 26, 20, 1, GREY_3),           # 台面
]


def render(size: int = 1024):
    """把像素表画成一张 QImage（最近邻放大，保持硬边像素感）。"""

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage, QPainter

    image = QImage(GRID, GRID, QImage.Format.Format_ARGB32)
    image.fill(QColor(GREY_6))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    for x, y, w, h, color in PIXELS:
        painter.fillRect(x, y, w, h, QColor(color))
    painter.end()
    return image.scaled(
        size, size,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,      # 最近邻：保持像素硬边
    )


# ---- 容器格式：ICO / ICNS 都是"头 + 若干 PNG" --------------------------

def png_bytes(image, size: int) -> bytes:
    """把某个尺寸的图标编码成 PNG 字节。

    注意 `QByteArray` 要**单独持有**：写成 `QBuffer(QByteArray())` 时那个临时对象
    会被立刻回收，QBuffer 拿着悬空指针，保存时直接段错误（这里踩过一次）。
    """
    from PySide6.QtCore import QBuffer, QByteArray, Qt
    scaled = image.scaled(
        size, size,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,      # 最近邻：像素边不糊
    )
    data = QByteArray()                                 # ← 必须留引用
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    scaled.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def write_ico(path: Path, image, sizes=(16, 32, 48, 64, 128, 256)) -> None:
    """ICO：6 字节头 + 16 字节目录项/图 + PNG 数据（Vista 起允许直接内嵌 PNG）。

    目录项里宽高写 0 表示 256（ICO 格式的约定）。
    """

    payloads = [(size, png_bytes(image, size)) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(payloads))
    offset = len(header) + 16 * len(payloads)
    entries, blobs = b"", b""
    for size, blob in payloads:
        entries += struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0, size if size < 256 else 0,
            0, 0, 1, 32, len(blob), offset,
        )
        offset += len(blob)
        blobs += blob
    path.write_bytes(header + entries + blobs)


#: ICNS 的类型码 ↔ 像素尺寸（苹果的固定表，只用得到这几个）
ICNS_TYPES = [
    (b"icp4", 16), (b"icp5", 32), (b"icp6", 64),
    (b"ic07", 128), (b"ic08", 256), (b"ic09", 512),
    (b"ic10", 1024), (b"ic11", 32), (b"ic12", 64),
    (b"ic13", 256), (b"ic14", 512),
]


def write_icns(path: Path, image) -> None:
    """ICNS：`icns` + 总长度 + 若干「类型 + 长度 + PNG」。"""

    chunks = b""
    for type_code, size in ICNS_TYPES:
        blob = png_bytes(image, size)
        chunks += type_code + struct.pack(">I", len(blob) + 8) + blob
    path.write_bytes(b"icns" + struct.pack(">I", len(chunks) + 8) + chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description="画应用图标（像素风 3D 打印机）")
    parser.add_argument("--preview", action="store_true", help="只出 app.png")
    parser.add_argument("--from-png", action="store_true",
                        help="用 packaging/app.png 转 ico/icns（你自己出的图）")
    parser.add_argument("--size", type=int, default=1024, help="预览图边长，默认 1024")
    args = parser.parse_args()

    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication, QImage

    app = QGuiApplication.instance() or QGuiApplication([])
    PACKAGING.mkdir(parents=True, exist_ok=True)
    preview = PACKAGING / "app.png"

    if args.from_png:
        image = QImage(str(preview))
        if image.isNull():
            print("读不到 %s —— 先放一张 1024×1024 的 PNG 进来" % preview)
            return 2
    else:
        image = render(args.size)
        image.save(str(preview), "PNG")
        print("预览图：%s（%d×%d，像素格 %d×%d）"
              % (preview.relative_to(ROOT), args.size, args.size, GRID, GRID))
        if args.preview:
            return 0

    write_ico(PACKAGING / "app.ico", image)
    write_icns(PACKAGING / "app.icns", image)
    print("Windows 图标：%s" % (PACKAGING / "app.ico").relative_to(ROOT))
    print("macOS 图标：%s" % (PACKAGING / "app.icns").relative_to(ROOT))
    print("（打包时自动带上：见 tools/build_app.py 里的 --icon）")
    return 0


if __name__ == "__main__":
    sys.exit(main())