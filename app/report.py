"""反馈上报：把"用户写的话 + 机器诊断 + 日志尾部"打包发给服务器。

服务器现状（见 `docs/update-and-feedback.md` 的评估）：

- `POST /feedback/submit` 公开可用，字段 `type/title/description/module/severity/
  contact/pageUrl/userAgent`，`description` 上限 **2000 字符**，超了服务器直接报错；
- **没有附件字段、也没有公开上传接口**，所以日志只能挤进 description。

因此这里的三条硬约束：

1. 拼装之后必须 ≤ 2000 字符：先放用户写的正文，再放诊断，最后放**尽可能长**的
   日志尾部（截断时明确写"已截断"）；
2. 一律先过**脱敏**：家目录 → `~`、其它绝对路径只留末两级，且不收集存档路径、
   世界名、项目名；
3. 完整日志另外落在 `logs/reports/<时间戳>_<编号>.txt`，并把编号与数据码记进
   `config/reports.json`——数据码是匿名查进度的唯一凭证，不能只显示一次就没了。

服务器以后加了 `diagnostics` 字段，只要把 `attach_log()` 改成往那个字段塞就行。
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import re
import sys
import tarfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import __version__
from .api import ApiClient, ApiError
from .applog import logger, session_path

DESC_MAX = 2000              # 服务器（FeedbackServiceImpl.DESC_MAX）的硬限制
TITLE_MAX = 128
LOG_TAIL = 1200              # 留给日志的字符数（剩下的给正文与诊断）

SUBMIT_PATH = "/feedback/submit"
QUERY_PATH = "/feedback/query"
ATTACH_PATH = "/feedback/attach"

#: 服务器只认 web / server / account / site / other（评估里建议加 app）
DEFAULT_MODULE = "other"
SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
TYPES = ("bug", "suggestion")

#: 日志包：默认打最近 24 小时，客户端自留上限 8 MB（服务器还有更硬的限制）
LOG_WINDOW_HOURS = 24
BUNDLE_MAX_BYTES = 8 * 1024 * 1024


@dataclass
class Report:
    """一次反馈的内容（提交前后都用它传递）。"""

    title: str
    description: str
    type: str = "bug"
    severity: str = "MEDIUM"
    module: str = DEFAULT_MODULE
    contact: str = ""
    diagnostics: str = ""
    log_tail: str = ""
    #: 提交者惯用语言（后台据此给译文；填的是应用当前界面语言）
    locale: str = "zh-Hans"
    payload: dict = field(default_factory=dict)


# ---- 脱敏 ---------------------------------------------------------------

_HOME_PATTERNS = (
    re.compile(r"[A-Za-z]:\\Users\\[^\\/\s]+", re.I),
    re.compile(r"[A-Za-z]:/Users/[^/\s]+", re.I),
    re.compile(r"/(?:Users|home)/[^/\s]+"),
)
_ABS_PATH = re.compile(r"(?:[A-Za-z]:\\[^\s\"']+|/(?:[^\s\"'/:]+/)+[^\s\"'/:]+)")


def redact(text: str, *, keep_parts: int = 2) -> str:
    """去掉家目录与路径里的用户名，绝对路径只留末几级。

    目标不是"绝对安全"，而是**不主动往外送**用户目录、存档位置这类信息；
    日志里几乎每行都有路径，所以这一步必须在拼 description 之前做。
    """

    if not text:
        return ""

    def short(match: re.Match) -> str:
        raw = match.group(0)
        # 统一分隔符后再取末几级，Windows / macOS 两套写法都能用
        parts = [piece for piece in re.split(r"[\\/]+", raw) if piece]
        if len(parts) <= keep_parts:
            return raw
        return "…/" + "/".join(parts[-keep_parts:])

    for pattern in _HOME_PATTERNS:
        text = pattern.sub("~", text)
    text = _ABS_PATH.sub(short, text)
    # 家目录替换后再缩短会拼出 "~…/" 这种怪样子，写成 "~/…/"
    return text.replace("~…/", "~/…/").replace("~\\…\\", "~\\…\\")


# ---- 诊断信息 -----------------------------------------------------------

def diagnostics(extra: dict | None = None) -> str:
    """机器与版本信息（**不含**任何用户数据）。"""

    lines = [
        "app=%s" % __version__,
        "os=%s %s" % (platform.system(), platform.release()),
        "python=%s" % platform.python_version(),
        "qt=PySide6",
        "frozen=%s" % bool(getattr(sys, "frozen", False)),
    ]
    for key, value in (extra or {}).items():
        if value not in (None, ""):
            lines.append("%s=%s" % (key, value))
    return redact("；".join(lines))


def log_tail(path: Path | str | None = None, limit: int = LOG_TAIL) -> str:
    """取当前会话日志的尾部（脱敏 + 截断）。"""

    target = Path(path) if path is not None else session_path()
    if not target or not Path(target).is_file():
        return ""
    try:
        text = Path(target).read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        logger().warning("读日志失败：%s（%s）", target, error)
        return ""
    tail = text[-limit:] if len(text) > limit else text
    if len(text) > limit:
        tail = "…（日志已截断，只保留最后 %d 字符）\n%s" % (limit, tail)
    return redact(tail)


# ---- 日志包（近 24 小时 → tar.gz） --------------------------------------

@dataclass
class LogBundle:
    """打好包的日志：交给服务器附件接口上传。"""

    path: Path
    name: str
    size: int
    sha256: str
    files: int
    hours: int
    redacted: bool
    skipped: int = 0          # 因为超过体积上限没装进去的文件数


@dataclass
class LogFile:
    path: Path
    rel: str
    mtime: float
    size: int


def recent_logs(app_dir: Path | str, hours: int = LOG_WINDOW_HOURS) -> list[LogFile]:
    """最近 N 小时动过的日志文件（会话日志 + 反馈留档）。

    按修改时间筛，不是按文件名——会话日志的文件名带启动时间，但**一直写到退出**，
    所以"今天凌晨启动、现在还在写"的那份也必须算进来。
    """

    root = Path(app_dir) / "logs"
    if not root.is_dir():
        return []
    cutoff = time.time() - hours * 3600
    found: list[LogFile] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        # 压缩包一律不收：`logs/reports/` 里放的就是历次打的日志包，
        # 不排除的话"这次的包会把上次的包再包一遍"，越滚越大
        lowered = path.name.lower()
        if lowered.endswith((".tar.gz", ".tgz", ".zip", ".tar")):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_mtime < cutoff:
            continue
        found.append(
            LogFile(
                path=path,
                rel=str(path.relative_to(root)).replace(os.sep, "/"),
                mtime=stat.st_mtime,
                size=stat.st_size,
            )
        )
    # 新的排前面：超上限时先保新的
    found.sort(key=lambda item: item.mtime, reverse=True)
    return found


def collect_logs_tar(
    app_dir: Path | str,
    hours: int = LOG_WINDOW_HOURS,
    *,
    diagnostics_text: str = "",
    redacted: bool = True,
    max_bytes: int = BUNDLE_MAX_BYTES,
    out_dir: Path | str | None = None,
) -> LogBundle | None:
    """把最近 N 小时的日志打成一个 tar.gz，返回包信息（没有日志就返回 None）。

    * 默认**脱敏**后再进包（家目录 → ~、绝对路径只留末两级）：日志里几乎每行都有路径，
      原样上传等于把"本机用户名 + 目录结构"送给服务器；
    * 超过 `max_bytes` 时**从最旧的开始丢**，并把丢掉的条数写进 README；
    * 包内一定带一份 `README.txt`：版本、诊断、时间窗、清单——管理员不查数据库也能看懂。
    """

    app_dir = Path(app_dir)
    files = recent_logs(app_dir, hours)
    when = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = "littletiles-logs-%s.tar.gz" % when
    target_dir = Path(out_dir) if out_dir else app_dir / "logs" / "reports"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / name

    # `max_bytes` 约束的是**成品包**大小（正文之外还有 tar 头、gzip 头与 README）。
    # 先按"上限 - 预留"排一遍，写完量一次；超了就按超出的量回缩重排，最多来回几次。
    OVERHEAD = 4096
    budget = max(256, max_bytes - OVERHEAD)
    kept: list[tuple[LogFile, bytes, bool]] = []
    skipped = 0
    for attempt in range(6):
        kept, skipped, rendered = _select_logs(files, budget, redacted)
        _write_bundle(target, kept, rendered, skipped, hours, max_bytes,
                      diagnostics_text, redacted)
        size = target.stat().st_size
        if size <= max_bytes or budget <= 256:
            break
        budget = max(256, budget - (size - max_bytes) - 256)

    if not kept and not diagnostics_text:
        target.unlink(missing_ok=True)
        return None

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return LogBundle(
        path=target,
        name=name,
        size=target.stat().st_size,
        sha256=digest,
        files=len(kept),
        hours=hours,
        redacted=redacted,
        skipped=skipped,
    )


def _select_logs(files, budget: int, redacted: bool):
    """按预算挑日志：优先新的；超预算的整份丢；一份都放不下时只留尾部。"""
    kept: list[tuple[LogFile, bytes, bool]] = []
    skipped = 0
    total = 0
    for item in files:
        remaining = budget - total
        if remaining <= 0:
            skipped += 1
            continue
        try:
            text = item.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if redacted:
            text = redact(text)
        payload = text.encode("utf-8")
        truncated = False
        if len(payload) > remaining:
            if kept:
                skipped += 1
                continue
            payload = payload[-remaining:]
            truncated = True
        total += len(payload)
        kept.append((item, payload, truncated))
    return kept, skipped, total


def _write_bundle(target, kept, rendered, skipped, hours, max_bytes,
                  diagnostics_text, redacted) -> None:
    with tarfile.open(target, "w:gz") as archive:
        for item, payload, truncated in reversed(kept):     # 包里按时间正序
            info = tarfile.TarInfo(
                name="logs/" + item.rel + ("（仅尾部）" if truncated else "")
            )
            info.size = len(payload)
            info.mtime = int(item.mtime)
            archive.addfile(info, io.BytesIO(payload))

        readme = "\n".join(
            [
                "LittleTiles Reader 日志包",
                "打包时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "时间窗：最近 %d 小时（按修改时间）" % hours,
                "脱敏：%s" % ("是（家目录→~，绝对路径只留末两级）" if redacted else "否"),
                "文件数：%d%s"
                % (
                    len(kept),
                    ("（另有 %d 个因体积上限未装入）" % skipped) if skipped else "",
                ),
                "包大小上限：%d 字节%s"
                % (max_bytes, "（超上限的那份只留了尾部）"
                   if any(flag for _, _, flag in kept) else ""),
                "",
                "—— 诊断 ——",
                diagnostics_text or "（无）",
                "",
                "—— 清单 ——",
            ]
            + [
                "%s\t%s%s\t%d 字节"
                % (
                    datetime.fromtimestamp(item.mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    item.rel,
                    "（仅尾部）" if truncated else "",
                    len(payload),
                )
                for item, payload, truncated in reversed(kept)
            ]
            + ["", "说明：日志里的路径已按上面的规则处理；不含存档内容与项目数据。", ""]
        ).encode("utf-8")
        info = tarfile.TarInfo(name="README.txt")
        info.size = len(readme)
        info.mtime = int(time.time())
        archive.addfile(info, io.BytesIO(readme))


def upload_bundle(bundle: LogBundle, upload_token: str, client: ApiClient | None = None) -> dict:
    """把日志包交给服务器（需要提交反馈时拿到的 uploadToken，一次有效）。"""

    if not upload_token:
        raise ApiError("这条反馈没有拿到上传凭证", kind="client")
    client = client or ApiClient()
    result = client.post_file(
        ATTACH_PATH, bundle.path, fields={"uploadToken": upload_token}
    )
    logger().info(
        "日志包已上传：%s（%d 字节，sha256=%s）",
        bundle.name, bundle.size, bundle.sha256[:12],
    )
    return result if isinstance(result, dict) else {}


# ---- 拼装与提交 ---------------------------------------------------------

def attach_log(report: Report) -> Report:
    """把诊断与日志塞进 description（服务器现在没有附件字段）。"""

    blocks = [report.description.strip()]
    if report.diagnostics:
        blocks.append("—— 诊断 ——\n%s" % report.diagnostics)
    if report.log_tail:
        blocks.append("—— 日志尾部 ——\n%s" % report.log_tail)
    text = "\n\n".join(block for block in blocks if block)
    report.description = text[:DESC_MAX]
    return report


def build_payload(report: Report, *, page_url: str = "desktop-app") -> dict:
    """转换成服务器要的 JSON（字段名与 FeedbackSubmitRequest 一一对应）。"""

    return {
        "type": report.type if report.type in TYPES else "bug",
        "title": report.title.strip()[:TITLE_MAX],
        "description": report.description[:DESC_MAX],
        "module": report.module,
        "severity": report.severity if report.severity in SEVERITIES else "MEDIUM",
        "contact": report.contact.strip(),
        # 桌面端没有 URL，填一个能看出来的标记，后台一眼知道来源
        "pageUrl": page_url,
        # 后台按 source 分栏（网站 / 桌面客户端）；locale 决定回复用哪种语言
        "source": "app",
        "locale": report.locale or "zh-Hans",
        "userAgent": "LittleTilesReader/%s (%s)" % (__version__, platform.system()),
    }


def submit(
    report: Report,
    client: ApiClient | None = None,
    *,
    want_attachment: bool = False,
) -> dict:
    """提交一次反馈，返回服务器的 `{bugId, bugNo, dataCode, uploadToken?}`。

    `want_attachment=True` 时请服务器发一张上传凭证（`uploadToken`），
    接着用 `upload_bundle()` 把日志包传上去——分开两步是因为服务器那边
    提交是 JSON、附件是 multipart，而且附件失败不该影响"反馈已经提交"。
    """

    client = client or ApiClient()
    attach_log(report)
    payload = build_payload(report)
    if want_attachment:
        payload["wantAttachment"] = True
    report.payload = payload
    if len(payload["description"]) > DESC_MAX:
        raise ApiError("描述太长了", kind="client")
    result = client.post_json(SUBMIT_PATH, payload)
    if not isinstance(result, dict):
        raise ApiError("服务器没有返回编号", kind="bad_response")
    logger().info(
        "反馈已提交：%s（severity=%s, module=%s, %d 字符）",
        result.get("bugNo"), payload["severity"], payload["module"],
        len(payload["description"]),
    )
    return result


def query(data_code: str, client: ApiClient | None = None) -> dict:
    """凭数据码查进度（公开接口，脱敏返回）。"""

    code = (data_code or "").strip().upper()
    if not code:
        raise ApiError("请填写数据码", kind="client")
    client = client or ApiClient()
    result = client.post_json("%s?dataCode=%s" % (QUERY_PATH, code), {})
    return result if isinstance(result, dict) else {}


def save_log_copy(report: Report, app_dir: Path | str, bug_no: str) -> Path:
    """把完整内容（未截断的日志）另存一份，方便用户自己补发。"""

    folder = Path(app_dir) / "logs" / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target = folder / ("%s_%s.txt" % (stamp, bug_no or "未编号"))
    body = "\n\n".join(
        [
            "标题：%s" % report.title,
            "类型：%s　严重程度：%s" % (report.type, report.severity),
            "正文：\n%s" % report.description,
            "诊断：\n%s" % report.diagnostics,
            "日志尾部：\n%s" % report.log_tail,
        ]
    )
    target.write_text(body + "\n", encoding="utf-8")
    return target


# ---- 本地留痕 -----------------------------------------------------------

@dataclass
class ReportStore:
    """`config/reports.json`：记下发出去的编号与数据码，能回头查进度。

    每条除了提交信息，还保存**服务端的最新状态与回复**，以及本机的"看过没有"：
    启动时只自动查**没看过**的条目；用户查看过就写 `seenAt`，之后不再自动查
    （省请求，也不烦人）——想再看就手动点「查看详情」，那永远是真查。
    """

    path: Path
    items: list[dict] = field(default_factory=list)

    @staticmethod
    def load(app_dir: Path | str) -> "ReportStore":
        path = Path(app_dir) / "config" / "reports.json"
        if not path.is_file():
            return ReportStore(path=path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ReportStore(path=path)
        items = data if isinstance(data, list) else data.get("items", [])
        return ReportStore(path=path, items=list(items or []))

    def add(self, entry: dict) -> None:
        self.items.insert(0, entry)
        self.items = self.items[:50]
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.items, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def latest(self) -> dict | None:
        return self.items[0] if self.items else None

    # ---- 状态追踪 ----

    def by_code(self, data_code: str) -> dict | None:
        for entry in self.items:
            if entry.get("dataCode") == data_code:
                return entry
        return None

    def unresolved(self) -> list[dict]:
        """还没看过的条目（启动时自动查这些）。"""
        return [e for e in self.items if e.get("dataCode") and not e.get("seenAt")]

    def solved_unread(self) -> list[dict]:
        """已经有结论、但用户还没看过的（要弹一次提示）。"""
        return [
            entry
            for entry in self.unresolved()
            if entry.get("status") in ("resolved", "rejected")
        ]

    def mark_checked(self, entry: dict, payload: dict) -> dict:
        """把服务端查回来的状态/回复写进本地记录。"""
        if not isinstance(payload, dict):
            return entry
        for key in (
            "status", "statusName", "opinion", "resolution",
            "opinionI18n", "resolutionI18n", "locale", "localeName",
        ):
            if payload.get(key) is not None:
                entry[key] = payload[key]
        entry["lastCheckedAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()
        return entry

    def mark_seen(self, entry: dict) -> None:
        """标记为已读：之后不再自动查这条。"""
        entry["seenAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()

    def remove(self, data_code: str) -> None:
        self.items = [e for e in self.items if e.get("dataCode") != data_code]
        self.save()


def refresh(store: ReportStore, client: ApiClient | None = None) -> list[dict]:
    """启动/手动：把"没看过"的条目查一遍，返回**新变成有结论**的那些。

    单条查失败（网络、服务器问题）只跳过它——不能让一条查不到就中断其余的。
    """
    client = client or ApiClient()
    solved: list[dict] = []
    for entry in store.unresolved():
        code = entry.get("dataCode")
        if not code:
            continue
        before = entry.get("status")
        try:
            payload = query(code, client)
        except ApiError as error:
            logger().info("查反馈状态失败（%s）：%s", code, error)
            continue
        store.mark_checked(entry, payload)
        if entry.get("status") in ("resolved", "rejected") and before != entry.get("status"):
            solved.append(entry)
    return solved


def reply_for(entry: dict, field_name: str) -> tuple[str, str | None]:
    """取一条回复：优先**用户语言的译文**，同时给出中文原文（供对照）。

    返回 `(要显示的文字, 中文原文或 None)`；没有译文时第二项是 None，
    调用方据此标注"本条回复只有中文"——不假装有翻译。
    """
    translated = (entry.get(field_name + "I18n") or "").strip()
    original = (entry.get(field_name) or "").strip()
    if translated:
        return translated, (original or None)
    return original, None
