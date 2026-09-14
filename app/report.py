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

import json
import os
import platform
import re
import sys
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

#: 服务器只认 web / server / account / site / other（评估里建议加 app）
DEFAULT_MODULE = "other"
SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
TYPES = ("bug", "suggestion")


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
        "userAgent": "LittleTilesReader/%s (%s)" % (__version__, platform.system()),
    }


def submit(report: Report, client: ApiClient | None = None) -> dict:
    """提交一次反馈，返回服务器的 `{bugId, bugNo, dataCode}`。"""

    client = client or ApiClient()
    attach_log(report)
    payload = build_payload(report)
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
    """`config/reports.json`：记下发出去的编号与数据码，能回头查进度。"""

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
