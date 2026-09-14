"""检查更新：客户端只认稳定版（服务器上一条发布带 channel）。

这条是产品要求，不是实现细节：后台一次发布一条，可以勾「测试版」；
测试版只该出现在网页下载页里，不能被客户端当成"有新版"弹给所有人。
本用例把各种服务器返回组合钉死。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.update import check, fetch_release, is_newer, parse_version  # noqa: E402

FAILURES: list[str] = []


def expect(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


class FakeClient:
    """只实现 get_json —— update.py 只用这一个方法。"""

    def __init__(self, payload) -> None:
        self.payload = payload

    def get_json(self, path: str):
        return self.payload


def row(platform: str, version: str, channel: str, url: str = "", **extra):
    data = {
        "platform": platform,
        "version": version,
        "channel": channel,
        "downloadUrl": url,
        "note": "",
        "ready": bool(url),
    }
    data.update(extra)
    return data


def main() -> int:
    print("== 检查更新：只认稳定版 ==")

    # 1. 同时有稳定版与更新的测试版：挑稳定版，测试版不参与
    payload = [
        row("macos-arm", "0.3.0", "beta", "https://x/beta.dmg"),
        row("macos-arm", "0.2.0", "stable", "https://x/stable.dmg"),
    ]
    release = fetch_release(FakeClient(payload), "macos-arm")
    expect("有稳定版时取稳定版", release is not None and release.version == "0.2.0",
           release.version if release else "None")
    info = check(FakeClient(payload), current="0.1.0")
    expect("稳定版更新会提示", info.has_update and info.latest == "0.2.0")
    expect("测试版不参与比较", info.latest != "0.3.0")

    # 2. 只有测试版：不提示更新，但界面上要能说明"只有测试版"
    only_beta = [row("macos-arm", "0.9.0", "beta", "https://x/beta.dmg")]
    info = check(FakeClient(only_beta), current="0.1.0")
    expect("只有测试版时不提示更新", not info.has_update, info.latest or "(空)")
    expect("只有测试版时标记 beta_only", info.beta_only)
    expect("只有测试版时仍算有条目", info.listed)

    # 3. 一条都没有：既不是 beta_only，也不提示
    info = check(FakeClient([]), current="0.1.0")
    expect("没有条目时不提示更新", not info.has_update)
    expect("没有条目时不是 beta_only", not info.beta_only and not info.listed)

    # 4. 缺 channel 字段（老数据 / 老服务端）按稳定版处理，别把用户卡住
    legacy = row("macos-arm", "0.2.0", "", "https://x/old.dmg")
    del legacy["channel"]
    info = check(FakeClient([legacy]), current="0.1.0")
    expect("老数据没 channel 也认稳定版", info.has_update and info.latest == "0.2.0")

    # 5. 更新日志跟着稳定版走
    with_notes = [
        row("macos-arm", "0.2.0", "stable", "https://x/stable.dmg",
            changelog="修了导出闪退\n加了 DMG"),
    ]
    info = check(FakeClient(with_notes), current="0.1.0")
    expect("更新日志会带出来", info.changelog.startswith("修了导出闪退"),
           repr(info.changelog))

    # 6. 版本比较本身（v 前缀、预发布后缀、认不出来）
    expect("v 前缀能剥掉", parse_version("v1.2.3") == (1, 2, 3))
    expect("预发布后缀不参与", parse_version("1.2.3-beta") == (1, 2, 3))
    expect("认不出来返回 None", parse_version("latest") is None)
    expect("1.10 比 1.9 新（按数字不按字符串）", is_newer("1.10.0", "1.9.0"))
    expect("认不出来就不提示", not is_newer("abc", "0.1.0"))

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
