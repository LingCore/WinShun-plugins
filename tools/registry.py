#!/usr/bin/env python3
"""插件库的共用部分：条目的字段、包的网址、下载、GitHub 接口、安全地解开 .wsplugin、读写条目。

check.py、entry.py、index.py、update.py 都用它，它自己不检查插件（那是 check.py 的事）。
只用标准库，Python 3.10+。
"""
from __future__ import annotations

import io
import json
import os
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "LingCore/WinShun-plugins"
CONTRIBUTING = f"https://github.com/{REPO}/blob/main/CONTRIBUTING.md"
USER_AGENT = "WinShun-plugins-tools"

MAX_PACKAGE = 64 * 1024 * 1024    # 和 Win顺 的 Gallery.h kMaxPackageBytes 一样
MAX_UNPACKED = 256 * 1024 * 1024  # Install.h kMaxArchiveBytes：解开后最多这么大
MAX_ENTRIES = 10000               # 压缩包里最多这么多项
MAX_API = 16 * 1024 * 1024        # 一次 GitHub 接口的回答

# 条目 plugins/<id>.json 的字段，也是写文件时的顺序
AUTHOR_KEYS = ("id", "repo", "autoUpdate")  # 作者定（entry.py 帮着填）
MAINTAINER_KEYS = ("bundled", "hosted")     # 只有维护者能改
GENERATED_KEYS = ("version", "url", "sha256", "size", "name", "description", "author", "license", "homepage",
                  "keywords", "permissions", "runtime", "minWinShun", "releaseDate", "dateAdded")  # 工具生成，不手写
ENTRY_KEYS = AUTHOR_KEYS + MAINTAINER_KEYS + GENERATED_KEYS

REPO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}")
PLAIN_VERSION_RE = re.compile(r"\d+\.\d+\.\d+")
TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
ASSET_RE = re.compile(r"(?P<id>.+)-(?P<version>\d+\.\d+\.\d+)\.wsplugin")


class FetchError(Exception):
    """下载或者 GitHub 接口出错了。"""


# ---------------------------------------------------------------- 网址和版本

@dataclass
class AssetUrl:
    repo: str     # 作者/仓库
    tag: str
    file: str     # <id>-<X.Y.Z>.wsplugin
    id: str
    version: str


def asset_url(url) -> AssetUrl | None:
    """https://github.com/<作者>/<仓库>/releases/download/<标签>/<id>-<X.Y.Z>.wsplugin 拆开；不是这个样子就是 None。"""
    if not isinstance(url, str):
        return None
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.netloc != "github.com" or parts.query or parts.fragment:
        return None
    segments = parts.path.split("/")  # ['', 作者, 仓库, 'releases', 'download', 标签…, 文件]
    if len(segments) < 7 or segments[0] or segments[3:5] != ["releases", "download"]:
        return None
    repo = f"{segments[1]}/{segments[2]}"
    tag = urllib.parse.unquote("/".join(segments[5:-1]))
    file = urllib.parse.unquote(segments[-1])
    m = ASSET_RE.fullmatch(file)
    if not REPO_RE.fullmatch(repo) or segments[2] in (".", "..") or not tag or not m:
        return None
    return AssetUrl(repo, tag, file, m["id"], m["version"])


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split("."))


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(text) -> datetime | None:
    if not isinstance(text, str) or not TIME_RE.fullmatch(text):
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def tree_url(repo: str, tag: str) -> str:
    return f"https://github.com/{repo}/tree/{urllib.parse.quote(tag, safe='')}"


def compare_url(repo: str, old_tag: str, new_tag: str) -> str:
    return f"https://github.com/{repo}/compare/{urllib.parse.quote(old_tag, safe='')}...{urllib.parse.quote(new_tag, safe='')}"


# ---------------------------------------------------------------- 下载和 GitHub 接口

