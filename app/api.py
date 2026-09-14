"""极简 HTTP 客户端：只做"发一个 JSON、收一个 JSON"，够用就好。

为什么不用 requests / httpx：这个应用的原则是**除 PySide6 外不引第三方依赖**
（生成端只用标准库，打包体积也是目标之一）。标准库的 `urllib.request` 足够，
而且超时、UA、错误分类都能自己控制。

服务器（inception-work）的统一响应是 `AjaxResult`：

```json
{"success": true,  "payload": {...}}
{"success": false, "error_type": "FEEDBACK", "error_code": "...", "error_message": "..."}
```

`ApiError` 把"网络不通"和"服务器拒绝了"分开：前者重试没意义，后者要看
`error_message` 告诉用户哪里不对（比如描述超长）。诊断信息里只放 `error_code`，
不放服务器原始堆栈。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import __version__
from .applog import logger

DEFAULT_BASE = "https://www.inception.work/api"
CONNECT_TIMEOUT = 3          # 连不上就别让用户等
READ_TIMEOUT = 8


class ApiError(RuntimeError):
    """一次调用没能拿到 payload。`kind` 区分网络问题与服务器拒绝。"""

    def __init__(self, message: str, *, kind: str = "network", code: str = "") -> None:
        super().__init__(message)
        self.kind = kind          # network / server / bad_response
        self.code = code


@dataclass(frozen=True)
class ApiClient:
    """一个 base URL + 超时的薄封装；`opener` 只为测试留的缝。"""

    base: str = DEFAULT_BASE
    timeout: int = READ_TIMEOUT
    opener: object | None = None        # 测试注入：callable(Request) -> bytes

    # ---- 对外 ----

    def get_json(self, path: str) -> object:
        return self._call("GET", path, None)

    def post_json(self, path: str, payload: dict | None = None) -> object:
        return self._call("POST", path, payload if payload is not None else {})

    # ---- 内部 ----

    def _url(self, path: str) -> str:
        base = (self.base or DEFAULT_BASE).rstrip("/")
        return base + (path if path.startswith("/") else "/" + path)

    def _call(self, method: str, path: str, payload: dict | None) -> object:
        url = self._url(path)
        body = None
        headers = {
            "Accept": "application/json",
            # 带上应用版本：服务器日志里能看出是哪个客户端的请求
            "User-Agent": "LittleTilesReader/%s (+desktop)" % __version__,
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            raw = self._send(request)
        except urllib.error.HTTPError as error:
            # 4xx/5xx 里也带 AjaxResult（例如字段超长），尽量按服务器的话说
            detail = self._decode(error.read()) if hasattr(error, "read") else None
            message = self._error_message(detail) or ("HTTP %s" % error.code)
            raise ApiError(message, kind="server", code=str(error.code)) from error
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            raise ApiError(str(error), kind="network") from error

        data = self._decode(raw)
        if isinstance(data, dict) and data.get("success") is False:
            raise ApiError(
                self._error_message(data) or "服务器拒绝了这次请求",
                kind="server",
                code=str(data.get("error_code", "")),
            )
        if isinstance(data, dict) and "payload" in data:
            return data.get("payload")
        return data

    def _send(self, request: urllib.request.Request) -> bytes:
        if self.opener is not None:         # 测试替身：直接给字节
            return self.opener(request)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()

    @staticmethod
    def _decode(raw) -> object:
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            logger().warning("接口返回的不是 JSON：%s", str(raw)[:200])
            return None

    @staticmethod
    def _error_message(data) -> str:
        if isinstance(data, dict):
            return str(data.get("error_message") or data.get("message") or "")
        return ""
