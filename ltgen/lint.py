"""校验一个素材包：库能不能吃、吃了会缺什么。

为什么要在生成端做这件事：库侧的 lint 只回一个"能/不能打开 + 缺几张",
而生成端此刻还知道**是哪个包、哪一步**导致的，能给出可修的问题列表。
库侧对应实现见 `AssetsPackage::Open`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import FORMAT_VERSION
from .contract import (
    MANIFEST_NAME,
    TABLE_NAME,
    TEXTURES_DIR,
    TINT_NAME,
    ContractError,
    check_format_version,
    load_manifest,
    parse_texture_table,
    resolve_texture,
)

# 报告里最多列几个例子，避免刷屏
MAX_EXAMPLES = 10


@dataclass
class PackageReport:
    """一次校验的结论。`errors` 非空表示库会拒绝或明显残缺。"""

    package_dir: Path
    exists: bool = False
    has_manifest: bool = False
    format_version: int | None = None
    layers: list[str] = field(default_factory=list)
    packs: list[str] = field(default_factory=list)
    block_count: int = 0
    texture_ref_count: int = 0
    texture_file_count: int = 0
    missing_textures: list[str] = field(default_factory=list)
    unreferenced_textures: list[str] = field(default_factory=list)
    tint_rule_count: int = 0
    has_tint_table: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        """给 CLI 打印的多行报告。"""
        lines = []
        state = "OK" if self.ok else "FAILED"
        lines.append("素材包 %s  [%s]" % (self.package_dir, state))
        lines.append(
            "  manifest  : %s"
            % ("有，format_version=%s" % self.format_version if self.has_manifest else "无（可选）")
        )
        if self.layers:
            lines.append("  layers    : %s" % " -> ".join(self.layers))
        if self.packs:
            lines.append("  packs     : %s" % ", ".join(self.packs))
        lines.append("  方块      : %d" % self.block_count)
        lines.append(
            "  贴图      : 引用 %d 张 / 目录里 %d 张 / 缺失 %d 张"
            % (self.texture_ref_count, self.texture_file_count, len(self.missing_textures))
        )
        lines.append(
            "  tint      : %s"
            % ("tint.tsv %d 条规则" % self.tint_rule_count if self.has_tint_table else "无（用库内默认色）")
        )
        for error in self.errors:
            lines.append("  ✗ %s" % error)
        for warning in self.warnings:
            lines.append("  ⚠ %s" % warning)
        return "\n".join(lines)


def _count_tint_rules(path: Path) -> int:
    """数 tint.tsv 里的有效规则行（与库的 LoadTintTable 解析方式一致）。"""
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if len(line.split()) >= 3:
                count += 1
    return count


def lint_package(package_dir: Path, max_examples: int = MAX_EXAMPLES) -> PackageReport:
    """校验一个素材包目录，返回可打印的报告。"""
    package_dir = Path(package_dir)
    report = PackageReport(package_dir=package_dir)

    if not package_dir.is_dir():
        report.errors.append("目录不存在：%s" % package_dir)
        return report
    report.exists = True

    # manifest.json（可选）
    try:
        manifest = load_manifest(package_dir)
    except ContractError as error:
        report.errors.append(str(error))
        manifest = {}
    if manifest:
        report.has_manifest = True
        report.format_version = manifest.get("format_version")
        report.layers = list(manifest.get("layers") or [])
        report.packs = [
            str(pack.get("id", "?")) if isinstance(pack, dict) else str(pack)
            for pack in (manifest.get("packs") or [])
        ]
        report.errors.extend(check_format_version(report.format_version, FORMAT_VERSION))
        if report.format_version is None:
            report.warnings.append(
                "%s 里没有 format_version；库会按 1 处理" % MANIFEST_NAME
            )

    # 映射表（必需）
    try:
        table = parse_texture_table(package_dir / TABLE_NAME)
    except ContractError as error:
        report.errors.append(str(error))
        return report

    report.block_count = len(table.entries)
    if not table.entries:
        report.errors.append("%s 里没有任何方块条目" % TABLE_NAME)
    for line_no, reason in table.malformed[:max_examples]:
        report.errors.append("%s 第 %d 行被跳过：%s" % (TABLE_NAME, line_no, reason))
    if len(table.malformed) > max_examples:
        report.errors.append(
            "……另有 %d 行同样被跳过（库会静默忽略这些行）"
            % (len(table.malformed) - max_examples)
        )
    if table.duplicates:
        report.warnings.append(
            "有 %d 个重复的方块键（后者覆盖前者），例如 %s"
            % (len(table.duplicates), ", ".join(table.duplicates[:max_examples]))
        )

    # 贴图（必需）
    referenced = table.texture_paths()
    report.texture_ref_count = len(referenced)
    textures_dir = package_dir / TEXTURES_DIR
    if not textures_dir.is_dir():
        report.errors.append("缺少贴图目录：%s" % textures_dir)

    on_disk: set[str] = set()
    if textures_dir.is_dir():
        for path in textures_dir.rglob("*.png"):
            on_disk.add(path.relative_to(textures_dir).with_suffix("").as_posix())
        report.texture_file_count = len(on_disk)

    for rel in referenced:
        if rel not in on_disk and not resolve_texture(package_dir, rel).is_file():
            if len(report.missing_textures) < max_examples:
                report.missing_textures.append(rel)
            elif len(report.missing_textures) == max_examples:
                report.missing_textures.append("……")
    if report.missing_textures:
        report.errors.append(
            "%d 张被引用的贴图在 %s/ 下找不到（前几个：%s）"
            % (
                len([m for m in report.missing_textures if m != "……"]),
                TEXTURES_DIR,
                ", ".join(report.missing_textures),
            )
        )

    unused = sorted(on_disk - set(referenced))
    if unused:
        report.unreferenced_textures = unused[:max_examples]
        report.warnings.append(
            "%d 张贴图在目录里但没被映射表引用（前几个：%s）"
            % (len(unused), ", ".join(unused[:max_examples]))
        )

    # tint 表（可选）
    tint_path = package_dir / TINT_NAME
    if tint_path.is_file():
        report.has_tint_table = True
        report.tint_rule_count = _count_tint_rules(tint_path)
        if report.tint_rule_count == 0:
            report.warnings.append("%s 存在但没有有效规则" % TINT_NAME)
    elif table.tint_pairs():
        report.warnings.append(
            "映射表里有 %d 处 tintindex，但没有 %s；库会用内置默认色"
            "（草 0xFF91BD59 / 树叶 0xFF79C05A）"
            % (len(table.tint_pairs()), TINT_NAME)
        )

    # 数字 ID 表：纹理不需要它，但**导出存档的普通方块需要**
    # （存档里存的是数字 ID，库靠它反查方块名）。缺了不会报错，只会默默
    # 不导出普通方块 —— 所以必须在这里说出来。
    if not (package_dir / "block_ids.tsv").is_file():
        report.warnings.append(
            "缺 block_ids.tsv：贴图导出不受影响，但**导出存档时不会包含普通方块**"
            "（这个文件由 tools/generate_block_id_table.py 生成）"
        )

    return report
