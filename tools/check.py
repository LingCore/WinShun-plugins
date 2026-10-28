#!/usr/bin/env python3
"""插件检查：照着 Win顺 的 src/plugin/Manifest.cpp 校验 plugin.json，再加本仓库自己的规矩；
也检查插件库的条目 plugins/<id>.json（联网时下载它指向的包，重新算一遍生成的字段）。

用法：
  python tools/check.py                         检查全部：plugins/<id>.json 条目和 legacy/ 里的老插件（不联网）
  python tools/check.py <文件夹> [--id ID]       只检查一个插件文件夹，比如你自己仓库的根目录（--id：它应该是的 id）
  python tools/check.py --online [ID ...]       再下载这些条目（不写就是全部）的包，生成的字段必须和包里的一致
  python tools/check.py --pr BASE               检查一个 PR（和 BASE 比）：只许改 plugins/<id>.json 和 legacy/ 里已有的
                                                老插件；改到的条目联网核对，改到的老插件必须升 version
  python tools/check.py --root DIR ...          检查 DIR 这个仓库，不是工具所在的这个（CI 用基础分支的工具查 PR）
  python tools/check.py --summary out.md        另写一份给审核者看的 Markdown（权限一栏，高风险加粗）

有错误退出码是 1，只有警告是 0。联网的部分设了 GH_TOKEN 就用它调 GitHub 接口。只用标准库，Python 3.10+。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I 不会自己加脚本所在的文件夹
import registry  # noqa: E402

ROOT = registry.ROOT

MANIFEST_VERSION = 1

# 和 Manifest.cpp 的 kPermissions 同顺序（索引里的权限名按这个顺序排）
PERMISSIONS = [
    "files:write", "processes", "clipboard:read", "clipboard:write", "ui", "network",
    "winshun:search", "winshun:open", "winshun:history", "winshun:content", "files:read",
]
# 审核者要多看一眼的
RISKY = {"network", "files:write", "processes", "ui", "winshun:content", "clipboard:read", "clipboard:write"}

ALLOWED_PROGRAMS = {"python", "pwsh", "powershell", "node"}  # Manifest.cpp 另外认插件文件夹里的 exe，本仓库不收
FORBIDDEN_EXT = {".exe", ".dll", ".sys", ".com", ".scr", ".msi", ".bat", ".cmd", ".vbs", ".jar", ".pyc"}
MAX_FILE = 1024 * 1024
MAX_TOTAL = 5 * 1024 * 1024
ICON_EXT = {".png", ".jpg", ".jpeg", ".ico"}
ICON_SCHEMES = ("ext:", "file:", "app:", "glyph:", "color:", "data:", "site:")
KNOWN_TOP = {"$schema", "manifest", "id", "name", "version", "description", "author", "homepage", "license",
             "icon", "minWinShun", "runtime", "permissions", "commands", "settings", "ai"}

VERSION_RE = re.compile(r"\d+(\.\d+)*([-+][0-9A-Za-z.-]+)?")  # Manifest.cpp kVersion
SEMVER_RE = re.compile(r"\d+\.\d+\.\d+([-+][0-9A-Za-z.-]+)?")  # 本仓库：至少 x.y.z
SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]+:(?!\d)")  # WebShortcut.cpp normalizeWebUrl


# ---------------------------------------------------------------- 照 Manifest.cpp 的校验

def valid_plugin_id(s: str) -> bool:
    if not s or len(s) > 64 or s[0] == "." or s[-1] == ".":
        return False
    return all(("a" <= c <= "z") or ("0" <= c <= "9") or c in "._-" for c in s)


def inside_folder(rel: str) -> bool:
    if not rel or rel[0] in "/\\" or ":" in rel:
        return False
    return ".." not in rel.replace("\\", "/").split("/")


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


class Errors:
    def __init__(self) -> None:
        self.items: list[str] = []

    def fail(self, text: str) -> None:
        if text not in self.items:
            self.items.append(text)

    def __bool__(self) -> bool:
        return bool(self.items)


def read_text(v, where: str, e: Errors) -> bool:
    """Text：字符串或 {zh, en}。返回有没有给值。"""
    if v is None:
        return False
    if isinstance(v, str):
        return True
    if isinstance(v, dict):
        zh = v.get("zh") if isinstance(v.get("zh"), str) else ""
        en = v.get("en") if isinstance(v.get("en"), str) else ""
        if not zh and not en:
            e.fail(f"{where} 要有 zh 或 en")
            return False
        return True
    e.fail(f"{where} 要是字符串或 {{zh, en}}")
    return False


def string_field(o: dict, key: str, where: str, e: Errors) -> str:
    v = o.get(key)
    if v is None:
        return ""
    if not isinstance(v, str):
        e.fail(f"{where}.{key} 要是字符串")
        return ""
    return v


def int_field(o: dict, key: str, where: str, e: Errors) -> None:
    v = o.get(key)
    if v is None:
        return
    if not is_num(v):
        e.fail(f"{where}.{key} 要是数字")


def string_list(v, where: str, e: Errors) -> list[str]:
    if isinstance(v, str):
        return [v]
    if not isinstance(v, list):
        e.fail(f"{where} 要是字符串或字符串数组")
        return []
    out = []
    for item in v:
        if not isinstance(item, str):
            e.fail(f"{where} 里有不是字符串的项")
            return out
        out.append(item)
    return out


def relative_inside(path: str, where: str, e: Errors) -> bool:
    if not inside_folder(path):
        e.fail(f"{where} 必须是插件文件夹里的相对路径")
        return False
    return True


def read_runtime(v, e: Errors) -> dict | None:
    if v is None:
        return None
    if not isinstance(v, dict):
        e.fail("runtime 要是对象")
        return None
    where = "runtime"
    info = {"mode": "", "program": "", "script": ""}
    mode = string_field(v, "mode", where, e)
    if mode in ("once", "resident"):
        info["mode"] = mode
    else:
        e.fail("runtime.mode 要是 once 或 resident")
    program = string_field(v, "program", where, e)
    info["program"] = program
    if program in ALLOWED_PROGRAMS:
        pass
    elif not program:
        e.fail("runtime.program 不能为空")
    else:
        # Manifest.cpp 把它当插件文件夹里的 exe；本仓库不收二进制
        if relative_inside(program, "runtime.program", e):
            e.fail("runtime.program 只能是 python、pwsh、powershell 或 node（本仓库不收 exe）")
    if "args" in v:
        string_list(v["args"], "runtime.args", e)
    script = string_field(v, "script", where, e)
    if not script:
        script = {"python": "main.py", "pwsh": "main.ps1", "powershell": "main.ps1", "node": "main.js"}.get(program, "")
    else:
        relative_inside(script, "runtime.script", e)
    info["script"] = script
    cwd = string_field(v, "cwd", where, e)
    if cwd:
        relative_inside(cwd, "runtime.cwd", e)
    env = v.get("env")
    if isinstance(env, dict):
        for key, val in env.items():
            if key.upper().startswith("WS_"):
                e.fail("runtime.env 不能设置 WS_* 变量")
                break
            if not isinstance(val, str):
                e.fail("runtime.env 的值要是字符串")
                break
    elif env is not None:
        e.fail("runtime.env 要是对象")
    encoding = string_field(v, "encoding", where, e)
    if encoding and encoding.lower() not in ("utf-8", "oem"):
        e.fail("runtime.encoding 要是 utf-8 或 oem")
    for key in ("timeoutMs", "debounceMs", "idleExitSec"):
        int_field(v, key, where, e)
    start = string_field(v, "start", where, e)
    if start not in ("", "lazy", "eager"):
        e.fail("runtime.start 要是 lazy 或 eager")
    int_field(v, "memoryMB", where, e)
    sandbox = string_field(v, "sandbox", where, e)
    if sandbox not in ("", "normal", "strict"):
        e.fail("runtime.sandbox 要是 normal 或 strict")
    return info


def read_permissions(v, e: Errors) -> list[str]:
    found: set[str] = set()
    if v is None:
        return []
    if not isinstance(v, list):
        e.fail("permissions 要是数组")
        return []
    for item in v:
        if isinstance(item, str):
            if item not in PERMISSIONS:
                e.fail(f"permissions 里的 {item} 不认识（可能需要更新的 Win顺）")
                return sorted(found, key=PERMISSIONS.index)
            found.add(item)
        elif isinstance(item, dict):
            for key, val in item.items():
                if key not in PERMISSIONS:
                    e.fail(f"permissions 里的 {key} 不认识（可能需要更新的 Win顺）")
                    return sorted(found, key=PERMISSIONS.index)
                found.add(key)
                if key == "files:read":
                    string_list(val, "permissions.files:read", e)
        else:
            e.fail("permissions 里有不是字符串的项")
            return sorted(found, key=PERMISSIONS.index)
    return sorted(found, key=PERMISSIONS.index)


def regex_ok(pattern: str) -> bool:
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def read_trigger(v, where: str, e: Errors) -> None:
    if not isinstance(v, dict):
        e.fail(f"{where} 要是对象")
        return
    if "regex" in v:
        pattern = string_field(v, "regex", where, e)
        if not regex_ok(pattern):
            e.fail(f"{where}.regex 不是有效的正则表达式")
        int_field(v, "minLength", where, e)
        int_field(v, "maxLength", where, e)
    elif "push" in v:
        push = v["push"] if isinstance(v["push"], dict) else {}
        for key in ("minLength", "maxLength", "maxItems"):
            int_field(push, key, f"{where}.push", e)
    elif "files" in v:
        files = v["files"] if isinstance(v["files"], dict) else {}
        kind = string_field(files, "kind", f"{where}.files", e) or "any"
        if kind not in ("file", "folder", "any"):
            e.fail(f"{where}.files.kind 要是 file、folder 或 any")
        if "extensions" in files:
            string_list(files["extensions"], f"{where}.files.extensions", e)
        int_field(files, "max", f"{where}.files", e)
    elif "clipboard" in v:
        clip = v["clipboard"] if isinstance(v["clipboard"], dict) else {}
        pattern = string_field(clip, "regex", f"{where}.clipboard", e)
        if pattern and not regex_ok(pattern):
            e.fail(f"{where}.clipboard.regex 不是有效的正则表达式")
    else:
        e.fail(f"{where} 要是 regex、push、files 或 clipboard 之一")


def normalize_web_url(text: str) -> str:
    url = text.strip()
    if not url:
        return ""
    if "%s" not in url and "%25s" in url:
        url = url.replace("%25s", "%s")
    if not SCHEME_RE.match(url):
        url = "https://" + url
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return ""
    if len(parts.scheme) < 2 or parts.scheme == "file":
        return ""
    if parts.scheme in ("http", "https") and not host:
        return ""
    return url


def read_run(v, where: str, e: Errors) -> str:
    """返回 run 的种类，没有 run 返回 ''。"""
    if v is None:
        return ""
    if not isinstance(v, dict):
        e.fail(f"{where} 要是对象")
        return ""
    kinds = []
    if "url" in v:
        kinds.append("url")
        raw = string_field(v, "url", where, e)
        string_field(v, "home", where, e)
        if not normalize_web_url(raw):
            e.fail(f"{where}.url 不是网址")
    if "program" in v:
        kinds.append("program")
        program = string_field(v, "program", where, e)
        string_field(v, "args", where, e)
        string_field(v, "cwd", where, e)
        if not program:
            e.fail(f"{where}.program 不能为空")
    if "folder" in v:
        kinds.append("folder")
        if not string_field(v, "folder", where, e):
            e.fail(f"{where}.folder 不能为空")
    if "search" in v:
        kinds.append("search")
        search = v["search"]
        scope = ""
        if isinstance(search, str):
            pass
        elif isinstance(search, dict):
            string_field(search, "query", f"{where}.search", e)
            scope = string_field(search, "scope", f"{where}.search", e)
        else:
            e.fail(f"{where}.search 要是字符串或 {{query, scope}}")
        if scope and scope not in ("all", "files", "folders", "content"):
            e.fail(f"{where}.search.scope 要是 all、files、folders 或 content")
    if "items" in v:
        kinds.append("items")
        items = v["items"]
        if not isinstance(items, list):
            e.fail(f"{where}.items 要是数组")
        else:
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("title"), str):
                    e.fail(f"{where}.items 里的每一项要有 title")
                    break
    if not kinds:
        e.fail(f"{where} 要是 url、program、folder、search 或 items 之一")
        return ""
    if len(kinds) > 1:
        e.fail(f"{where} 只能是 url、program、folder、search、items 中的一种")
    return kinds[0]


def read_command(v, index: int, has_runtime: bool, e: Errors) -> dict:
    where = f"commands[{index}]"
    info = {"id": "", "keywords": [], "icon": ""}
    if not isinstance(v, dict):
        e.fail(f"{where} 要是对象")
        return info
    cid = string_field(v, "id", where, e)
    info["id"] = cid
    if not cid:
        e.fail(f"{where}.id 不能为空")
    elif not valid_plugin_id(cid):
        e.fail(f"{where}.id 只能用小写字母、数字、点、连字符和下划线")
    for key in ("title", "description", "hint"):
        read_text(v.get(key), f"{where}.{key}", e)
    icon = string_field(v, "icon", where, e)
    info["icon"] = icon
    if icon.lower().endswith(".svg"):
        e.fail(f"{where}.icon 是 SVG：Win顺 不带 SVG 支持，请用 PNG")
    if "keyword" in v:
        keywords = string_list(v["keyword"], f"{where}.keyword", e)
        info["keywords"] = keywords
        for keyword in keywords:
            if " " in keyword:
                e.fail(f"{where}.keyword 含空格")
            elif not keyword or any(c.isspace() or c == '"' for c in keyword):
                e.fail(f"{where}.keyword 不能为空，也不能含引号")
    if "triggers" in v:
        triggers = v["triggers"]
        if not isinstance(triggers, list):
            e.fail(f"{where}.triggers 要是数组")
        else:
            for i, t in enumerate(triggers):
                read_trigger(t, f"{where}.triggers[{i}]", e)
    mode = string_field(v, "mode", where, e)
    if mode not in ("", "list", "instant"):
        e.fail(f"{where}.mode 要是 list 或 instant")
    if "actions" in v:
        actions = v["actions"]
        if not isinstance(actions, list):
            e.fail(f"{where}.actions 要是数组")
        else:
            for i, a in enumerate(actions):
                aw = f"{where}.actions[{i}]"
                if not isinstance(a, dict):
                    e.fail(f"{aw} 要是对象")
                    break
                aid = string_field(a, "id", aw, e)
                read_text(a.get("title"), f"{aw}.title", e)
                string_field(a, "key", aw, e)
                if not aid:
                    e.fail(f"{aw}.id 不能为空")
    run_kind = read_run(v.get("run"), f"{where}.run", e)
    if not run_kind and not has_runtime:
        e.fail(f"{where} 没有 run，插件也没有 runtime：不知道怎么执行")
    if "cache" in v:
        cache = v["cache"]
        if isinstance(cache, dict):
            int_field(cache, "seconds", f"{where}.cache", e)
        elif not is_num(cache):
            e.fail(f"{where}.cache 要是 {{seconds}} 或数字")
    return info


def read_setting(v, index: int, e: Errors) -> None:
    where = f"settings[{index}]"
    if not isinstance(v, dict):
        e.fail(f"{where} 要是对象")
        return
    if not string_field(v, "key", where, e):
        e.fail(f"{where}.key 不能为空")
    kind = string_field(v, "type", where, e)
    if kind not in ("text", "password", "bool", "number", "choice", "folder", "file", "hotkey"):
        e.fail(f"{where}.type 要是 text、password、bool、number、choice、folder、file 或 hotkey")
    read_text(v.get("title"), f"{where}.title", e)
    read_text(v.get("hint"), f"{where}.hint", e)
    if "options" in v and not isinstance(v["options"], list):
        e.fail(f"{where}.options 要是数组")


def validate_manifest(o, e: Errors) -> dict:
    """照 Manifest::parse。返回后面要用的几样东西。"""
    info = {"runtime": None, "permissions": [], "commands": [], "icon": ""}
    if not isinstance(o, dict):
        e.fail("plugin.json 要是一个 JSON 对象")
        return info
    mv = o.get("manifest")
    if not is_num(mv):
        e.fail("缺少 manifest（架构版本，现在是 1）")
        return info
    if int(mv) > MANIFEST_VERSION:
        e.fail(f"这个插件要 manifest {int(mv)}，这个检查只认识到 {MANIFEST_VERSION}：请升级 Win顺")
        return info
    if int(mv) < 1:
        e.fail("manifest 要是 1")
        return info

    pid = string_field(o, "id", "顶层", e)
    if not pid:
        e.fail("缺少 id（作者.名字）")
    elif not valid_plugin_id(pid):
        e.fail("id 只能用小写字母、数字、点、连字符和下划线（作者.名字）")
    if not read_text(o.get("name"), "name", e) and not e:
        e.fail("缺少 name")
    version = string_field(o, "version", "顶层", e)
    if not version:
        e.fail("缺少 version（如 1.0.0）")
    elif not VERSION_RE.fullmatch(version):
        e.fail("version 要像 1.2.0 这样")
    read_text(o.get("description"), "description", e)
    string_field(o, "author", "顶层", e)
    string_field(o, "homepage", "顶层", e)
    string_field(o, "license", "顶层", e)
    icon = string_field(o, "icon", "顶层", e)
    info["icon"] = icon
    if icon.lower().endswith(".svg"):
        e.fail("icon 是 SVG：Win顺 不带 SVG 支持，请用 PNG")
    elif icon:
        relative_inside(icon, "icon", e)
    min_win = string_field(o, "minWinShun", "顶层", e)
    if min_win and not VERSION_RE.fullmatch(min_win):
        e.fail("minWinShun 要像 0.7.0 这样")
    info["runtime"] = read_runtime(o.get("runtime"), e)
    info["permissions"] = read_permissions(o.get("permissions"), e)

    commands = o.get("commands")
    if not isinstance(commands, list) or not commands:
        e.fail("commands 要至少有一个命令")
    else:
        has_runtime = info["runtime"] is not None
        info["commands"] = [read_command(c, i, has_runtime, e) for i, c in enumerate(commands)]
        seen: set[str] = set()
        for c in info["commands"]:
            if c["id"] and c["id"] in seen:
                e.fail(f"commands 里有两个 id 都是 {c['id']} 的命令")
            seen.add(c["id"])
    if "settings" in o:
        settings = o["settings"]
        if not isinstance(settings, list):
            e.fail("settings 要是数组")
        else:
            for i, s in enumerate(settings):
                read_setting(s, i, e)
    return info


# ---------------------------------------------------------------- 本仓库的规矩

def semver_tuple(v: str) -> tuple:
    head = re.split(r"[-+]", v, maxsplit=1)[0]
    pre = "-" in v.split("+", 1)[0]
    return tuple(int(x) for x in head.split(".")) + (0 if pre else 1,)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


class Result:
    """一个插件文件夹的检查结果。label 是消息里怎么称呼它（legacy/<id>、包的文件名、作者给的路径）。"""

    def __init__(self, folder: Path, label: str | None = None) -> None:
        self.folder = folder
        self.name = folder.name
        self.label = label or folder.as_posix()
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.manifest: dict | None = None
        self.info: dict = {}

    def error(self, where: str, text: str) -> None:
        self.errors.append(f"{self.label}/{where}：{text}" if where else f"{self.label}：{text}")

    def warn(self, where: str, text: str) -> None:
        self.warnings.append(f"{self.label}/{where}：{text}" if where else f"{self.label}：{text}")


def is_relative_icon(icon: str) -> bool:
    return bool(icon) and not icon.lower().startswith(ICON_SCHEMES)


def check_icon_file(r: Result, folder: Path, icon: str, where: str) -> None:
    if not is_relative_icon(icon) or icon.lower().endswith(".svg") or not inside_folder(icon):
        return  # svg 和路径出界 Manifest 那段已经报过
    target = folder / icon.replace("\\", "/")
    if target.suffix.lower() not in ICON_EXT:
        r.error("plugin.json", f"{where} 的图标 {icon} 不是 PNG、JPG 或 ICO")
    elif not target.is_file():
        r.error("plugin.json", f"{where} 的图标文件 {icon} 不在插件文件夹里")


def source_files(folder: Path) -> list[Path]:
    """作者的插件文件夹里会打进包的文件（build.py 打包、这里检查，用的都是这一份）。

    在 git 仓库里只算提交过的（没提交的杂物、__pycache__ 不算；plugin.json 还没提交就按文件夹里有的算）；
    以点开头的文件和文件夹（.git、.github、.gitignore……）都不算。
    """
    listed = None
    try:
        done = subprocess.run(["git", "-C", str(folder), "ls-files", "-z"], capture_output=True)
        if done.returncode == 0:
            names = [n for n in done.stdout.decode("utf-8", "surrogateescape").split("\0") if n]
            if "plugin.json" in names:
                listed = [folder / n for n in names]
    except OSError:
        pass
    if listed is None:
        listed = list(folder.rglob("*"))
    files = [p for p in listed if (p.is_file() or p.is_symlink())
             and not any(part.startswith(".") for part in p.relative_to(folder).parts)]
    return sorted(files, key=lambda p: p.relative_to(folder).as_posix())


def check_files(r: Result, folder: Path, packed: bool) -> list[Path]:
    if packed:  # 解开的包：里面的每个文件都算
        files = sorted(p for p in folder.rglob("*") if p.is_file() or p.is_symlink())
    else:
        files = source_files(folder)
    total = 0
    for p in files:
        rel = p.relative_to(folder).as_posix()
        if p.is_symlink():
            r.error(rel, "不能是符号链接")
            continue
        size = p.stat().st_size
        total += size
        if p.suffix.lower() in FORBIDDEN_EXT:
            r.error(rel, f"本仓库不收 {p.suffix.lower()} 文件（不放二进制和批处理）")
        if size > MAX_FILE:
            r.error(rel, f"{size / 1024 / 1024:.1f} MB，单个文件不能超过 1 MB")
        if p.suffix.lower() in (".ps1", ".psm1", ".psd1") and not p.read_bytes().startswith(b"\xef\xbb\xbf"):
            r.error(rel, "PowerShell 文件必须存成带 BOM 的 UTF-8（否则 Windows PowerShell 5.1 里的中文会乱码）")
    if total > MAX_TOTAL:
        r.error("", f"整个文件夹 {total / 1024 / 1024:.1f} MB，不能超过 5 MB")
    return files


def check_imports(r: Result, folder: Path, files: list[Path]) -> None:
    names = {p.name for p in files if not p.is_symlink()}
    py_import = re.compile(r"^\s*(import\s+winshun\b|from\s+winshun\s+import\b)", re.M)
    ps_import = re.compile(r"WinShun\.psm1", re.I)
    for p in files:
        if p.is_symlink():
            continue
        rel = p.relative_to(folder).as_posix()
        suffix = p.suffix.lower()
        if suffix == ".py" and p.name != "winshun.py":
            if py_import.search(p.read_text(encoding="utf-8", errors="replace")) and "winshun.py" not in names:
                r.error(rel, "用了 import winshun，但文件夹里没有 winshun.py（从 Win顺 的 src/plugins-sdk 复制一份进来）")
        elif suffix == ".ps1":
            if ps_import.search(p.read_text(encoding="utf-8-sig", errors="replace")) and "WinShun.psm1" not in names:
                r.error(rel, "引用了 WinShun.psm1，但文件夹里没有它（从 Win顺 的 src/plugins-sdk 复制一份进来）")


def check_plugin(folder: Path, expected_id: str | None = None, label: str | None = None, packed: bool = False) -> Result:
    """检查一个插件文件夹。expected_id：它应该是的 id（老插件是文件夹名，包是条目的 id；不给就不比）。
    packed：这是解开的包（每个文件都算），不是作者的源码文件夹（只算会打进包的）。"""
    r = Result(folder, label)
    manifest_path = folder / "plugin.json"
    if not manifest_path.is_file():
        r.error("", "没有 plugin.json")
        return r
    try:
        obj = load_json(manifest_path)
    except UnicodeDecodeError:
        r.error("plugin.json", "不是 UTF-8 编码")
        return r
    except json.JSONDecodeError as ex:
        r.error("plugin.json", f"不是有效的 JSON：{ex.msg}（第 {ex.pos} 个字符）")
        return r
    errors = Errors()
    info = validate_manifest(obj, errors)
    for text in errors.items:
        r.error("plugin.json", text)
    if not isinstance(obj, dict):
        return r
    r.manifest = obj
    r.info = info

    pid = obj.get("id") if isinstance(obj.get("id"), str) else ""
    if pid:
        if expected_id and pid != expected_id:
            r.error("plugin.json", f"id 是 {pid}，应该是 {expected_id}")
        if "." not in pid.strip("."):
            r.error("plugin.json", f"id {pid} 要写成 作者.名字（带一个点）")
    for key, label in (("author", "作者"), ("license", "许可证")):
        value = obj.get(key)
        if not isinstance(value, str) or not value.strip():
            r.error("plugin.json", f"缺少 {key}（{label}）：本仓库要求每个插件写明")
    version = obj.get("version")
    if isinstance(version, str) and version and not SEMVER_RE.fullmatch(version):
        r.error("plugin.json", f"version {version} 要写成 1.2.3 这样的三段")
    name = obj.get("name")
    if name == "" or (isinstance(name, dict) and not (name.get("zh") or name.get("en"))):
        r.error("plugin.json", "name 不能是空的")
    if not obj.get("description"):
        r.warn("plugin.json", "没有 description：插件列表里会是空的")
    homepage = obj.get("homepage")
    if isinstance(homepage, str) and homepage and not homepage.lower().startswith(("http://", "https://")):
        r.warn("plugin.json", "homepage 应该是 http(s) 链接")
    for key in obj:
        if key not in KNOWN_TOP:
            r.warn("plugin.json", f"顶层字段 {key} 不认识，Win顺 会忽略它（拼错了？）")

    readme = folder / "README.md"
    if not readme.is_file():
        r.error("", "缺少 README.md（写清楚它做什么、要哪些权限、为什么）")
    elif not readme.read_text(encoding="utf-8-sig", errors="replace").strip():
        r.error("README.md", "是空的")

    files = check_files(r, folder, packed)

    runtime = info.get("runtime")
    if runtime and runtime["script"] and inside_folder(runtime["script"]):
        script = folder / runtime["script"].replace("\\", "/")
        if not script.is_file():
            r.error("plugin.json", f"runtime.script {runtime['script']} 不在插件文件夹里")
    check_icon_file(r, folder, info["icon"], "icon")
    for i, c in enumerate(info["commands"]):
        check_icon_file(r, folder, c["icon"], f"commands[{i}].icon")
    check_imports(r, folder, files)
    return r


# ---------------------------------------------------------------- 权限和关键字

def permissions_of(manifest: dict) -> tuple[list[str], list[str]]:
    """(权限名, files:read 的路径)"""
    e = Errors()
    names = read_permissions(manifest.get("permissions"), e)
    paths: list[str] = []
    for item in manifest.get("permissions") or []:
        if isinstance(item, dict) and "files:read" in item:
            v = item["files:read"]
            paths += [v] if isinstance(v, str) else [x for x in v if isinstance(x, str)]
    return names, paths


def keywords_of(manifest: dict) -> list[str]:
    out: list[str] = []
    for c in manifest.get("commands") or []:
        v = c.get("keyword") if isinstance(c, dict) else None
        for k in ([v] if isinstance(v, str) else v if isinstance(v, list) else []):
            if isinstance(k, str) and k not in out:
                out.append(k)
    return out


def permission_scopes(manifest: dict) -> dict[str, str]:
    """权限名 → 它的范围（{"files:read": [路径]} 里的路径；没写范围是 ""）。比两个版本时用。"""
    out: dict[str, str] = {}
    for item in manifest.get("permissions") or []:
        if isinstance(item, str):
            out.setdefault(item, "")
        elif isinstance(item, dict):
            for key, val in item.items():
                out[key] = json.dumps(val, ensure_ascii=False, sort_keys=True)
    return out


# ---------------------------------------------------------------- 包（.wsplugin）

def fields_of(m: dict, data: bytes) -> dict:
    """包里的 plugin.json 和包本身 → 条目里生成的字段（url、releaseDate、dateAdded 另算）。

    和以前 build.py 写进 index.json 的一模一样。别"顺手改进"（比如空的 homepage 填上仓库地址）：
    已发布的 index.json 和旧版 Win顺 都靠这些字段不变。
    """
    runtime = m.get("runtime")
    names, _ = permissions_of(m)
    return {
        "version": m["version"],
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "name": m["name"],
        "description": m.get("description", ""),
        "author": m.get("author", ""),
        "license": m.get("license", ""),
        "homepage": m.get("homepage", ""),
        "keywords": keywords_of(m),
        "permissions": names,
        "runtime": {"mode": runtime["mode"], "program": runtime["program"]} if isinstance(runtime, dict)
                   else {"mode": "zero-code", "program": None},
        "minWinShun": m.get("minWinShun", ""),
    }


class Package:
    """一个 .wsplugin 解开检查的结果。"""

    def __init__(self, label: str) -> None:
        self.label = label
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.manifest: dict | None = None
        self.fields: dict = {}                       # fields_of 的结果；检查没过是空的
        self.files: dict[str, tuple[str, int]] = {}  # 相对路径 → (sha256, 字节数)


def check_package(data: bytes, expected_id: str, version: str, label: str) -> Package:
    """解到系统的临时文件夹（不在仓库里）检查，查完就删。不运行包里的任何东西。"""
    p = Package(label)
    if len(data) > registry.MAX_PACKAGE:
        p.errors.append(f"{label}：超过 {registry.MAX_PACKAGE >> 20} MB")
        return p
    with tempfile.TemporaryDirectory(prefix="winshun-package-") as tmp:
        folder = Path(tmp)
        problems = registry.unpack(data, folder)
        if problems:
            p.errors += [f"{label}：{t}" for t in problems]
            return p
        r = check_plugin(folder, expected_id=expected_id, label=label, packed=True)
        p.errors += r.errors
        p.warnings += r.warnings
        p.manifest = r.manifest
        for f in sorted(x for x in folder.rglob("*") if x.is_file() and not x.is_symlink()):
            content = f.read_bytes()
            p.files[f.relative_to(folder).as_posix()] = (hashlib.sha256(content).hexdigest(), len(content))
    m = p.manifest
    if m is not None and m.get("version") != version:
        p.errors.append(f"{label}：plugin.json 的 version 是 {m.get('version')}，文件名上是 {version}")
    if m is not None and not p.errors:
        p.fields = fields_of(m, data)
    return p


class Asset:
    """条目指向的一个包：下载、和 GitHub 上的 Release 对上、解开检查，算出条目里生成的字段。"""

    def __init__(self, url: str) -> None:
        self.url = url
        self.parts = registry.asset_url(url)
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.release: dict | None = None
        self.package: Package | None = None
        self.fields: dict = {}  # 生成的字段（dateAdded 除外）；检查没过是空的


def check_asset(url: str, expected_id: str | None = None, release: dict | None = None) -> Asset:
    """release：已经拿到的那个 Release（update.py 列 Release 时就有），不给就去问 GitHub。"""
    a = Asset(url)
    parts = a.parts
    if parts is None:
        a.errors.append(f"{url}：不是 GitHub Release 上的包（要像 https://github.com/作者/仓库/releases/download/标签/<id>-1.2.3.wsplugin）")
        return a
    if expected_id and parts.id != expected_id:
        a.errors.append(f"{parts.file}：文件名上的 id 是 {parts.id}，应该是 {expected_id}")
        return a
    try:
        data = registry.fetch(url)
        a.release = release or registry.release_by_tag(parts.repo, parts.tag)
    except registry.FetchError as ex:
        a.errors.append(f"{url}：{ex}")
        return a
    asset = registry.asset_of(a.release, parts.file) if a.release else None
    if a.release is None:
        a.errors.append(f"{parts.repo} 里找不到标签 {parts.tag} 的 Release")
    elif a.release.get("draft") or a.release.get("prerelease"):
        a.errors.append(f"{parts.repo} 的 {parts.tag} 是草稿或预发布：要正式发布的 Release")
    elif asset is None:
        a.errors.append(f"{parts.repo} 的 {parts.tag} 里没有 {parts.file}")
    elif registry.digest_of(asset) and registry.digest_of(asset) != hashlib.sha256(data).hexdigest():
        a.errors.append(f"{parts.file}：下载到的 sha256 和 GitHub 记的不一样")
    a.package = check_package(data, parts.id, parts.version, parts.file)
    a.errors += a.package.errors
    a.warnings += a.package.warnings
    if not a.errors:
        a.fields = dict(a.package.fields, url=url, releaseDate=a.release["published_at"])
    return a


RUNTIME_TUNING = {"timeoutMs", "debounceMs", "idleExitSec", "memoryMB", "start", "encoding"}  # 只调快慢，变了不算


class Diff:
    """同一个插件的两个包比一比。risky：多要了权限、权限的范围变了，或者运行方式变了
    （程序、参数、脚本、沙盒、环境变量……）：这样的新版本要人看过才收录。"""

    def __init__(self, old: Package, new: Package) -> None:
        om, nm = old.manifest or {}, new.manifest or {}
        before, after = permission_scopes(om), permission_scopes(nm)
        self.added = [p for p in PERMISSIONS if p in after and p not in before]
        self.removed = [p for p in PERMISSIONS if p in before and p not in after]
        self.rescoped = [p for p in PERMISSIONS if p in after and p in before and after[p] != before[p]]
        ort = om.get("runtime") if isinstance(om.get("runtime"), dict) else {}
        nrt = nm.get("runtime") if isinstance(nm.get("runtime"), dict) else {}
        self.runtime = [(k, ort.get(k), nrt.get(k)) for k in sorted(set(ort) | set(nrt))
                        if k not in RUNTIME_TUNING and not registry.same(ort.get(k), nrt.get(k))]
        self.files_added = sorted(set(new.files) - set(old.files))
        self.files_removed = sorted(set(old.files) - set(new.files))
        self.files_changed = sorted(f for f in set(old.files) & set(new.files) if old.files[f] != new.files[f])
        self.sizes = {f: size for f, (_, size) in new.files.items()}

    @property
    def risky(self) -> bool:
        return bool(self.added or self.rescoped or self.runtime)

    def markdown(self) -> list[str]:
        lines = []
        if self.added:
            lines.append("- 多要的权限：" + "、".join(f"**{p}**" for p in self.added))
        if self.rescoped:
            lines.append("- 范围变了的权限：" + "、".join(f"**{p}**" for p in self.rescoped))
        if self.removed:
            lines.append("- 不再要的权限：" + "、".join(self.removed))
        for key, a, b in self.runtime:
            lines.append(f"- 运行方式 runtime.{key}：`{json.dumps(a, ensure_ascii=False)}` → `{json.dumps(b, ensure_ascii=False)}`")
        for label, names, sized in (("新增的文件", self.files_added, True), ("改了的文件", self.files_changed, True),
                                    ("删掉的文件", self.files_removed, False)):
            if names:
                shown = [f"`{n}`" + (f"（{self.sizes[n]} 字节）" if sized else "") for n in names[:50]]
                lines.append(f"- {label}：" + "、".join(shown) + (f" 等 {len(names)} 个" if len(names) > 50 else ""))
        if not (self.files_added or self.files_changed or self.files_removed):
            lines.append("- 包里的文件没有变化")
        return lines


# ---------------------------------------------------------------- 条目 plugins/<id>.json

class Report:
    """一个条目的检查结果，和给审核者看的东西。"""

    def __init__(self, pid: str) -> None:
        self.id = pid
        self.label = f"plugins/{pid}.json"
        self.entry: dict | None = None
        self.old: dict | None = None  # PR：基础分支上的这个条目
        self.change = ""              # PR：新增、更新、修改、删除
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []    # 给审核者的链接和说明（Markdown 的列表项）

    def error(self, text: str) -> None:
        self.errors.append(f"{self.label}：{text}")

    def warn(self, text: str) -> None:
        self.warnings.append(f"{self.label}：{text}")


def check_entry_fields(r: Report, obj, root: Path) -> None:
    """不联网能查的：字段齐不齐、样子对不对、和 legacy/ 对不对得上。"""
    if not isinstance(obj, dict):
        r.error("要是一个 JSON 对象")
        return
    r.entry = obj
    for key in obj:
        if key not in registry.ENTRY_KEYS:
            r.error(f"不认识的字段 {key}（拼错了？）")
    missing = [k for k in ("id", "repo") + registry.GENERATED_KEYS if k not in obj]
    if missing:
        r.error("缺少 " + "、".join(missing) + "：用 python tools/entry.py <包的网址> 生成这个文件")
    pid, repo, version = obj.get("id"), obj.get("repo"), obj.get("version")
    if not isinstance(pid, str) or not valid_plugin_id(pid) or "." not in pid.strip("."):
        r.error("id 要写成 作者.名字，只用小写字母、数字、点、连字符和下划线")
    elif pid != r.id:
        r.error(f"id 是 {pid}，文件名应该是 plugins/{pid}.json")
    if "repo" in obj and not (isinstance(repo, str) and registry.REPO_RE.fullmatch(repo)):
        r.error("repo 要写成 作者/仓库（GitHub 上的公开仓库）")
    for key in ("autoUpdate",) + registry.MAINTAINER_KEYS:
        if key in obj and not isinstance(obj[key], bool):
            r.error(f"{key} 要是 true 或 false")
    if "version" in obj and not (isinstance(version, str) and registry.PLAIN_VERSION_RE.fullmatch(version)):
        r.error("version 要写成 1.2.3 这样的三段数字")
    if "url" in obj:
        parts = registry.asset_url(obj["url"])
        if parts is None:
            r.error("url 要是 GitHub Release 上的包：https://github.com/作者/仓库/releases/download/标签/<id>-<版本>.wsplugin")
        else:
            if isinstance(repo, str) and parts.repo.lower() != repo.lower():
                r.error(f"url 不在 {repo} 的 Release 里")
            if parts.id != r.id:
                r.error(f"url 里的文件是 {parts.file}，应该是 {r.id}-<版本>.wsplugin")
            if isinstance(version, str) and parts.version != version:
                r.error(f"url 里的文件是 {parts.version} 版，version 却是 {version}")
    sha = obj.get("sha256")
    if "sha256" in obj and not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha)):
        r.error("sha256 要是 64 位小写十六进制")
    size = obj.get("size")
    if "size" in obj and not (isinstance(size, int) and not isinstance(size, bool) and 0 < size <= registry.MAX_PACKAGE):
        r.error(f"size 要是 1 到 {registry.MAX_PACKAGE} 之间的整数（字节）")
    texts = Errors()
    if "name" in obj and (not read_text(obj["name"], "name", texts) or obj["name"] == ""):
        texts.fail("name 不能是空的")
    if "description" in obj:
        read_text(obj["description"], "description", texts)
    for text in texts.items:
        r.error(text)
    for key in ("author", "license"):
        if key in obj and not (isinstance(obj[key], str) and obj[key].strip()):
            r.error(f"{key} 不能是空的")
    if "homepage" in obj and not isinstance(obj["homepage"], str):
        r.error("homepage 要是字符串")
    keywords = obj.get("keywords")
    if "keywords" in obj and not (isinstance(keywords, list) and all(isinstance(k, str) and k for k in keywords)):
        r.error("keywords 要是字符串数组")
    perms = obj.get("permissions")
    if "permissions" in obj and not (isinstance(perms, list) and all(isinstance(p, str) and p in PERMISSIONS for p in perms)
                                     and perms == sorted(set(perms), key=PERMISSIONS.index)):
        r.error("permissions 要是 Win顺 认识的权限名，不重复，按固定的顺序排（entry.py 会排好）")
    runtime = obj.get("runtime")
    if "runtime" in obj and not (isinstance(runtime, dict) and set(runtime) == {"mode", "program"} and (
            (runtime["mode"] in ("once", "resident") and runtime["program"] in ALLOWED_PROGRAMS)
            or (runtime["mode"] == "zero-code" and runtime["program"] is None))):
        r.error('runtime 要是 {"mode": once 或 resident, "program": python、pwsh、powershell 或 node}，'
                '零代码插件是 {"mode": "zero-code", "program": null}')
    min_win = obj.get("minWinShun")
    if "minWinShun" in obj and not (isinstance(min_win, str) and (not min_win or VERSION_RE.fullmatch(min_win))):
        r.error("minWinShun 要是空的，或者像 0.15.0 这样")
    for key in ("releaseDate", "dateAdded"):
        if key in obj and registry.parse_time(obj[key]) is None:
            r.error(f"{key} 要像 2026-10-28T12:00:00Z 这样（UTC）")
    legacy = root / "legacy" / r.id
    if obj.get("hosted"):
        if not (legacy / "plugin.json").is_file():
            r.error(f"hosted 是 true，可是没有 legacy/{r.id}/")
        if isinstance(repo, str) and repo.lower() != registry.REPO.lower():
            r.error(f"hosted 的插件在本仓库打包发布，repo 要是 {registry.REPO}")
    elif legacy.is_dir():
        r.error(f"legacy/{r.id}/ 在本仓库打包发布，条目要写 hosted: true")


def brief(value) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 80 else text[:77] + "…"


def check_entry_online(r: Report) -> Asset | None:
    """下载条目指向的包，重新算一遍生成的字段，必须和条目里写的一样。"""
    obj = r.entry or {}
    url = obj.get("url")
    if registry.asset_url(url) is None:
        return None  # 不联网的检查已经报过了
    a = check_asset(url, expected_id=r.id)
    r.errors += [f"{r.label}：{t}" for t in a.errors]
    r.warnings += [f"{r.label}：{t}" for t in a.warnings]
    if a.fields:
        wrong = [k for k in a.fields if not registry.same(obj.get(k), a.fields[k])]
        for k in wrong:
            r.error(f"{k} 和包里的不一样（条目里是 {brief(obj.get(k))}，包里是 {brief(a.fields[k])}）")
        if wrong:
            r.error(f"用 python tools/entry.py {url} 重新生成这个文件，生成的字段不要手改")
    return a


def keyword_clashes(reports: list[Report]) -> None:
    owners: dict[str, list[str]] = {}
    for r in reports:
        for k in (r.entry or {}).get("keywords") or []:
            if isinstance(k, str):
                ids = owners.setdefault(k.lower(), [])
                if r.id not in ids:
                    ids.append(r.id)
    for r in reports:
        clash: dict[str, list[str]] = {}
        for k, ids in owners.items():
            if r.id in ids:
                for other in ids:
                    if other != r.id:
                        clash.setdefault(other, []).append(k)
        for other, ks in sorted(clash.items()):
            r.warn(f"关键字 {'、'.join(ks)} 和 {other} 撞了（用户可以在设置里改，但最好换一个）")


# ---------------------------------------------------------------- 整个仓库

def load_entries(root: Path) -> tuple[list[Report], list[str]]:
    """plugins/ 下的全部条目（做过不联网的检查），和 plugins/ 里不该有的东西。"""
    reports: list[Report] = []
    stray: list[str] = []
    folder = root / "plugins"
    for p in sorted(folder.iterdir()) if folder.is_dir() else []:
        if p.suffix != ".json" or not p.is_file() or p.is_symlink():
            what = "符号链接" if p.is_symlink() else ("文件夹" if p.is_dir() else "文件")
            stray.append(f"plugins/{p.name}：plugins/ 里只放条目 <id>.json，不放{what}。插件的代码放在作者自己的仓库里"
                         f"（以前收录的老插件在 legacy/），见 {registry.CONTRIBUTING}")
            continue
        r = Report(p.stem)
        try:
            obj = load_json(p)
        except UnicodeDecodeError:
            r.error("不是 UTF-8 编码")
        except json.JSONDecodeError as ex:
            r.error(f"不是有效的 JSON：{ex.msg}（第 {ex.pos} 个字符）")
        else:
            check_entry_fields(r, obj, root)
        reports.append(r)
    return reports, stray


def legacy_folders(root: Path) -> list[Path]:
    legacy = root / "legacy"
    return sorted(p for p in legacy.iterdir() if p.is_dir()) if legacy.is_dir() else []


def check_legacy(root: Path, reports: list[Report]) -> list[Result]:
    """legacy/ 里的老插件：照旧检查；条目要有，而且文件夹里的版本不能比已发布的低。"""
    results = [check_plugin(f, expected_id=f.name, label=f"legacy/{f.name}") for f in legacy_folders(root)]
    entries = {r.id: r.entry or {} for r in reports}
    for res in results:
        entry = entries.get(res.name)
        if entry is None:
            res.error("", f"没有条目 plugins/{res.name}.json")
            continue
        old, new = entry.get("version"), (res.manifest or {}).get("version")
        try:
            if isinstance(old, str) and isinstance(new, str) and semver_tuple(new) < semver_tuple(old):
                res.error("plugin.json", f"version {new} 比已经发布的 {old} 还低")
        except ValueError:
            pass
    return results


def git_in(root: Path):
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    return git


def check_bumped(results: list[Result], base: str, root: Path) -> None:
    """改过文件的老插件必须升 version（results 的 label 是 legacy/<id>）。"""
    git = git_in(root)
    if git("rev-parse", "--verify", "--quiet", base).returncode != 0:
        print(f"提示：找不到 {base}，跳过版本号检查", file=sys.stderr)
        return
    for r in results:
        if r.manifest is None:
            continue
        old = git("show", f"{base}:{r.label}/plugin.json")
        if old.returncode != 0:
            continue  # 新的
        if git("diff", "--quiet", base, "--", r.label).returncode == 0:
            continue  # 没改
        try:
            old_version = json.loads(old.stdout.decode("utf-8-sig")).get("version")
        except (ValueError, UnicodeDecodeError):
            continue
        new_version = r.manifest.get("version")
        if not (isinstance(old_version, str) and isinstance(new_version, str)):
            continue
        try:
            if semver_tuple(new_version) <= semver_tuple(old_version):
                r.error("plugin.json", f"文件改了，但 version 还是 {new_version}（之前是 {old_version}）：更新要把 version 升上去")
        except ValueError:
            pass


# ---------------------------------------------------------------- PR

def pr_changes(root: Path, base: str) -> list[tuple[str, str]]:
    """(状态, 路径)：A 新增、M 修改、D 删除、T 类型变了（比如变成了符号链接）。"""
    done = git_in(root)("diff", "--name-status", "--no-renames", "-z", base, "HEAD")
    if done.returncode != 0:
        raise SystemExit("git diff 失败：" + done.stderr.decode("utf-8", "replace").strip())
    tokens = done.stdout.decode("utf-8", "surrogateescape").split("\0")
    return [(tokens[i][:1], tokens[i + 1]) for i in range(0, len(tokens) - 1, 2)]


def check_pr_entry(r: Report) -> None:
    """PR 改到的一个条目：谁能改什么，再联网核对；给审核者留下源码和对比的链接。"""
    e, old = r.entry or {}, r.old
    r.change = "新增" if old is None else ("更新" if e.get("version") != old.get("version") else "修改")
    for key in registry.MAINTAINER_KEYS:
        if bool(e.get(key)) != bool((old or {}).get(key)):
            r.error(f"{key} 只有维护者能改")
    if old is None:
        if r.id.startswith("winshun."):
            r.error("winshun. 开头的 id 留给 Win顺 自带的插件")
        added = registry.parse_time(e.get("dateAdded"))
        if added and added > datetime.now(timezone.utc) + timedelta(days=1):
            r.error("dateAdded 不能在将来")
    else:
        if not registry.same(e.get("dateAdded"), old.get("dateAdded")):
            r.error("dateAdded 是第一次收录的时间，不能改")
        if isinstance(e.get("repo"), str) and isinstance(old.get("repo"), str) and e["repo"].lower() != old["repo"].lower():
            r.warn(f"**repo 从 {old['repo']} 换成了 {e['repo']}**：维护者要确认是作者本人搬了家，不是别人接手")
        try:
            if registry.version_key(e["version"]) < registry.version_key(old["version"]):
                r.error(f"version {e['version']} 比原来的 {old['version']} 低")
        except (KeyError, TypeError, ValueError, AttributeError):
            pass
    asset = check_entry_online(r)
    parts = registry.asset_url(e.get("url"))
    if parts is None or asset is None or asset.package is None:
        return
    if r.change == "新增":
        r.notes.append(f"- 第一次收录：请先读一遍这个版本的代码：{registry.tree_url(parts.repo, parts.tag)}")
    elif r.change == "更新":
        r.notes.append(f"- 这个版本的代码：{registry.tree_url(parts.repo, parts.tag)}")
        old_parts = registry.asset_url(old.get("url"))
        if old_parts and old_parts.repo.lower() == parts.repo.lower():
            r.notes.append(f"- 和上一版对比：{registry.compare_url(parts.repo, old_parts.tag, parts.tag)}")
        before = check_asset(old["url"], expected_id=r.id) if old_parts else None
        if before and before.package and before.package.manifest and asset.package.manifest:
            r.notes += Diff(before.package, asset.package).markdown()
        else:
            r.notes.append("- 上一版的包下载或检查不了，没法比较权限和文件")


def check_pr(root: Path, base: str) -> tuple[list[Report], list[Result], list[str]]:
    """投稿的 PR 只能改 plugins/<id>.json，和 legacy/ 里已有的老插件；别的地方一改就不过。
    返回 (改到的条目, 改到的老插件, 改了不该改的地方)。"""
    git = git_in(root)
    if git("rev-parse", "--verify", "--quiet", base + "^{commit}").returncode != 0:
        raise SystemExit(f"找不到 {base}")
    scope: list[str] = []
    entries: dict[str, str] = {}
    legacy: set[str] = set()
    folders: set[str] = set()
    for status, path in pr_changes(root, base):
        parts = path.split("/")
        if parts[0] == "plugins" and len(parts) == 2 and parts[1].endswith(".json"):
            entries[parts[1][: -len(".json")]] = status
        elif parts[0] == "plugins" and len(parts) > 2:
            if parts[1] not in folders:
                folders.add(parts[1])
                scope.append(f"加了 plugins/{parts[1]}/ 文件夹：插件的代码不再放进这个仓库。请在你自己的 GitHub 仓库里发布插件，"
                             f"再来这里加一个 plugins/<id>.json。怎么做见 CONTRIBUTING.md：{registry.CONTRIBUTING}")
        elif parts[0] == "legacy" and len(parts) > 2 \
                and git("cat-file", "-e", f"{base}:legacy/{parts[1]}/plugin.json").returncode == 0:
            legacy.add(parts[1])
        elif parts[0] == "legacy":
            scope.append(f"{path}：legacy/ 只放以前收录的老插件，不再加新的。新插件请放在你自己的仓库里，见 {registry.CONTRIBUTING}")
        else:
            scope.append(f"{path}：投稿的 PR 只能改 plugins/<id>.json（以前收录的老插件还能改 legacy/<id>/ 里的文件）。"
                         "工具、工作流和文档的改动请先开 Issue 和维护者商量")

    reports, _ = load_entries(root)
    keyword_clashes(reports)  # 和全部条目比
    by_id = {r.id: r for r in reports}
    picked: list[Report] = []
    for pid, status in sorted(entries.items()):
        shown = git("show", f"{base}:plugins/{pid}.json")
        old = None
        if shown.returncode == 0:
            try:
                old = json.loads(shown.stdout.decode("utf-8-sig"))
            except (ValueError, UnicodeDecodeError):
                old = None
        r = by_id.get(pid) or Report(pid)
        r.old = old if isinstance(old, dict) else None
        path = registry.entry_path(root, pid)
        if status == "D" or not (path.exists() or path.is_symlink()):
            r.change = "删除"
            r.warn("这个 PR 删掉了这个条目：维护者要确认是作者本人要下架")
        elif pid not in by_id:
            r.error("要是一个普通文件（不能是符号链接）")
        else:
            check_pr_entry(r)
        picked.append(r)

    results: list[Result] = []
    for lid in sorted(legacy):
        folder = root / "legacy" / lid
        if not (folder / "plugin.json").is_file():
            res = Result(folder, f"legacy/{lid}")
            res.error("", "这个 PR 删掉了 plugin.json：要下架老插件请开 Issue 找维护者")
            results.append(res)
        else:
            results.append(check_plugin(folder, expected_id=lid, label=f"legacy/{lid}"))
    check_bumped(results, base, root)
    return picked, results, scope


# ---------------------------------------------------------------- 给审核者的摘要

def folders_markdown(results: list[Result]) -> list[str]:
    lines = ["| 插件 | 版本 | 运行方式 | 权限（粗体 = 审核时多看一眼） | 结果 |", "|---|---|---|---|---|"]
    for r in results:
        m = r.manifest or {}
        names, _ = permissions_of(m) if m else ([], [])
        shown = [f"**{n}**" if n in RISKY else n for n in names]
        runtime = m.get("runtime")
        how = "零代码" if not isinstance(runtime, dict) else f"{runtime.get('mode', '?')} · {runtime.get('program', '?')}"
        state = "有错误" if r.errors else ("有警告" if r.warnings else "通过")
        lines.append(f"| `{r.label}` | {m.get('version', '?')} | {how} | {'、'.join(shown) or '无'} | {state} |")
    for r in results:
        m = r.manifest or {}
        _, paths = permissions_of(m) if m else ([], [])
        if paths or r.errors or r.warnings:
            lines += ["", f"#### `{r.label}`"]
            if paths:
                lines.append("读这些文件：" + "、".join(f"`{p}`" for p in paths))
            lines += [f"- 错误：{t}" for t in r.errors]
            lines += [f"- 警告：{t}" for t in r.warnings]
    return lines


def entries_markdown(reports: list[Report], pr: bool) -> list[str]:
    lines = ["| 条目 | " + ("改动 | " if pr else "") + "版本 | 运行方式 | 权限（粗体 = 审核时多看一眼） | 结果 |",
             "|---|" + ("---|" if pr else "") + "---|---|---|---|"]
    for r in reports:
        e = r.entry or r.old or {}
        version = str(e.get("version", "?"))
        if r.old and r.entry and r.old.get("version") != r.entry.get("version"):
            version = f"{r.old.get('version')} → {version}"
        runtime = e.get("runtime") if isinstance(e.get("runtime"), dict) else {}
        how = "零代码" if runtime.get("mode") == "zero-code" else f"{runtime.get('mode', '?')} · {runtime.get('program', '?')}"
        before = set(r.old.get("permissions") or []) if r.old and r.entry else None
        perms = []
        for p in e.get("permissions") or []:
            text = f"**{p}**" if p in RISKY else str(p)
            perms.append(text + ("（新增）" if before is not None and p not in before else ""))
        state = "有错误" if r.errors else ("有警告" if r.warnings else "通过")
        change = f"{r.change} | " if pr else ""
        lines.append(f"| `{r.id}` | {change}{version} | {how} | {'、'.join(perms) or '无'} | {state} |")
    for r in reports:
        if r.notes or r.errors or r.warnings:
            lines += ["", f"#### `{r.id}`"] + r.notes
            lines += [f"- 错误：{t}" for t in r.errors]
            lines += [f"- 警告：{t}" for t in r.warnings]
    return lines


def summary_markdown(reports: list[Report], legacy: list[Result], scope: list[str], pr: bool) -> str:
    lines = ["## 插件库检查", ""]
    if scope:
        lines += ["### 改了不该改的地方", ""] + [f"- {t}" for t in scope] + [""]
    if reports:
        lines += ["### 条目", ""] + entries_markdown(reports, pr) + [""]
    if legacy:
        lines += ["### legacy/ 里的老插件", ""] + folders_markdown(legacy) + [""]
    if not (scope or reports or legacy):
        lines += ["这次没有改到条目和老插件。", ""]
    lines += ["审核者：新收录的插件，顺着源码链接把那个版本的代码读一遍；更新看多要的权限和改了的文件。"
              "权限里的粗体项，对照插件的 README 和代码，看是不是真的需要。", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="检查插件库的条目和老插件，或者一个插件文件夹")
    ap.add_argument("folder", nargs="?", help="只检查这个插件文件夹（比如你自己仓库的根目录）")
    ap.add_argument("--id", help="和插件文件夹一起用：它应该是的 id")
    ap.add_argument("--online", nargs="*", metavar="ID", help="再下载这些条目（不写就是全部）的包核对")
    ap.add_argument("--pr", metavar="BASE", help="检查一个 PR：和 BASE 比")
    ap.add_argument("--root", default=str(ROOT), help="要检查的仓库，默认是工具所在的这个")
    ap.add_argument("--summary", metavar="FILE", help="另写一份给审核者看的 Markdown")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = ap.parse_args()

    if args.folder:
        folder = Path(args.folder)
        if not folder.is_dir():
            print(f"错误：{args.folder} 不是文件夹")
            return 1
        r = check_plugin(folder, expected_id=args.id, label=folder.as_posix())
        for text in r.warnings:
            print("警告：" + text)
        for text in r.errors:
            print("错误：" + text)
        if args.summary:
            lines = ["## 插件检查", ""] + folders_markdown([r]) + ["", "审核者：权限里的粗体项，对照 README 和代码，看是不是真的需要。", ""]
            Path(args.summary).write_text("\n".join(lines), encoding="utf-8")
        print(f"检查了 {folder.as_posix()}：{len(r.errors)} 个错误，{len(r.warnings)} 条警告")
        return 1 if r.errors else 0

    root = Path(args.root).resolve()
    if args.pr:
        reports, legacy, scope = check_pr(root, args.pr)
    else:
        reports, scope = load_entries(root)
        legacy = check_legacy(root, reports)
        keyword_clashes(reports)
        if args.online is not None:
            wanted = set(args.online) or {r.id for r in reports}
            scope += [f"没有条目 plugins/{pid}.json" for pid in sorted(wanted - {r.id for r in reports})]
            for r in reports:
                if r.id in wanted:
                    check_entry_online(r)
    for item in [*reports, *legacy]:
        for text in item.warnings:
            print("警告：" + text)
    for text in scope:
        print("错误：" + text)
    for item in [*reports, *legacy]:
        for text in item.errors:
            print("错误：" + text)
    if args.summary:
        Path(args.summary).write_text(summary_markdown(reports, legacy, scope, bool(args.pr)), encoding="utf-8")
    bad = len(scope) + sum(1 for item in [*reports, *legacy] if item.errors)
    warnings = sum(len(item.warnings) for item in [*reports, *legacy])
    print(f"检查了 {len(reports)} 个条目、{len(legacy)} 个老插件：{bad} 处有错误，{warnings} 条警告")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
