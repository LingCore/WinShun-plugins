#!/usr/bin/env python3
"""把每个插件包里的 README.md 取出来，供 Win顺 的插件库在安装前显示（“说明”）。

用法：
  python tools/readmes.py --out dist/readmes                    每个条目的包下载一遍，取出 README
  python tools/readmes.py --have LIVE --out dist/readmes        LIVE 里已经有的（上次发布的）直接用，不再下载

写出的文件叫 readme-<id>-<version>.md：一个版本的包不会变，所以它的 README 也不会变，
名字里带版本，新版本发布时旧索引指着的那份还在，直到被换掉。index.py --readmes 把它的网址和
sha256 写进 index.json（Win顺 下载后核对）。

取不到的（下载失败、包里没有 README.md、超过 1 MB、是空的）只警告、跳过：那个插件在索引里就没有
readme 字段，Win顺 不显示“说明”，别的不受影响。包的 sha256 和条目对不上也跳过。
不运行包里的任何东西。只用标准库，Python 3.10+。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I 不会自己加脚本所在的文件夹
import check  # noqa: E402
import registry  # noqa: E402

MAX_README = 1024 * 1024  # Win顺 的说明窗口最多读这么多


def file_name(plugin_id: str, version: str) -> str:
    return f"readme-{plugin_id}-{version}.md"


def readme_of(package: bytes) -> bytes | None:
    """包最外层的 README.md（不分大小写）；没有、太大、是空的都是 None。"""
    try:
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            for info in archive.infolist():
                if info.is_dir() or info.filename.lower() != "readme.md":
                    continue
                if info.file_size > MAX_README:
                    return None
                with archive.open(info) as member:
                    data = member.read(MAX_README + 1)
                if len(data) > MAX_README or not data.decode("utf-8-sig", errors="replace").strip():
                    return None
                return data
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError):
        return None
    return None


def collect(root: Path, have: Path | None, out: Path) -> tuple[int, int, list[str]]:
    """(沿用的, 新取的, 警告)。"""
    reports, stray = check.load_entries(root)
    warnings = list(stray)
    out.mkdir(parents=True, exist_ok=True)
    kept = fresh = 0
    for report in reports:
        e = report.entry
        if report.errors or not isinstance(e, dict):
            continue
        name = file_name(e["id"], e["version"])
        if have is not None and (have / name).is_file():
            shutil.copyfile(have / name, out / name)
            kept += 1
            continue
        try:
            package = registry.fetch(e["url"])
        except registry.FetchError as ex:
            warnings.append(f"{e['id']}：包下载不了（{ex}），这次没有说明")
            continue
        if hashlib.sha256(package).hexdigest() != e["sha256"]:
            warnings.append(f"{e['id']}：包的 sha256 和条目对不上，这次没有说明")
            continue
        data = readme_of(package)
        if data is None:
            warnings.append(f"{e['id']}：包里没有可用的 README.md（没有、是空的或超过 1 MB）")
            continue
        (out / name).write_bytes(data)
        fresh += 1
    return kept, fresh, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="取出每个插件包里的 README.md")
    ap.add_argument("--out", default="dist/readmes", help="输出文件夹，默认 dist/readmes")
    ap.add_argument("--have", metavar="DIR", help="已经发布过的 readme-*.md 所在的文件夹：里面有的不再下载")
    ap.add_argument("--root", default=str(registry.ROOT), help="插件库仓库，默认是工具所在的这个")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = ap.parse_args()
    kept, fresh, warnings = collect(Path(args.root).resolve(), Path(args.have) if args.have else None, Path(args.out))
    for text in warnings:
        print("警告：" + text)
    print(f"说明：沿用 {kept} 份，新取 {fresh} 份，写在 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
