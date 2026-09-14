"""检查更新与反馈上报：拼装、脱敏、截断、提交、留痕。

不联网：`ApiClient` 的 opener 是注入的缝，这里全部走替身。
"""

from __future__ import annotations

import json
import os
import time
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
    reply_for,
    refresh,
    collect_logs_tar,
    recent_logs,
    upload_bundle,
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
                           "contact", "pageUrl", "source", "locale", "userAgent"},
          str(sorted(payload)))
    check("标题去掉空白", payload["title"] == "导出卡住", payload["title"])
    check("默认报 other（服务器只认那五个值）", payload["module"] == "other")
    check("带上来源（后台据此分栏）", payload.get("source") == "app", str(payload.get("source")))
    check("带惯用语言", payload.get("locale") == "zh-Hans", str(payload.get("locale")))
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

    seen: dict = {}

    def opener(request):
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return json.dumps({"success": True, "payload": {"bugNo": "20260914-001",
                                                        "dataCode": "ABCD2345",
                                                        "uploadToken": "9f3c"}}).encode("utf-8")

    submit(Report(title="t", description="d"), ApiClient(opener=opener), want_attachment=True)
    check("要附件时带上 wantAttachment 标记",
          seen["payload"].get("wantAttachment") is True, str(seen["payload"].get("wantAttachment")))
    submit(Report(title="t", description="d"), ApiClient(opener=opener))
    check("不要附件时不带这个字段（保持老契约）",
          "wantAttachment" not in seen["payload"], str(sorted(seen["payload"])))


def test_logs(tmp: Path) -> None:
    print("日志包：")
    logs = tmp / "logs"
    (logs / "reports").mkdir(parents=True)
    fresh = logs / "2026-09-14_100000.log"
    fresh.write_text("app=0.1.0\nerror at /Users/gaksy/proj/app/main.py:12\n" * 300,
                     encoding="utf-8")
    old = logs / "2026-09-01_100000.log"
    old.write_text("很旧的一行\n", encoding="utf-8")
    os.utime(old, (time.time() - 3 * 86400,) * 2)

    window = recent_logs(tmp, hours=24)
    names = [item.rel for item in window]
    check("24 小时内动的日志才算", names == ["2026-09-14_100000.log"], str(names))

    bundle = collect_logs_tar(tmp, 24, diagnostics_text="app=0.1.0；os=Darwin")
    check("打成了 tar.gz", bundle is not None and bundle.path.is_file()
          and bundle.name.endswith(".tar.gz"), str(bundle))
    check("文件数对得上", bundle.files == 1, str(bundle.files))
    check("算了 sha256", len(bundle.sha256) == 64, bundle.sha256[:16])

    import tarfile
    with tarfile.open(bundle.path) as archive:
        inside = archive.getnames()
        readme = archive.extractfile("README.txt").read().decode("utf-8")
        body = archive.extractfile("logs/2026-09-14_100000.log").read().decode("utf-8")
    check("包内有 README 与日志", "README.txt" in inside
          and "logs/2026-09-14_100000.log" in inside, str(inside))
    check("README 写了时间窗与诊断", "24 小时" in readme and "os=Darwin" in readme)
    check("日志做了脱敏", "gaksy" not in body and "~/…/app/main.py" in body,
          body.splitlines()[1] if len(body.splitlines()) > 1 else body)
    check("旧日志没进包", "2026-09-01_100000.log" not in " ".join(inside), str(inside))
    check("上一次打的包不会再被包一遍",
          not any(n.endswith(".tar.gz") for n in inside), str(inside))

    # 体积上限：把上限压到很小，只装得下最新的那个
    small = collect_logs_tar(tmp, 24, max_bytes=4096, out_dir=tmp / "out")
    check("超上限时连一份都放不下 → 只留尾部，包不超上限",
          small is not None and small.files == 1 and small.size <= 4096,
          "files=%s size=%s" % (small.files if small else None, small.size if small else None))
    with tarfile.open(small.path) as archive:
        note = archive.extractfile("README.txt").read().decode("utf-8")
        tail_name = [n for n in archive.getnames() if "仅尾部" in n]
    check("README 说明了只留尾部", "只留了尾部" in note,
          " / ".join(line for line in note.splitlines() if "上限" in line))
    check("包内文件名也标了", len(tail_name) == 1, str(tail_name))


