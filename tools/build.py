#!/usr/bin/env python3
"""打包：把插件文件夹打成 <id>-<version>.wsplugin。

用法：
  python tools/build.py <文件夹> [--id ID] [--out DIR]   检查并打包一个插件文件夹（作者仓库的发布工作流用它）
  python tools/build.py --legacy [--out DIR]             打包 legacy/ 下的全部老插件，另写 DIR/legacy.tsv（本仓库的发布工作流用）

同样的文件一定打出同样的包（文件按名字排序、时间固定、不压缩），所以 sha256 可以拿来比对。
打进包的文件和 check.py 检查的是同一份（check.source_files：提交过的文件，以点开头的不要）。
index.json 和 README 的插件表由 index.py 用条目生成。只用标准库，Python 3.10+。
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I 不会自己加脚本所在的文件夹
import check  # noqa: E402
import registry  # noqa: E402

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
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as z:
        for p in check.source_files(folder):  # 已按相对路径排好
            info = zipfile.ZipInfo(p.relative_to(folder).as_posix(), FIXED_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            z.writestr(info, p.read_bytes())


def build(folder: Path, out: Path, expected_id: str | None, label: str) -> tuple[check.Result, dict | None]:
    """检查，过了就打包。返回检查结果和包的信息（id、version、file、sha256、name）。"""
    r = check.check_plugin(folder, expected_id=expected_id, label=label)
    version = (r.manifest or {}).get("version")
    if not r.errors and not (isinstance(version, str) and registry.PLAIN_VERSION_RE.fullmatch(version)):
        r.error("plugin.json", f"version {version} 要是 1.2.3 这样的三段数字：插件库只收正式版本")
    if r.errors:
        return r, None
    m = r.manifest
    target = out / f"{m['id']}-{m['version']}.wsplugin"
    pack(folder, target)
    built = {"id": m["id"], "version": m["version"], "file": target.name,
             "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
             "name": " ".join(pick(m["name"]).split()) or m["id"]}
    print(f"打包 {target.name}（{target.stat().st_size} 字节，sha256 {built['sha256']}）")
    return r, built


def main() -> int:
    ap = argparse.ArgumentParser(description="检查并打包插件文件夹")
    ap.add_argument("folder", nargs="?", help="要打包的插件文件夹（比如你自己仓库的根目录）")
    ap.add_argument("--id", help="和插件文件夹一起用：它应该是的 id")
    ap.add_argument("--legacy", action="store_true", help="打包 legacy/ 下的全部老插件")
    ap.add_argument("--out", default="dist", help="输出文件夹，默认 dist/")
    ap.add_argument("--root", default=str(registry.ROOT), help="插件库仓库（--legacy 用），默认是工具所在的这个")
    ap.add_argument("--github-output", metavar="FILE",
                    help="把包的 id、version、file、sha256、name 追加到这个文件（GitHub Actions 的 $GITHUB_OUTPUT）")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    if bool(args.folder) == args.legacy:
        ap.error("要么给一个插件文件夹，要么用 --legacy")

    out = Path(args.out)
    if args.legacy:
        rows, bad = [], 0
        for folder in check.legacy_folders(Path(args.root)):
            r, built = build(folder, out, folder.name, f"legacy/{folder.name}")
            for text in r.errors:
                print("错误：" + text)
            bad += bool(r.errors)
            if built:
                rows.append("\t".join(built[k] for k in ("id", "version", "file", "sha256", "name")))
        if bad:
            print("检查没过，不打包。先跑 python tools/check.py")
            return 1
        out.mkdir(parents=True, exist_ok=True)
        (out / "legacy.tsv").write_bytes("".join(row + "\n" for row in rows).encode("utf-8"))
        print(f"写了 {out / 'legacy.tsv'}（{len(rows)} 个老插件）")
        return 0

    r, built = build(Path(args.folder), out, args.id, Path(args.folder).as_posix())
    for text in r.warnings:
        print("警告：" + text)
    for text in r.errors:
        print("错误：" + text)
    if not built:
        print("检查没过，不打包")
        return 1
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8", newline="\n") as f:
            f.write("".join(f"{k}={built[k]}\n" for k in ("id", "version", "file", "sha256", "name")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