def fetch(url: str, limit: int = MAX_PACKAGE) -> bytes:
    """下载一个文件（不带令牌：跳转到别的域名时不能把它带过去）。超过 limit 就不要了。"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as ex:
        raise FetchError(f"HTTP {ex.code}") from None
    except (urllib.error.URLError, OSError) as ex:
        raise FetchError(str(getattr(ex, "reason", ex))) from None
    if len(data) > limit:
        raise FetchError(f"超过 {limit >> 20} MB")
    return data


def api(path: str):
    """GitHub 接口的一次 GET；找不到（404）是 None。设了 GH_TOKEN 或 GITHUB_TOKEN 就带上（不带每小时只能 60 次）。"""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request("https://api.github.com" + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read(MAX_API).decode("utf-8"))
    except urllib.error.HTTPError as ex:
        if ex.code == 404:
            return None
        raise FetchError(f"GitHub 接口 {path}：HTTP {ex.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as ex:
        raise FetchError(f"GitHub 接口 {path}：{getattr(ex, 'reason', ex)}") from None


def release_by_tag(repo: str, tag: str) -> dict | None:
    return api(f"/repos/{repo}/releases/tags/{urllib.parse.quote(tag, safe='')}")


def releases(repo: str, pages: int = 10) -> list[dict]:
    """仓库的全部 Release（新的在前；草稿只有有权限的人看得到）。仓库不存在是空的。"""
    out: list[dict] = []
    for page in range(1, pages + 1):
        batch = api(f"/repos/{repo}/releases?per_page=100&page={page}")
        if not batch:
            break
        out += batch
        if len(batch) < 100:
            break
    return out


def asset_of(release: dict, file: str) -> dict | None:
    return next((a for a in release.get("assets") or [] if a.get("name") == file), None)


def digest_of(asset: dict) -> str:
    """GitHub 给附件记的 sha256（老附件没有，是空的）。"""
    digest = asset.get("digest") or ""
    return digest[len("sha256:"):] if digest.startswith("sha256:") else ""


# ---------------------------------------------------------------- 安全地解开 .wsplugin

def unpack(data: bytes, dest: Path) -> list[str]:
    """把 .wsplugin 解到 dest（一个空文件夹）。返回问题，没问题就是空的。

    照 Win顺 的 Install.cpp：plugin.json 在最外层，或者在唯一的一个文件夹里，解出来都放在 dest 下。
    比它更严：绝对路径、..、盘符、符号链接、加密、重名、没标 UTF-8 的非 ASCII 名字、
    Win顺 解不开的压缩方式，一律不收。只解开，不运行里面的任何东西。
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        infos = archive.infolist()
    except Exception:  # 坏压缩包的各种样子
        return ["不是有效的 zip 压缩包"]
    if len(infos) > MAX_ENTRIES:
        return [f"压缩包里有 {len(infos)} 项，太多了"]
    problems: list[str] = []
    entries: list[tuple[zipfile.ZipInfo, str, bool]] = []
    total = 0
    root: str | None = None  # 都在一个文件夹里时是 "文件夹/"
    manifest_at_root = False
    for info in infos:
        name = info.filename.replace("\\", "/")
        if not name.strip("/"):
            continue
        if not info.flag_bits & 0x800 and not name.isascii():
            problems.append(f"{name}：名字里有非 ASCII 字符，压缩包却没标 UTF-8（不同电脑上解出来的名字会不一样）")
            continue
        if name.startswith("/"):
            problems.append(f"{name}：是绝对路径")
            continue
        if ":" in name or name == ".." or "../" in name or "/.." in name:
            problems.append(f"{name}：越出了插件文件夹")
            continue
        if info.flag_bits & 0x1:
            problems.append(f"{name}：加了密")
            continue
        if stat.S_ISLNK(info.external_attr >> 16) or info.external_attr & 0x400:  # Unix 的符号链接；Windows 的重解析点
            problems.append(f"{name}：是符号链接")
            continue
        directory = name.endswith("/")
        if not directory and info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            problems.append(f"{name}：压缩方式 Win顺 解不开（只认不压缩和 deflate）")
            continue
        total += info.file_size
        slash = name.find("/")
        top = "" if slash < 0 else name[: slash + 1]
        root = top if root is None else (root if root == top else "")
        if name.lower() == "plugin.json":
            manifest_at_root = True
        entries.append((info, name, directory))
    if total > MAX_UNPACKED:
        problems.append(f"解开后超过 {MAX_UNPACKED >> 20} MB")
    if problems:
        return problems
    if not entries:
        return ["压缩包是空的"]
    if manifest_at_root or root is None:
        root = ""  # plugin.json 在最外层：旁边的文件夹都是插件自己的
    if not manifest_at_root and not (root and any(n.lower() == (root + "plugin.json").lower() for _, n, _ in entries)):
        return ["压缩包里没有 plugin.json（要在最外层，或者在唯一的一个文件夹里）"]

    base = dest.resolve()
    seen: set[str] = set()
    for info, name, directory in entries:
        relative = name[len(root):]
        parts = [p for p in relative.split("/") if p and p != "."]
        if not parts:
            continue
        target = dest.joinpath(*parts)
        if not target.resolve().is_relative_to(base):
            problems.append(f"{name}：越出了插件文件夹")
            continue
        key = "/".join(parts).lower()
        if not directory:
            if key in seen:
                problems.append(f"{name}：和另一个文件重名（Windows 不分大小写）")
                continue
            seen.add(key)
        try:
            if directory:
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
        except Exception as ex:  # 坏数据、CRC 不对、文件和文件夹同名……
            problems.append(f"{name}：解不开（{ex}）")
    return problems


# ---------------------------------------------------------------- 条目文件

def entry_path(root: Path, pid: str) -> Path:
    return root / "plugins" / f"{pid}.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ordered(entry: dict) -> dict:
    """按固定顺序排字段；bundled、hosted 是 false 就不写。"""
    out = {k: entry[k] for k in ENTRY_KEYS if k in entry and not (k in MAINTAINER_KEYS and entry[k] is False)}
    out.update({k: v for k, v in entry.items() if k not in out and k not in ENTRY_KEYS})  # 不认识的留着，让检查报出来
    return out


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def write_json(path: Path, obj) -> None:
    """UTF-8、LF 换行（write_text 在 Windows 上会写成 CRLF）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dumps(obj).encode("utf-8"))


def same(a, b) -> bool:
    """按 JSON 比：true 和 1、1 和 1.0 算不一样。"""
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)
