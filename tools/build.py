#!/usr/bin/env python3
"""打包：每个插件一个 dist/<id>-<version>.wsplugin，再生成 dist/index.json；--readme 改写 README 里的插件表。

同样的文件一定打出同样的包（文件按名字排序、时间固定、不压缩），所以 sha256 可以拿来比对。
只用标准库，Python 3.10+。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import check

ROOT = check.ROOT
DIST = ROOT / "dist"
REPO = "LingCore/WinShun-plugins"
BUNDLED = {"winshun.go", "winshun.web", "winshun.bookmarks", "winshun.kill", "winshun.translate"}  # 也随 Win顺 安装
README_START = "<!-- plugins:start -->"
README_END = "<!-- plugins:end -->"
FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def pick(text, locale: str = "zh") -> str:
    if isinstance(text, str):
        return text
    if isinstance(text, dict):
        order = ("zh", "en") if locale == "zh" else ("en", "zh")
        for key in order:
            if isinstance(text.get(key), str) and text[key]:
                return text[key]
    return ""


def pack(folder: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    files = sorted((p for p in folder.rglob("*") if p.is_file()), key=lambda p: p.relative_to(folder).as_posix())
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as z:
        for p in files:
            info = zipfile.ZipInfo(p.relative_to(folder).as_posix(), FIXED_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            z.writestr(info, p.read_bytes())


def entry(r: check.Result, archive: Path) -> dict:
    m = r.manifest
    pid, version = m["id"], m["version"]
    runtime = m.get("runtime")
    names, _ = check.permissions_of(m)
    name = f"{pid}-{version}.wsplugin"
    data = archive.read_bytes()
    return {
        "id": pid,
        "name": m["name"],
        "version": version,
        "description": m.get("description", ""),
        "author": m.get("author", ""),
        "homepage": m.get("homepage", ""),
        "license": m.get("license", ""),
        "keywords": check.keywords_of(m),
        "permissions": names,
        "runtime": {"mode": runtime["mode"], "program": runtime["program"]} if isinstance(runtime, dict)
                   else {"mode": "zero-code", "program": None},
        "minWinShun": m.get("minWinShun", ""),
        "bundled": pid in BUNDLED,
        "file": name,
        "url": f"https://github.com/{REPO}/releases/download/{pid}-v{version}/{name}",
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def table(entries: list[dict]) -> str:
    rows = ["| 名称 | 关键字 | 说明 | 作者 | 权限 | 下载 |", "|---|---|---|---|---|---|"]
    for e in entries:
        name = cell(pick(e["name"]))
        name = f"[{name}](plugins/{e['id']})" + ("<br>（随 Win顺 自带）" if e["bundled"] else "")
        keywords = " ".join(f"`{cell(k)}`" for k in e["keywords"]) or "—"
        perms = "、".join(f"**{p}**" if p in check.RISKY else p for p in e["permissions"]) or "无"
        link = f"[{e['version']}]({e['url']})"
        rows.append(f"| {name} | {keywords} | {cell(pick(e['description']))} | {cell(e['author'])} | {perms} | {link} |")
    return "\n".join(rows)


def write_readme(entries: list[dict]) -> bool:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    start, end = text.find(README_START), text.find(README_END)
    if start < 0 or end < start:
        sys.exit(f"README.md 里找不到 {README_START} 和 {README_END}")
    new = text[: start + len(README_START)] + "\n" + table(entries) + "\n" + text[end:]
    if new == text:
        return False
    path.write_bytes(new.encode("utf-8"))
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="打包插件并生成 index.json")
    ap.add_argument("--readme", action="store_true", help="同时改写 README.md 里的插件表")
    ap.add_argument("--out", default=str(DIST), help="输出文件夹，默认 dist/")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    results, _ = check.check_all()
    bad = [r for r in results if r.errors]
    if bad:
        for r in bad:
            for t in r.errors:
                print("错误：" + t)
        print("检查没过，不打包。先跑 python tools/check.py")
        return 1

    out = Path(args.out)
    entries = []
    for r in results:
        m = r.manifest
        archive = out / f"{m['id']}-{m['version']}.wsplugin"
        pack(r.folder, archive)
        entries.append(entry(r, archive))
        print(f"打包 {archive.name}（{archive.stat().st_size} 字节）")
    entries.sort(key=lambda e: e["id"])
    index = {
        "schema": 1,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plugins": entries,
    }
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"写了 {out / 'index.json'}（{len(entries)} 个插件）")
    if args.readme:
        print("README 表已更新" if write_readme(entries) else "README 表没有变化")
    return 0


if __name__ == "__main__":
    sys.exit(main())
