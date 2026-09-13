"""保留策略：哪些旧导出可以清掉（设计文档 §7.7）。

三种规则，任意组合；**默认一条都不开**——程序不该自作主张删用户的东西。

* 只保留最近 N 次：多出来的从最旧的开始删
* 超过 X 天：`created_at` 早于这个天数的删
* 总大小超过 Y MB：从最旧的开始腾，直到降到阈值以下

"删"指的是删**产物目录与记录**；贴图库靠"没人引用就回收"单独处理
（见 `texture_library.py`），记录索引与 SNBT 输入副本永不自动删——它们很小，
是追溯与重建的依据。

这层不碰 Qt，能单独测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .storage import human_size

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass
class RetentionPlan:
    victims: list[str] = field(default_factory=list)   # 记录 id，最旧的在前
    freed: int = 0                                     # 预计释放的字节
    reasons: list[str] = field(default_factory=list)   # 给用户看的理由

    @property
    def is_empty(self) -> bool:
        return not self.victims

    def render(self) -> str:
        if self.is_empty:
            return "没有需要清理的旧导出。"
        return "将清理 %d 次旧导出，释放约 %s：\n%s" % (
            len(self.victims),
            human_size(self.freed),
            "\n".join("· " + reason for reason in self.reasons),
        )


def policy_active(keep: int = 0, max_days: int = 0, max_size_mb: int = 0) -> bool:
    return keep > 0 or max_days > 0 or max_size_mb > 0


def plan(
    records,
    *,
    keep: int = 0,
    max_days: int = 0,
    max_size_mb: int = 0,
    sizes: dict | None = None,
    now: datetime | None = None,
) -> RetentionPlan:
    """按策略算出该清哪些。`records` 是记录列表，`sizes` 是 id → 字节。"""
    result = RetentionPlan()
    if not policy_active(keep, max_days, max_size_mb):
        return result
    sizes = sizes or {}
    now = now or datetime.now()
    ordered = sorted(records, key=lambda r: r.created_at, reverse=True)   # 新 → 旧

    victims: dict[str, None] = {}       # 用 dict 去重，同时保持顺序

    if keep > 0 and len(ordered) > keep:
        extra = ordered[keep:]
        result.reasons.append("只保留最近 %d 次，多出 %d 次" % (keep, len(extra)))
        for record in extra:
            victims.setdefault(record.id, None)

    if max_days > 0:
        deadline = now - timedelta(days=max_days)
        old = [
            record
            for record in ordered
            if _parse(record.created_at) and _parse(record.created_at) < deadline
        ]
        if old:
            result.reasons.append("早于 %d 天的 %d 次" % (max_days, len(old)))
        for record in old:
            victims.setdefault(record.id, None)

    if max_size_mb > 0:
        limit = max_size_mb * 1024 * 1024
        total = sum(sizes.get(record.id, 0) for record in ordered)
        if total > limit:
            extra = []
            for record in reversed(ordered):        # 最旧的先腾
                if total <= limit:
                    break
                extra.append(record)
                total -= sizes.get(record.id, 0)
            result.reasons.append(
                "总大小超过 %d MB，需要腾出 %s"
                % (
                    max_size_mb,
                    human_size(sum(sizes.get(r.id, 0) for r in extra)),
                )
            )
            for record in extra:
                victims.setdefault(record.id, None)

    # 最旧的先删：列表里是新的在前，删的时候反着来更符合直觉
    order = {record.id: index for index, record in enumerate(reversed(ordered))}
    result.victims = sorted(victims, key=lambda rid: order.get(rid, 0))
    result.freed = sum(sizes.get(rid, 0) for rid in result.victims)
    return result


def _parse(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, TIME_FORMAT)
    except (TypeError, ValueError):
        return None
