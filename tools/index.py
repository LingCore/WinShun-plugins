#!/usr/bin/env python3
"""用条目 plugins/<id>.json 生成插件库的 index.json（Win顺 设置 → 插件 → 插件库 读的就是它）和 README 里的插件表。

用法：
  python tools/index.py                     写 dist/index.json
  python tools/index.py --readme            同时改写 README.md 里的插件表
  python tools/index.py --compare OLD.json  再和一份已发布的 index.json 比：OLD 里每个插件的每个字段都要一模一样

index.json 只加字段、不改已有的：旧版 Win顺（0.14、0.15）不认识的字段会忽略，网址也一直是
index 这个 Release 上的 index.json。不打包、不下载任何东西。只用标准库，Python 3.10+。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I 不会自己加脚本所在的文件夹
import check  # noqa: E402
import registry  # noqa: E402
from build import pick  # noqa: E402

README_START = "<!-- plugins:start -->"
README_END = "<!-- plugins:end -->"
MAIN_REPO = "LingCore/WinShun"


def source_of(e: dict) -> str:
    """插件的源码在哪：自带的在 Win顺 主仓库，老插件在本仓库的 legacy/，别的在作者自己的仓库。"""
    if e.get("bundled"):
        return f"https://github.com/{MAIN_REPO}/tree/main/plugins/{e['id']}"
    if e.get("hosted"):
        return f"https://github.com/{registry.REPO}/tree/main/legacy/{e['id']}"
    return f"https://github.com/{e['repo']}"


def item_of(e: dict) -> dict:
    """一个条目 → index.json 里的一项。前 16 个字段的名字、顺序和取法和迁移前的 index.json 一样；新字段加在后面。"""
    return {
        "id": e["id"],
        "name": e["name"],
        "version": e["version"],
        "description": e["description"],
        "author": e["author"],
        "homepage": e["homepage"],
        "license": e["license"],
        "keywords": e["keywords"],
        "permissions": e["permissions"],
        "runtime": e["runtime"],
        "minWinShun": e["minWinShun"],
        "bundled": bool(e.get("bundled", False)),
        "file": registry.asset_url(e["url"]).file,
        "url": e["url"],
        "sha256": e["sha256"],
        "size": e["size"],
        # 迁移到条目以后新加的
        "repo": e["repo"],
        "source": source_of(e),
        "releaseDate": e["releaseDate"],
        "dateAdded": e["dateAdded"],
    }


def build_index(root: Path) -> dict | None:
    """条目有错误就不生成（返回 None），错误已经打印出来。"""
    reports, stray = check.load_entries(root)
    errors = stray + [t for r in reports for t in r.errors]
    for text in errors:
        print("错误：" + text)
    if errors:
        print("条目检查没过，不生成 index.json。先跑 python tools/check.py")
        return None
    entries = sorted((r.entry for r in reports), key=lambda e: e["id"])
    return {"schema": 1, "generated": registry.now(), "plugins": [item_of(e) for e in entries]}


# ---------------------------------------------------------------- README 的插件表

def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def table(items: list[dict]) -> str:
    rows = ["| 名称 | 关键字 | 说明 | 作者 | 权限 | 下载 |", "|---|---|---|---|---|---|"]
    for e in items:
        name = f"[{cell(pick(e['name']))}]({e['source']})" + ("<br>（随 Win顺 自带）" if e["bundled"] else "")
        keywords = " ".join(f"`{cell(k)}`" for k in e["keywords"]) or "—"
        perms = "、".join(f"**{p}**" if p in check.RISKY else p for p in e["permissions"]) or "无"
        link = f"[{e['version']}]({e['url']})"
        rows.append(f"| {name} | {keywords} | {cell(pick(e['description']))} | {cell(e['author'])} | {perms} | {link} |")
    return "\n".join(rows)


def write_readme(root: Path, items: list[dict]) -> bool:
    path = root / "README.md"
    text = path.read_text(encoding="utf-8")
    start, end = text.find(README_START), text.find(README_END)
    if start < 0 or end < start:
        sys.exit(f"README.md 里找不到 {README_START} 和 {README_END}")
    new = text[: start + len(README_START)] + "\n" + table(items) + "\n" + text[end:]
    if new == text:
        return False
    path.write_bytes(new.encode("utf-8"))
    return True


# ---------------------------------------------------------------- 和已发布的比

def dropped_by_app(item: dict, seen: set) -> str:
    """Win顺 的 Gallery.cpp（gallery::parse）会丢掉的项：返回原因；留下的是空的。"""
    pid, url, sha, size = item.get("id"), item.get("url"), item.get("sha256"), item.get("size")
    if not (isinstance(pid, str) and check.valid_plugin_id(pid)):
        return "id 不对"
    if not (isinstance(item.get("version"), str) and item["version"]):
        return "没有 version"
    if not (isinstance(url, str) and url.lower().startswith("https://")):
        return "url 不是 https"
    if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha.lower())):
        return "sha256 不对"
    if not (isinstance(size, (int, float)) and not isinstance(size, bool) and size > 0):
        return "size 不对"
    if pid in seen:
        return "id 重复"
    return ""


def compare(old: dict, new: dict) -> tuple[list[str], list[str]]:
    """(不一样的地方, 说明)。OLD 里每个插件的每个字段都要在 NEW 里一模一样；generated 是生成时间，不比。"""
    problems: list[str] = []
    if new.get("schema") != 1 or old.get("schema") != 1:
        problems.append(f"schema 要是 1（旧的 {old.get('schema')}，新的 {new.get('schema')}）")
    olds, news = old.get("plugins") or [], new.get("plugins") or []
    old_ids, new_ids = [p.get("id") for p in olds], [p.get("id") for p in news]
    if old_ids != new_ids:
        problems.append(f"插件或顺序不一样：旧的 {old_ids}，新的 {new_ids}")
    by_id = {p.get("id"): p for p in news}
    same_fields, added = 0, set()
    for o in olds:
        n = by_id.get(o.get("id"))
        if n is None:
            continue
        for key, value in o.items():
            if key not in n:
                problems.append(f"{o['id']}：少了 {key}")
            elif not registry.same(n[key], value):
                problems.append(f"{o['id']}.{key}：{check.brief(value)} → {check.brief(n[key])}")
            else:
                same_fields += 1
        added |= set(n) - set(o)
    seen: set = set()
    dropped = []
    for item in news:
        why = dropped_by_app(item, seen)
        seen.add(item.get("id"))
        if why:
            dropped.append(f"{item.get('id')}（{why}）")
    if dropped:
        problems.append("Win顺 会丢掉：" + "、".join(dropped))
    notes = [f"{len(olds)} 个插件，{same_fields} 个旧字段一模一样，{len(problems)} 处不一样",
             f"Win顺 会丢掉的：{len(dropped)} 个；新加的字段：{'、'.join(sorted(added)) or '无'}"]
    return problems, notes


def main() -> int:
    ap = argparse.ArgumentParser(description="用条目生成 index.json 和 README 的插件表")
    ap.add_argument("--out", default="dist", help="输出文件夹，默认 dist/")
    ap.add_argument("--readme", action="store_true", help="同时改写 README.md 里的插件表")
    ap.add_argument("--compare", metavar="OLD", help="和这份已发布的 index.json 比，不一样就退出码 1")
    ap.add_argument("--root", default=str(registry.ROOT), help="插件库仓库，默认是工具所在的这个")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    index = build_index(root)
    if index is None:
        return 1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.json").write_bytes(registry.dumps(index).encode("utf-8"))
    print(f"写了 {out / 'index.json'}（{len(index['plugins'])} 个插件）")
    if args.readme:
        print("README 表已更新" if write_readme(root, index["plugins"]) else "README 表没有变化")
    if args.compare:
        old = json.loads(Path(args.compare).read_text(encoding="utf-8-sig"))
        problems, notes = compare(old, index)
        for text in problems:
            print("不一样：" + text)
        for text in notes:
            print(f"和 {args.compare} 比：{text}")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
