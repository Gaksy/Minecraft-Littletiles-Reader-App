"""命令行入口：``python -m ltgen <子命令>``。

只放生成端新增/编排的东西；原有的具体解析脚本仍在 tools/ 下，按原方式调用。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import FORMAT_VERSION, __version__
from .console import enable_utf8_output
from .contract import ContractError
from .lint import lint_package
from .manifest import Pack, build_manifest, describe, write_package_manifest
from . import paths
from .tint import DEFAULT_FOLIAGE_ARGB, DEFAULT_GRASS_ARGB, write_tint_table


def _parse_argb(text: str) -> int:
    """接受 ``0xFF91BD59`` / ``FF91BD59`` / ``#91BD59``（后者补上不透明 alpha）。"""
    value = text.strip().lstrip("#")
    if value.startswith(("0x", "0X")):
        value = value[2:]
    try:
        number = int(value, 16)
    except ValueError as error:
        raise argparse.ArgumentTypeError("不是合法的十六进制颜色：%r" % text) from error
    return number if len(value) > 6 else number | 0xFF000000


def cmd_manifest(args: argparse.Namespace) -> int:
    packs = [Pack.parse(spec) for spec in args.pack]
    manifest = build_manifest(
        layers=args.layer,
        packs=packs,
        note=args.note or "",
        texture_layout=args.texture_layout,
    )
    path = write_package_manifest(args.dir, manifest, merge_existing=not args.no_merge)
    print("已写入 %s" % path)
    print(describe(args.dir))
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    reports = [lint_package(path) for path in args.dir]
    for report in reports:
        print(report.render())
        print()
    failed = [report for report in reports if not report.ok]
    print("== %d/%d 个素材包通过 ==" % (len(reports) - len(failed), len(reports)))
    return 1 if failed else 0


def cmd_tint(args: argparse.Namespace) -> int:
    for package_dir in args.dir:
        path, rules = write_tint_table(
            package_dir, grass_argb=args.grass, foliage_argb=args.foliage
        )
        print("已写入 %s（%d 条规则）" % (path, len(rules)))
        for rule in rules:
            print("  %s" % rule.as_line())
    return 0


def cmd_paths(args: argparse.Namespace) -> int:
    print(paths.describe())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ltgen",
        description="LittleTiles Reader 生成端：素材包契约工具（版本 %s）" % __version__,
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    lint_parser = subparsers.add_parser("lint", help="校验素材包（库能不能吃、缺什么）")
    lint_parser.add_argument("dir", type=Path, nargs="+", help="素材包目录")
    lint_parser.set_defaults(func=cmd_lint)

    paths_parser = subparsers.add_parser("paths", help="打印解析到的数据根 / 库路径")
    paths_parser.set_defaults(func=cmd_paths)

    manifest_parser = subparsers.add_parser("manifest", help="生成 manifest.json")
    manifest_parser.add_argument("dir", type=Path, help="素材包目录")
    manifest_parser.add_argument(
        "--layer", action="append", default=[], help="叠加层，按优先级从低到高，可重复"
    )
    manifest_parser.add_argument(
        "--pack",
        action="append",
        default=[],
        metavar="ID[@版本][:命名空间,命名空间]",
        help="素材来源，可重复，例如 vanilla@1.12.2:minecraft",
    )
    manifest_parser.add_argument("--note", help="补充说明（写进 manifest 的 note 字段）")
    manifest_parser.add_argument(
        "--texture-layout",
        default="<相对路径>.png",
        help="纹理引用布局的说明性字段（库不强制解析它）",
    )
    manifest_parser.add_argument(
        "--no-merge", action="store_true", help="不保留已有 manifest 里的额外字段"
    )
    manifest_parser.set_defaults(func=cmd_manifest)

    tint_parser = subparsers.add_parser("tint", help="生成 tint.tsv（默认色规则）")
    tint_parser.add_argument("dir", type=Path, nargs="+", help="素材包目录")
    tint_parser.add_argument(
        "--grass", type=_parse_argb, default=DEFAULT_GRASS_ARGB,
        help="草色，默认 0xFF91BD59（与库内默认一致）",
    )
    tint_parser.add_argument(
        "--foliage", type=_parse_argb, default=DEFAULT_FOLIAGE_ARGB,
        help="树叶色，默认 0xFF79C05A（与库内默认一致）",
    )
    tint_parser.set_defaults(func=cmd_tint)

    return parser


def main(argv: list[str] | None = None) -> int:
    enable_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ContractError as error:
        print("错误：%s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