def test_upload(tmp: Path) -> None:
    print("日志包上传（multipart）：")
    bundle_file = tmp / "littletiles-logs-test.tar.gz"
    bundle_file.write_bytes(b"\x1f\x8b fake gzip")
    bundle = report_mod.LogBundle(path=bundle_file, name=bundle_file.name,
                                  size=bundle_file.stat().st_size, sha256="a" * 64,
                                  files=3, hours=24, redacted=True)
    seen: dict = {}

    def opener(request):
        seen["url"] = request.full_url
        seen["type"] = request.get_header("Content-type") or ""
        seen["body"] = request.data or b""
        return json.dumps({"success": True, "payload": {"name": bundle.name,
                                                        "size": bundle.size,
                                                        "sha256": bundle.sha256}}
                          ).encode("utf-8")

    result = upload_bundle(bundle, "9f3c" * 8, ApiClient(opener=opener))
    check("打到了附件接口", seen["url"].endswith("/feedback/attach"), seen["url"])
    check("用的是 multipart", seen["type"].startswith("multipart/form-data; boundary="),
          seen["type"])
    check("带上了 uploadToken 字段", b'name="uploadToken"' in seen["body"])
    check("带上了文件与文件名", b'name="file"; filename="' in seen["body"]
          and b"fake gzip" in seen["body"])
    check("服务器回的是元信息", result.get("sha256") == "a" * 64, str(result))

    try:
        upload_bundle(bundle, "")
        raised = ""
    except ApiError as error:
        raised = error.kind
    check("没凭证就直说", raised == "client", raised)


def test_tracking(tmp: Path) -> None:
    print("反馈状态追踪：")
    store = ReportStore.load(tmp)
    store.add({"bugNo": "20260914-003", "dataCode": "WXYZ2345", "title": "t",
               "locale": "zh-Hant", "seenAt": None})
    store.add({"bugNo": "20260914-004", "dataCode": "ABCD2345", "title": "u",
               "seenAt": "2026-09-14 22:00:00"})      # 已读：不该再自动查
    check("只自动查没看过的", [e["bugNo"] for e in store.unresolved()] == ["20260914-003"],
          str(store.unresolved()))

    def client_for(payload):
        def opener(_request):
            return json.dumps({"success": True, "payload": payload},
                              ensure_ascii=False).encode("utf-8")

        return ApiClient(opener=opener)

    solved = refresh(store, client_for({"status": "resolved", "statusName": "已解决",
                                        "opinion": "已修复", "resolution": "0.2.0 修复",
                                        "opinionI18n": "已修復", "resolutionI18n": "0.2.0 修復",
                                        "localeName": "繁體中文"}))
    check("查到新结论会报出来", [e["bugNo"] for e in solved] == ["20260914-003"],
          str([e["bugNo"] for e in solved]))
    entry = store.by_code("WXYZ2345")
    check("状态与回复写进本地", entry is not None and entry["status"] == "resolved"
          and entry["resolutionI18n"] == "0.2.0 修復", str(entry and entry.get("status")))
    check("记了查询时间", bool(entry and entry.get("lastCheckedAt")))

    store.mark_seen(entry)
    check("标记已读后不再自动查", not store.unresolved())
    check("再查一次不会重复报", refresh(store, client_for({"status": "resolved"})) == [])

    text, origin = reply_for(entry, "resolution")
    check("回复优先给译文", text == "0.2.0 修復" and origin == "0.2.0 修复",
          "%s / %s" % (text, origin))
    plain = {"resolution": "只有中文"}
    text2, origin2 = reply_for(plain, "resolution")
    check("没译文就如实给中文", text2 == "只有中文" and origin2 is None, str((text2, origin2)))

    store.remove("WXYZ2345")
    check("能删本机记录", store.by_code("WXYZ2345") is None)


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
        root = Path(tmp)
        test_logs(root / "logs-case")
        test_tracking(root / "tracking")
        test_upload(root)
        test_store(root)
    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
