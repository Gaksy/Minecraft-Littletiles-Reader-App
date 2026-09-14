"""检查更新：拿服务器上的发布版本和应用自己的版本比一比。

数据来源是公开接口 `GET /public/lt-read/downloads`：后台现在是**一次发布一条**，
每条带渠道（`stable` 稳定版 / `beta` 测试版）、更新日志与发布时间，
同一平台可以有很多历史版本。

**客户端只认稳定版**：`channel != 'stable'` 的条目永远不会被当成更新——
测试版是给愿意尝鲜的人去下载页自己拿的，不该弹到所有人脸上。
平台只有两个：`windows` 与 `macos-arm`，和桌面端发布形态对得上。

版本号做归一化比较：服务器写的是 `v1.0.0`，应用里是 `0.1.0`；
还可能出现 `1.2.3-beta` / `1.2.3+build`。比较规则保守——**认不出来就不提示**，
宁可漏报一次，也不要拿错误的字符串比较去骚扰用户。
"""

from __future__ import annotations

import platform
import re
import sys
from dataclasses import dataclass

from . import __version__
from .api import ApiClient, ApiError
from .applog import logger

DOWNLOADS_PATH = "/public/lt-read/downloads"


@dataclass(frozen=True)
class Release:
    """服务器上一条下载项。"""

    platform: str
    version: str
    url: str
    note: str
    ready: bool
    #: stable=稳定版 / beta=测试版
    channel: str = "stable"
    #: 更新日志（纯文本，一行一条）
    changelog: str = ""


@dataclass(frozen=True)
class UpdateInfo:
    """比较结果。`has_update` 为 False 时其余字段只作展示用。"""

    current: str
    latest: str
    has_update: bool
    platform: str
    url: str = ""
    note: str = ""
    #: 服务器上有没有这个平台的条目（有但没填版本号 / 地址，也算"有"）
    listed: bool = False
    #: 服务器上这个平台目前只有测试版（客户端不提示更新，界面上说明一句）
    beta_only: bool = False
    #: 稳定版的更新日志（有就展示）
    changelog: str = ""


def platform_key() -> str:
    """当前机器对应哪个平台键（服务器只认这两个）。"""

    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        machine = platform.machine().lower()
        return "macos-arm" if machine in ("arm64", "aarch64") else "macos-arm"
    return "windows" if sys.platform.startswith("win") else "macos-arm"


def parse_version(text: str) -> tuple[int, ...] | None:
    """把 `v1.2.3-beta` 归一化成 `(1, 2, 3)`；认不出来返回 None。

    只取主版本.次版本.修订号这三段数字：预发布后缀（`-beta`）不参与比较——
    "beta 算不算更新"是有歧义的判断，交给人在下载页看备注更稳妥。
    """

    if not text:
        return None
    cleaned = str(text).strip().lstrip("vV")
    match = re.match(r"^(\d+(?:\.\d+)*)", cleaned)
    if not match:
        return None
    parts = [int(piece) for piece in match.group(1).split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer(latest: str, current: str) -> bool:
    """latest 是否比 current 新（任一边认不出来就返回 False）。"""

    new, old = parse_version(latest), parse_version(current)
    if new is None or old is None:
        return False
    return new > old


def _to_release(item: dict, key: str) -> Release:
    return Release(
        platform=str(item.get("platform", key)),
        version=str(item.get("version") or ""),
        url=str(item.get("downloadUrl") or ""),
        note=str(item.get("note") or ""),
        ready=bool(item.get("ready")),
        channel=str(item.get("channel") or "stable").strip().lower(),
        changelog=str(item.get("changelog") or "").strip(),
    )


def fetch_releases(client: ApiClient, wanted: str | None = None) -> list[Release]:
    """取当前平台的**所有**发布（新的在前，顺序由服务端给定）。"""

    key = wanted or platform_key()
    payload = client.get_json(DOWNLOADS_PATH)
    if not isinstance(payload, list):
        return []
    return [
        _to_release(item, key)
        for item in payload
        if isinstance(item, dict) and item.get("platform") == key
    ]


def fetch_release(client: ApiClient, wanted: str | None = None) -> Release | None:
    """取当前平台**最新稳定版**；没有稳定版（或只有测试版）返回 None。"""

    for release in fetch_releases(client, wanted):
        if release.channel == "stable":
            return release
    return None


def check(client: ApiClient | None = None, current: str | None = None) -> UpdateInfo:
    """查一次更新。网络/服务器出错一律抛 `ApiError`，让调用方决定怎么说。"""

    client = client or ApiClient()
    current = current or __version__
    releases = fetch_releases(client)
    stable = next((item for item in releases if item.channel == "stable"), None)
    if stable is None:
        # 没有稳定版：可能是这个平台压根没条目，也可能只发了测试版。
        # 两种都按"没有更新"处理（客户端只检查稳定版），界面上说明一句。
        logger().info(
            "检查更新：服务器上没有当前平台的稳定版（共 %d 条，%s）",
            len(releases),
            "只有测试版" if releases else "没有条目",
        )
        return UpdateInfo(
            current=current, latest="", has_update=False, platform=platform_key(),
            listed=bool(releases), beta_only=bool(releases),
        )
    release = stable
    newer = release.ready and is_newer(release.version, current)
    logger().info(
        "检查更新：当前 %s，服务器稳定版 %s（ready=%s）→ %s",
        current, release.version or "（未填）", release.ready,
        "有新版" if newer else "已是最新",
    )
    return UpdateInfo(
        current=current,
        latest=release.version,
        has_update=newer,
        platform=release.platform,
        url=release.url if release.ready else "",
        note=release.note,
        listed=True,          # 有条目，只是可能还没填版本号 / 地址
        changelog=release.changelog,
    )
