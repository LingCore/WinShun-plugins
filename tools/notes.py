#!/usr/bin/env python3
"""只刷新条目里的 notes（Win顺 插件库里的“更新内容”），不下载包、不动别的字段。

用法：
  python tools/notes.py                  全部条目
  python tools/notes.py ID [ID ...]      只刷新这几个
  python tools/notes.py --dry-run        只看哪些会变，不写文件

notes 是条目 url 指向的那个 Release 的说明（正文），拆成中文、英文各一份（拆法见 registry.split_notes）。
Release 没有说明的，条目里就没有 notes（原来有的会去掉）。问不到 GitHub 的（网络出错、找不到 Release），
条目保持原样，打印警告，退出码是 1，再跑一遍就行。
作者不用手写 notes：entry.py 和自动更新（update.py）生成条目时会带上；这个工具用来补老条目，
或者作者改了 Release 的说明以后重新生成（check.py --online 会提醒“notes 和 Release 现在的说明不一样”）。
设了 GH_TOKEN 或 GITHUB_TOKEN 就用它调 GitHub 接口。只用标准库，Python 3.10+。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I 不会自己加脚本所在的文件夹
import registry  # noqa: E402

TRIES = 3  # 偶尔有一次问不到的，隔一会儿再问


def release_of(repo: str, tag: str) -> dict | None:
    for attempt in range(TRIES):
        try:
            return registry.release_by_tag(repo, tag)
        except registry.FetchError:
            if attempt == TRIES - 1:
                raise
            time.sleep(1 + attempt)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="只刷新条目里的 notes（Release 的说明）")
    ap.add_argument("ids", nargs="*", metavar="ID", help="只刷新这些插件，不写就是全部")
    ap.add_argument("--dry-run", action="store_true", help="只看哪些会变，不写文件")
    ap.add_argument("--root", default=str(registry.ROOT), help="插件库仓库，默认是工具所在的这个")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    wanted = set(args.ids)
    paths = sorted((root / "plugins").glob("*.json"))
    unknown = wanted - {p.stem for p in paths}
    for pid in sorted(unknown):
        print(f"错误：没有条目 plugins/{pid}.json", file=sys.stderr)
    failed = len(unknown)
    changed = 0
    for path in paths:
        if wanted and path.stem not in wanted:
            continue
        try:
            entry = registry.load_json(path)
        except (ValueError, UnicodeDecodeError) as ex:
            print(f"警告：{path.name} 读不出来：{ex}", file=sys.stderr)
            failed += 1
            continue
        parts = registry.asset_url(entry.get("url")) if isinstance(entry, dict) else None
        if parts is None:
            print(f"警告：{path.name} 的 url 不是 Release 上的包，跳过", file=sys.stderr)
            failed += 1
            continue
        try:
            release = release_of(parts.repo, parts.tag)
        except registry.FetchError as ex:
            print(f"警告：{path.stem} 问不到 {parts.repo} 的 Release：{ex}，notes 保持原样", file=sys.stderr)
            failed += 1
            continue
        if release is None:
            print(f"警告：{path.stem} 在 {parts.repo} 里找不到标签 {parts.tag} 的 Release，notes 保持原样", file=sys.stderr)
            failed += 1
            continue
        notes = registry.notes_of(release)
        new = registry.ordered({**{k: v for k, v in entry.items() if k != "notes"}, **({"notes": notes} if notes else {})})
        if registry.dumps(new) == registry.dumps(entry):
            print(f"没有变化：{path.stem}（{'有' if notes else '没有'} notes）")
            continue
        changed += 1
        if not args.dry_run:
            registry.write_json(path, new)
        detail = f"notes 中文 {len(notes['zh'])} 字、英文 {len(notes['en'])} 字" if notes else "去掉 notes"
        print(f"{'会改' if args.dry_run else '写了'}：{path.stem}（{detail}）")
    print(f"{changed} 个条目的 notes {'会变' if args.dry_run else '变了'}，{failed} 个没弄成")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
