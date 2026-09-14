"""检查更新与反馈上报：拼装、脱敏、截断、提交、留痕。

不联网：`ApiClient` 的 opener 是注入的缝，这里全部走替身。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app import report as report_mod  # noqa: E402
from app import update as update_mod  # noqa: E402
from app.api import ApiClient, ApiError  # noqa: E402
from app.report import (  # noqa: E402
    DESC_MAX,
    Report,
    ReportStore,
    attach_log,
    build_payload,
    diagnostics,
    log_tail,
    redact,
    save_log_copy,
    submit,
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def fake_client(payload, *, envelope=True):
    """造一个不会联网的客户端：返回给定的 payload。"""
    def opener(_request):
        body = {"success": True, "payload": payload} if envelope else payload
        return json.dumps(body, ensure_ascii=False).encode("utf-8")

    return ApiClient(opener=opener)


def test_api() -> None:
    print("HTTP 客户端：")
    client = fake_client({"hello": 1})
    check("正常返回 payload", client.post_json("/x", {}) == {"hello": 1})

    def failing(_request):
        raise urllib.error.URLError("connection refused")

    try:
        ApiClient(opener=failing).get_json("/x")
        kind = ""
    except ApiError as error:
        kind = error.kind
    check("连不上算网络问题", kind == "network", kind)

    def refused(_request):
        body = {"success": False, "error_type": "FEEDBACK",
                "error_code": "DESCRIPTION_TOO_LONG",
                "error_message": "描述过长"}
        return json.dumps(body, ensure_ascii=False).encode("utf-8")

    try:
        ApiClient(opener=refused).post_json("/x", {"a": 1})
        kind = message = ""
    except ApiError as error:
        kind, message = error.kind, str(error)
    check("服务器拒绝时带上原因", kind == "server" and message == "描述过长",
          "%s / %s" % (kind, message))

    check("base 拼路径不会双斜杠",
          ApiClient("https://x/api/", opener=lambda r: b'{"success":true,"payload":{}}')
          ._url("/a") == "https://x/api/a")


def test_update() -> None:
    print("检查更新：")
    check("版本号归一化 v1.2.3 → (1,2,3)",
          update_mod.parse_version("v1.2.3") == (1, 2, 3))
    check("预发布后缀不影响主版本", update_mod.parse_version("1.2.3-beta") == (1, 2, 3))
    check("不写修订号按 0 补", update_mod.parse_version("2.0") == (2, 0, 0))
    check("认不出来给 None", update_mod.parse_version("最新版") is None)
    check("比大小：1.0.0 < 1.0.1", update_mod.is_newer("1.0.1", "1.0.0"))
    check("比大小：相同不算新", not update_mod.is_newer("1.0.0", "1.0.0"))
    check("认不出来时不提示", not update_mod.is_newer("最新版", "0.1.0"))

    listed = [{"platform": "macos-arm", "version": "v0.9.0", "downloadUrl": "https://x/a.dmg",
               "note": "12 MB", "ready": True}]
    info = update_mod.check(fake_client(listed), current="0.1.0")
    check("服务器版本更新时给出提示",
          info.has_update and info.latest == "v0.9.0" and info.url.endswith(".dmg"),
          "%s / %s" % (info.has_update, info.latest))

    same = update_mod.check(fake_client(listed), current="0.9.0")
    check("同版本不提示", not same.has_update)

    not_ready = update_mod.check(
        fake_client([dict(listed[0], ready=False)]), current="0.1.0"
    )
    check("地址没配好就不给下载入口",
          not not_ready.has_update and not not_ready.url, not_ready.url)

    missing = update_mod.check(fake_client([]), current="0.1.0")
    check("服务器没有这个平台时不报错（只是没有更新）",
          not missing.has_update and missing.latest == "", missing.latest)


def test_redact() -> None:
    print("脱敏：")
    mac = "错误 at /Users/gaksy/Development/project/app/main.py:12"
    check("macOS 家目录换成 ~", "~" in redact(mac) and "gaksy" not in redact(mac),
          redact(mac))
    win = r"打不开 C:\Users\gaksy\Documents\saves\base\level.dat"
    out = redact(win)
    check("Windows 家目录也换掉", "gaksy" not in out, out)
    check("其它绝对路径只留末两级",
          redact("/var/folders/k8/abc123/outputs/house.obj").count("/") <= 2,
          redact("/var/folders/k8/abc123/outputs/house.obj"))
    check("相对路径不动", redact("outputs/house.obj") == "outputs/house.obj")
    diag = diagnostics({"library": "0.2.0-beta", "cli": "/Users/gaksy/tools/reader"})
    check("诊断里没有用户名", "gaksy" not in diag, diag)
    check("诊断里有库版本与 CLI 位置", "0.2.0-beta" in diag and "reader" in diag, diag)


def test_payload() -> None:
    print("反馈内容：")
    report = Report(title="  导出卡住  ", description="点了导出没反应")
    report.diagnostics = "app=0.1.0；os=Darwin"
    report.log_tail = "line1\nline2"
    attach_log(report)
    payload = build_payload(report)
    check("字段名与服务器一致",
          set(payload) == {"type", "title", "description", "module", "severity",
                           "contact", "pageUrl", "userAgent"}, str(sorted(payload)))
    check("标题去掉空白", payload["title"] == "导出卡住", payload["title"])
    check("默认报 other（服务器只认那五个值）", payload["module"] == "other")
    check("诊断与日志都拼进去了",
          "诊断" in payload["description"] and "line2" in payload["description"])

    long_report = Report(title="t", description="x" * 5000)
    attach_log(long_report)
    check("超长会被截断到服务器上限",
          0 < len(build_payload(long_report)["description"]) <= DESC_MAX,
          str(len(build_payload(long_report)["description"])))

    sent = submit(Report(title="t", description="d"), fake_client({"bugNo": "20260914-001",
                                                                   "dataCode": "ABCD2345"}))
    check("提交拿到编号与数据码",
          sent["bugNo"] == "20260914-001" and sent["dataCode"] == "ABCD2345", str(sent))

    check("日志尾部能读出来", isinstance(log_tail(ROOT / "不存在.log"), str))


def test_store(tmp: Path) -> None:
    print("留痕：")
    store = ReportStore.load(tmp)
    store.add({"bugNo": "20260914-001", "dataCode": "ABCD2345", "title": "t"})
    again = ReportStore.load(tmp)
    check("编号与数据码落盘了",
          again.latest() is not None and again.latest()["dataCode"] == "ABCD2345",
          str(again.items))
    report = Report(title="t", description="d", diagnostics="diag", log_tail="tail")
    target = save_log_copy(report, tmp, "20260914-001")
    check("本机留了一份完整日志",
          target.is_file() and "20260914-001" in target.name and "diag" in target.read_text(encoding="utf-8"),
          str(target))
    check("留档目录在 logs/reports 下", target.parent == tmp / "logs" / "reports",
          str(target.parent))


def main() -> int:
    print("== 检查更新与反馈 ==")
    test_api()
    test_update()
    test_redact()
    test_payload()
    with tempfile.TemporaryDirectory(prefix="lt-report-") as tmp:
        test_store(Path(tmp))
    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
