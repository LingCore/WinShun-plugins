#!/usr/bin/env python3
"""自动更新：开了 autoUpdate 的插件，去它的仓库看有没有新版本；--verify 每天核对一遍每个条目的包。

用法：
  python tools/update.py [ID ...]                 只看不改：哪些插件有新版本，能不能直接收录
  python tools/update.py --write [--out DIR]      能直接收录的写进 plugins/<id>.json；要人看的写到 DIR，给工作流开 PR 或 Issue
  python tools/update.py --verify [--out DIR]     每个条目的包还在不在、sha256 变没变；有问题的写到 DIR，给工作流开 Issue
  --summary FILE                                  另写一份 Markdown 摘要（工作流的运行摘要）

新版本：仓库里正式发布（不是草稿、预发布）的 Release 上叫 <id>-X.Y.Z.wsplugin 的附件，比条目新的里面取最高的。
像 entry.py 一样下载、检查，再和条目现在的包比：
  - 权限没多、范围没变、运行方式没变：直接收录（--write 时改条目）。
  - 多要了权限、权限范围变了、运行方式变了：开 PR 让维护者看（DIR/<id>.json 是新条目，DIR/<id>.md 是 PR 的说明）。
  - 检查没过：开 Issue（DIR/<id>.md）。
DIR/review.tsv 每行一项：种类（pr 或 issue）、id、版本、标题。DIR/updated.txt 是直接收录的，一行一个。
不运行插件里的任何东西。设了 GH_TOKEN 就用它调 GitHub 接口。只用标准库，Python 3.10+。
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I 不会自己加脚本所在的文件夹
import check  # noqa: E402
import registry  # noqa: E402


class Finding:
    """要人看的一项：pr（新条目 + 说明）或 issue（说明）。"""

    def __init__(self, kind: str, pid: str, version: str, title: str, body: list[str], entry: dict | None = None) -> None:
        self.kind, self.id, self.version, self.title, self.body, self.entry = kind, pid, version, title, body, entry


def newest(entry: dict, releases: list[dict]) -> tuple[str, dict, dict] | None:
    """正式 Release 上版本最高的 <id>-X.Y.Z.wsplugin：(版本, Release, 附件)。"""
    pattern = re.compile(re.escape(entry["id"]) + r"-(\d+\.\d+\.\d+)\.wsplugin")
    best = None
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        for asset in release.get("assets") or []:
            m = pattern.fullmatch(asset.get("name") or "")
            if m and (best is None or registry.version_key(m[1]) > registry.version_key(best[0])):
                best = (m[1], release, asset)
    return best


def problems_lines(asset: check.Asset) -> list[str]:
    return [f"- 错误：{t}" for t in asset.errors] + [f"- 警告：{t}" for t in asset.warnings]


def look(entry: dict, version: str, release: dict, asset_info: dict) -> tuple[str, Finding | None, dict | None]:
    """检查一个新版本。返回 (摘要里的结果, 要人看的一项, 能直接收录的新条目)。"""
    pid, repo = entry["id"], entry["repo"]
    url = asset_info.get("browser_download_url") or ""
    new = check.check_asset(url, expected_id=pid, release=release)
    parts = registry.asset_url(url)
    old_parts = registry.asset_url(entry["url"])
    links = [f"- 插件仓库：https://github.com/{repo}"]
    if parts:
        links.append(f"- 这个版本的代码：{registry.tree_url(parts.repo, parts.tag)}")
        if old_parts and old_parts.repo.lower() == parts.repo.lower():
            links.append(f"- 和上一版对比：{registry.compare_url(parts.repo, old_parts.tag, parts.tag)}")
    if new.errors or not new.fields:
        body = [f"## 自动更新没通过检查：`{pid}` {version}", "",
                f"{repo} 的 Release 上有新版本 {parts.file if parts else url}，但它没通过检查，插件库还停在 {entry['version']}。", ""]
        body += links + [""] + problems_lines(new) + ["", "作者修好以后再发一个更高的版本就行，插件库会自动跟上。"]
        return "检查没过，开 Issue", Finding("issue", pid, version, f"自动更新没通过检查：{pid} {version}", body), None

    updated = registry.ordered({**entry, **new.fields})  # id、repo、autoUpdate、bundled、hosted、dateAdded 照旧
    old = check.check_asset(entry["url"], expected_id=pid)  # 现在收录的包，拿来比权限和文件
    reasons: list[str] = []
    diff_lines: list[str] = []
    if old.package is None or old.package.manifest is None:
        reasons.append("现在收录的包下载或检查不了，没法比较")
    else:
        diff = check.Diff(old.package, new.package)
        diff_lines = diff.markdown()
        if diff.added:
            reasons.append("多要了权限 " + "、".join(diff.added))
        if diff.rescoped:
            reasons.append("权限的范围变了：" + "、".join(diff.rescoped))
        if diff.runtime:
            reasons.append("运行方式变了：" + "、".join(f"runtime.{k}" for k, _, _ in diff.runtime))
    if not reasons:
        return "直接收录", None, updated
    body = [f"## 自动更新：`{pid}` {entry['version']} → {version}", "",
            f"这个新版本没有直接收录，因为{'；'.join(reasons)}。维护者看过没问题就合并；不想收录就关掉这个 PR，"
            "这个版本以后不会再开 PR。", ""]
    body += links + [f"- 新的包：{url}（{new.fields['size']} 字节，sha256 `{new.fields['sha256']}`）", "",
                     "### 和现在收录的版本比", ""] + (diff_lines or ["- （没法比较）"])
    if new.warnings:
        body += [""] + [f"- 警告：{t}" for t in new.warnings]
    finding = Finding("pr", pid, version, f"更新 {pid} 到 {version}（要维护者看一眼）", body, updated)
    return "要人看，开 PR", finding, None


def run_update(root: Path, only: set[str], write: bool) -> tuple[list[str], list[Finding], list[str]]:
    reports, _ = check.load_entries(root)
    rows: list[str] = []
    findings: list[Finding] = []
    updated: list[str] = []
    cache: dict[str, list[dict]] = {}
    for r in reports:
        e = r.entry or {}
        if (only and r.id not in only) or not e.get("autoUpdate"):
            continue
        if r.errors:
            rows.append(f"| `{r.id}` | {e.get('version', '?')} | — | 条目有错误，先修条目（python tools/check.py） |")
            continue
        repo = e["repo"]
        try:
            if repo.lower() not in cache:
                cache[repo.lower()] = registry.releases(repo)
        except registry.FetchError as ex:
            rows.append(f"| `{r.id}` | {e['version']} | — | 列不出 {repo} 的 Release：{ex} |")
            continue
        best = newest(e, cache[repo.lower()])
        if best is None or registry.version_key(best[0]) <= registry.version_key(e["version"]):
            rows.append(f"| `{r.id}` | {e['version']} | — | 已经是最新的 |")
            continue
        version, release, asset_info = best
        state, finding, entry = look(e, version, release, asset_info)
        rows.append(f"| `{r.id}` | {e['version']} | {version} | {state} |")
        if finding:
            findings.append(finding)
        if entry:
            updated.append(f"{r.id} {e['version']} → {version}")
            if write:
                registry.write_json(registry.entry_path(root, r.id), entry)
    return rows, findings, updated


def run_verify(root: Path, only: set[str]) -> tuple[list[str], list[Finding]]:
    """每个条目的包：Release 还在、附件还在、sha256 和大小没变（GitHub 记了 digest 就用它，没记就下载下来算）。"""
    reports, _ = check.load_entries(root)
    rows: list[str] = []
    findings: list[Finding] = []
    for r in reports:
        e = r.entry or {}
        parts = registry.asset_url(e.get("url"))
        if (only and r.id not in only) or parts is None:
            continue
        problem = ""
        try:
            release = registry.release_by_tag(parts.repo, parts.tag)
            asset = registry.asset_of(release, parts.file) if release else None
            if release is None:
                problem = f"{parts.repo} 里找不到标签 {parts.tag} 的 Release（404）"
            elif asset is None:
                problem = f"{parts.repo} 的 {parts.tag} 里没有 {parts.file} 了"
            elif registry.digest_of(asset):
                if registry.digest_of(asset) != e.get("sha256") or asset.get("size") != e.get("size"):
                    problem = f"{parts.file} 被换过：GitHub 记的 sha256 是 {registry.digest_of(asset)}，条目里是 {e.get('sha256')}"
            else:
                data = registry.fetch(e["url"])
                if hashlib.sha256(data).hexdigest() != e.get("sha256") or len(data) != e.get("size"):
                    problem = f"{parts.file} 被换过：下载到的 sha256 是 {hashlib.sha256(data).hexdigest()}，条目里是 {e.get('sha256')}"
        except registry.FetchError as ex:
            if str(ex).startswith("HTTP 404") or str(ex).startswith("HTTP 410"):
                problem = f"{e['url']} 下载不了：{ex}"
            else:
                rows.append(f"| `{r.id}` | {e.get('version')} | 这次问不到 GitHub（{ex}），下次再看 |")
                continue
        rows.append(f"| `{r.id}` | {e.get('version')} | {problem or '没问题'} |")
        if problem:
            body = [f"## 插件包不见了或者被换过：`{r.id}` {e.get('version')}", "", f"- {problem}",
                    f"- 条目：plugins/{r.id}.json，包：{e['url']}", "",
                    "Win顺 的插件库现在装不了这个版本，或者装到的不是收录时检查过的那个文件。"
                    "作者发一个新版本（开了 autoUpdate 会自动跟上），或者维护者先把条目撤下。"]
            findings.append(Finding("issue", r.id, str(e.get("version")), f"插件包不见了或者被换过：{r.id} {e.get('version')}", body))
    return rows, findings


def write_out(out: Path, findings: list[Finding], updated: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    for f in findings:
        lines.append("\t".join((f.kind, f.id, f.version, f.title)))
        (out / f"{f.id}.md").write_bytes(("\n".join(f.body) + "\n").encode("utf-8"))
        if f.entry is not None:
            registry.write_json(out / f"{f.id}.json", f.entry)
    (out / "review.tsv").write_bytes("".join(line + "\n" for line in lines).encode("utf-8"))
    (out / "updated.txt").write_bytes("".join(line + "\n" for line in updated).encode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="自动更新开了 autoUpdate 的插件；--verify 核对每个条目的包")
    ap.add_argument("ids", nargs="*", metavar="ID", help="只看这些插件")
    ap.add_argument("--write", action="store_true", help="能直接收录的写进 plugins/<id>.json")
    ap.add_argument("--verify", action="store_true", help="核对每个条目的包还在、没被换过")
    ap.add_argument("--out", metavar="DIR", help="要人看的写到这里（给工作流开 PR、Issue 用）")
    ap.add_argument("--summary", metavar="FILE", help="另写一份 Markdown 摘要")
    ap.add_argument("--root", default=str(registry.ROOT), help="插件库仓库，默认是工具所在的这个")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    only = set(args.ids)

    updated: list[str] = []
    if args.verify:
        rows, findings = run_verify(root, only)
        lines = ["## 核对插件包", "", "| 插件 | 版本 | 结果 |", "|---|---|---|"] + rows
    else:
        rows, findings, updated = run_update(root, only, args.write)
        lines = ["## 自动更新", "", "| 插件 | 现在 | 新版本 | 结果 |", "|---|---|---|---|"] + rows
        if updated and not args.write:
            lines += ["", "（只看不改：加 --write 才会改条目）"]
    if not rows:
        lines.append("| — | — | — |" if args.verify else "| — | — | — | 没有开 autoUpdate 的插件 |")
    for f in findings:
        lines += ["", f"### {f.title}", ""] + f.body[2:]
    text = "\n".join(lines) + "\n"
    print(text)
    if args.summary:
        Path(args.summary).write_bytes(text.encode("utf-8"))
    if args.out:
        write_out(Path(args.out), findings, updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
