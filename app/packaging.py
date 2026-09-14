"""把一次导出打包成"能拷走"的 zip（OBJ + MTL + 这次用到的贴图）。

为什么需要它：项目模式的产物是**项目的一部分**——贴图按内容哈希只存一份在
`<项目>/textures/`，MTL 用相对路径指过去（`map_Kd ../../textures/ab/<sha1>.png`）。
同一个模型导出两次共用同一张图，项目不会因为重复导出而翻倍，这是对的；
但要拿给别人（或者换台机器打开）就得连着 textures/ 一起拷、还得保持相对层级。

所以这里只做"带走"那一步：把 OBJ、MTL 与本次真正引用到的贴图收进一个 zip，
并把 MTL 里的贴图路径改写成**包内**相对路径（`textures/<名字>`）。
解压出来就是自足的目录，Blender / 其他软件直接能用，不需要改任何路径。

产物目录里同时放着 job.json 这类本机路径的文件，**不**进包——那是给本机重建用的。
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# MTL 里指向图片的行：map_Kd / map_Ka / map_Ks / bump / decal / disp / refl
_MAP_LINE = re.compile(r"^\s*(map_\w+|bump|decal|disp|refl)\s+(?P<rest>.+?)\s*$")
# OBJ 里的贴图库引用
_MTLLIB_LINE = re.compile(r"^\s*mtllib\s+(?P<name>.+?)\s*$")


@dataclass
class PackResult:
    """打包结果：包在哪、装了什么、有多少张图没找到。"""

    zip_path: Path
    obj_arc: str
    textures: int
    materials: int
    missing: list[str] = field(default_factory=list)
    size_bytes: int = 0


def _texture_name(rest: str) -> str:
    """从 map_* 那一行的参数里取出文件名。

    行尾可能是 `-o 1 2 3 -s 1 1 1 贴图.png` 这种带选项的写法，所以取**最后一个**
    词；我们的 MTL 写的是最简形式，这条规则对两种都成立。
    """

    tokens = rest.split()
    name = tokens[-1] if tokens else ""
    return name.strip('"')


def _rewrite_mtl(text: str, mtl_dir: Path, into: str = "textures") -> tuple[str, list[Path], list[str]]:
    """改写一份 MTL 的贴图路径，返回（新文本，用到的图片，找不到的图片名）。"""

    used: list[Path] = []
    missing: list[str] = []
    lines: list[str] = []
    for line in text.splitlines():
        match = _MAP_LINE.match(line)
        if match is None:
            lines.append(line)
            continue
        name = _texture_name(match.group("rest"))
        source = (mtl_dir / name)
        if not source.is_file():
            missing.append(name)
            lines.append(line)
            continue
        arc = "%s/%s" % (into, source.name)
        if source not in used:
            used.append(source)
        lines.append("%s %s" % (match.group(1), arc))
    newline = "\n" if text.endswith("\n") else ""
    return "\n".join(lines) + newline, used, missing


def _textures_referenced(obj_dir: Path, mtl_names: list[str]):
    """收集这些 MTL 引用到的贴图，并给出改写后的 MTL 文本。"""

    textures: list[Path] = []
    missing: list[str] = []
    rewritten: dict[str, str] = {}
    for name in mtl_names:
        mtl_path = obj_dir / name
        if not mtl_path.is_file():
            missing.append(name)
            continue
        text = mtl_path.read_text(encoding="utf-8", errors="replace")
        new_text, used, lost = _rewrite_mtl(text, mtl_path.parent)
        rewritten[name] = new_text
        for texture in used:
            if texture not in textures:
                textures.append(texture)
        missing.extend(lost)
    return rewritten, textures, missing


def pack(obj_path: Path | str, zip_path: Path | str | None = None) -> PackResult:
    """把 OBJ 及其贴图打成一个自足的 zip。

    `zip_path` 不给就写在产物目录里，名字是 `<模型名>_便携包.zip`。
    """

    obj = Path(obj_path)
    if not obj.is_file():
        raise FileNotFoundError("找不到要打包的模型：%s" % obj)
    obj_dir = obj.parent
    text = obj.read_text(encoding="utf-8", errors="replace")

    mtl_names: list[str] = []
    for line in text.splitlines():
        match = _MTLLIB_LINE.match(line)
        if match is not None:
            name = match.group("name").strip().strip('"')
            if name and name not in mtl_names:
                mtl_names.append(name)

    rewritten, textures, missing = _textures_referenced(obj_dir, mtl_names)

    # 包里的 MTL 一律放在顶层（用文件名），所以 OBJ 里的 mtllib 也要跟着改成文件名，
    # 免得包里出现 `../x.mtl` 这种指到包外的路径。
    def _to_basename(match: re.Match) -> str:
        name = Path(match.group("name").strip().strip('"')).name
        return "%smtllib %s" % (match.group("pre") or "", name)

    text = re.sub(
        r"^(?P<pre>\s*)mtllib\s+(?P<name>.+?)\s*$",
        _to_basename,
        text,
        flags=re.MULTILINE,
    )
    rewritten = {Path(name).name: body for name, body in rewritten.items()}

    target = Path(zip_path) if zip_path else obj_dir / ("%s_便携包.zip" % obj.stem)
    target.parent.mkdir(parents=True, exist_ok=True)
    obj_arc = obj.name
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(obj_arc, text)
        for name, mtl_text in rewritten.items():
            archive.writestr(name, mtl_text)
        for texture in textures:
            archive.write(texture, "textures/%s" % texture.name)
    size = target.stat().st_size if target.is_file() else 0
    return PackResult(
        zip_path=target,
        obj_arc=obj_arc,
        textures=len(textures),
        materials=len(rewritten),
        missing=missing,
        size_bytes=size,
    )
