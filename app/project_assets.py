"""项目自己的素材包：把绑定的素材组合好，**复制一份进项目**。

为什么不直接用应用缓存里的组合结果（`cache/packages/<指纹>`）：项目目录是用户
自己挑的位置，可能被搬到别的盘、发给别人、几年后再打开。那时全局素材库里的
解压结果早没了，而"重建贴图"偏偏依赖"当时那套素材"（设计文档 §7.6）。所以组合
结果要在项目里留一份，导出只认项目里这份。

于是有两条路径：

1. 绑定没变（`package_fingerprint` 与当前指纹一致）→ 直接用项目里那份，毫秒级；
2. 绑定变了 / 项目里还没有 → 走 `compose()`（按指纹缓存，二次组合很快），
   再把结果复制进项目。

指纹只含"有序的素材 id（= 内容指纹）"，所以"换了个区块再导一次"不会触发重新组合。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .compose import ComposeError, compose, order_fingerprint
from .library import Library
from .project import Project


@dataclass
class ProjectPackage:
    package_dir: Path
    fingerprint: str
    reused: bool        # 直接用了项目里已有的那份
    stale: bool         # 绑定已经对不上，但没别的可用，只能拿旧的顶上
    note: str


def bound_library(project: Project, library: Library) -> Library:
    """把项目绑定的 id 映射回素材库里的条目（顺序就是项目的顺序）。"""
    known = {source.id: source for source in library.sources}
    return Library(
        sources=[known[i] for i in project.materials if i in known],
        enabled=[i for i in project.materials if i in known],
    )


def missing_bindings(project: Project, library: Library) -> list[str]:
    """绑定了但素材库里找不到的 id（换机器、清空重来之后会出现）。"""
    known = {source.id for source in library.sources}
    return [i for i in project.materials if i not in known]


def ensure_package(
    app_dir: Path,
    project: Project,
    library: Library,
    force: bool = False,
) -> ProjectPackage:
    """保证项目里有一份可用的素材包，返回它。没有素材时抛 `ComposeError`。"""
    package_dir = project.package_dir
    have_copy = (package_dir / "block_textures.tsv").is_file()

    bound = bound_library(project, library)
    fingerprint = order_fingerprint(bound) if bound.enabled else ""

    if not bound.enabled:
        if have_copy:
            # 绑定丢了但项目里那份还在：白模不如拿旧的顶上，并在界面说清楚
            return ProjectPackage(
                package_dir, project.package_fingerprint, True, True,
                "绑定的素材不在素材库里了，先用项目里已有的素材包",
            )
        raise ComposeError(
            "这个项目还没有绑定任何素材。请在「素材」里添加，或选择不用材质导出白模。"
        )

    if (
        not force
        and have_copy
        and project.package_fingerprint == fingerprint
    ):
        return ProjectPackage(package_dir, fingerprint, True, False, "项目素材包已就绪")

    # 组合（走指纹缓存），然后把结果复制进项目
    composed = compose(app_dir, bound, force=force)
    if package_dir.exists():
        shutil.rmtree(package_dir, ignore_errors=True)
    shutil.copytree(composed.package_dir, package_dir)
    project.package_fingerprint = fingerprint
    project.save()
    return ProjectPackage(
        package_dir, fingerprint, False, False, composed.note
    )
