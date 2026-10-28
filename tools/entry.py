#!/usr/bin/env python3
"""生成或刷新插件库的一个条目 plugins/<id>.json。

用法：
  python tools/entry.py <包的网址>              下载、检查，写 plugins/<id>.json（已有就刷新）
  python tools/entry.py <包的网址> --print      只打印条目，不写文件（作者仓库的发布工作流用）

包的网址是 GitHub Release 上的附件：https://github.com/作者/仓库/releases/download/标签/<id>-<X.Y.Z>.wsplugin。
工具会下载它（最多 64 MB），在内存里检查压缩包（不许 ..、绝对路径、符号链接），解到系统的临时文件夹，
跑一遍 check.py 的检查，确认 plugin.json 的 id、version 和文件名上的一样，再算 sha256 和大小。
不运行插件里的任何东西。

已有的条目：id、repo、autoUpdate、bundled、hosted、dateAdded 照旧，别的都照包重新生成。
设了 GH_TOKEN 就用它调 GitHub 接口。只用标准库，Python 3.10+。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I 不会自己加脚本所在的文件夹
import check  # noqa: E402
import registry  # noqa: E402


def make_entry(asset: check.Asset, old: dict | None, args: argparse.Namespace) -> dict:
    """作者和维护者的字段：命令行给了就用，不然照旧条目，再不然用默认；其余的是包里生成的。"""
    old = old or {}

    def kept(key: str, given, default):
        return given if given is not None else old.get(key, default)

    return registry.ordered({
        "id": asset.parts.id,
        "repo": old.get("repo") or asset.parts.repo,
        "autoUpdate": kept("autoUpdate", args.auto_update, True),
        "bundled": kept("bundled", args.bundled, False),
        "hosted": kept("hosted", args.hosted, False),
        **asset.fields,
        "dateAdded": args.date_added or old.get("dateAdded") or registry.now(),
    })


def main() -> int:
    ap = argparse.ArgumentParser(description="生成或刷新插件库的一个条目 plugins/<id>.json")
    ap.add_argument("url", help="Release 上的包：https://github.com/作者/仓库/releases/download/标签/<id>-1.2.3.wsplugin")
    ap.add_argument("--print", action="store_true", help="只打印条目，不写文件")
    ap.add_argument("--auto-update", action=argparse.BooleanOptionalAction, default=None,
                    help="以后发的新版本自动跟上（新条目默认开；不想要就 --no-auto-update）")
    ap.add_argument("--root", default=str(registry.ROOT), help="插件库仓库，默认是工具所在的这个")
    maintainer = ap.add_argument_group("只有维护者用")
    maintainer.add_argument("--bundled", action=argparse.BooleanOptionalAction, default=None, help="随 Win顺 自带")
    maintainer.add_argument("--hosted", action=argparse.BooleanOptionalAction, default=None,
                            help="在本仓库的 legacy/ 里打包发布")
    maintainer.add_argument("--date-added", metavar="TIME", help="第一次收录的时间，如 2026-10-23T09:12:34Z（迁移老条目用）")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parts = registry.asset_url(args.url)
    if parts is None:
        print("错误：网址要像 https://github.com/作者/仓库/releases/download/标签/<id>-1.2.3.wsplugin", file=sys.stderr)
        return 1
    if args.date_added and registry.parse_time(args.date_added) is None:
        print("错误：--date-added 要像 2026-10-23T09:12:34Z 这样（UTC）", file=sys.stderr)
        return 1
    root = Path(args.root).resolve()
    path = registry.entry_path(root, parts.id)
    old = None
    if path.is_file():
        try:
            old = registry.load_json(path)
        except (ValueError, UnicodeDecodeError) as ex:
            print(f"错误：{path} 读不出来：{ex}", file=sys.stderr)
            return 1
        old = old if isinstance(old, dict) else None
    if old and isinstance(old.get("repo"), str) and old["repo"].lower() != parts.repo.lower():
        print(f"错误：plugins/{parts.id}.json 的 repo 是 {old['repo']}，这个包却在 {parts.repo}。"
              "换仓库要先和维护者说好（开个 Issue）", file=sys.stderr)
        return 1

    asset = check.check_asset(args.url, expected_id=parts.id)
    for text in asset.warnings:
        print("警告：" + text, file=sys.stderr)
    for text in asset.errors:
        print("错误：" + text, file=sys.stderr)
    if asset.errors:
        print("检查没过，没有写条目", file=sys.stderr)
        return 1
    entry = make_entry(asset, old, args)
    report = check.Report(parts.id)
    check.check_entry_fields(report, entry, root)
    for text in report.errors:
        print("错误：" + text, file=sys.stderr)
    if report.errors:
        return 1

    if args.print:
        sys.stdout.write(registry.dumps(entry))
        return 0
    changed = old is None or registry.dumps(old) != registry.dumps(entry)
    registry.write_json(path, entry)
    print(f"{'写了' if changed else '没有变化：'} plugins/{parts.id}.json（{parts.id} {entry['version']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
