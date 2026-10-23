#!/usr/bin/env python3
"""插件检查：照着 Win顺 的 src/plugin/Manifest.cpp 校验 plugin.json，再加本仓库自己的规矩。

用法：
  python tools/check.py                      检查 plugins/ 下全部插件
  python tools/check.py --changed a b ...    只检查这些插件（插件 id、文件夹或其中的文件路径都行）
  python tools/check.py --base origin/main   改过内容的插件必须升 version（要在 git 仓库里跑）
  python tools/check.py --summary out.md     另写一份给审核者看的 Markdown（权限一栏，高风险加粗）

有错误退出码是 1，只有警告是 0。只用标准库，Python 3.10+。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"

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
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.name = folder.name
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.manifest: dict | None = None
        self.info: dict = {}

    def error(self, where: str, text: str) -> None:
        self.errors.append(f"plugins/{self.name}/{where}：{text}" if where else f"plugins/{self.name}：{text}")

    def warn(self, where: str, text: str) -> None:
        self.warnings.append(f"plugins/{self.name}/{where}：{text}" if where else f"plugins/{self.name}：{text}")


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


def check_files(r: Result, folder: Path) -> list[Path]:
    files = sorted(p for p in folder.rglob("*") if p.is_file() or p.is_symlink())
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


def check_plugin(folder: Path) -> Result:
    r = Result(folder)
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
        if pid != folder.name:
            r.error("plugin.json", f"id 是 {pid}，和文件夹名 {folder.name} 不一致")
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

    files = check_files(r, folder)

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


# ---------------------------------------------------------------- 整个仓库

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


def plugin_folders() -> list[Path]:
    return sorted(p for p in PLUGINS.iterdir() if p.is_dir()) if PLUGINS.is_dir() else []


def check_all(only: set[str] | None = None) -> tuple[list[Result], None]:
    """检查 plugins/ 里的全部插件；only 不为空时只返回这些的结果（冲突仍按全部算）。"""
    results = [check_plugin(f) for f in plugin_folders()]
    ids: dict[str, str] = {}
    keywords: dict[str, list[str]] = {}
    for r in results:
        if r.manifest is None:
            continue
        pid = r.manifest.get("id")
        if isinstance(pid, str):
            if pid in ids:
                r.error("plugin.json", f"id {pid} 和 plugins/{ids[pid]} 重复")
            ids.setdefault(pid, r.name)
        for k in keywords_of(r.manifest):
            keywords.setdefault(k.lower(), [])
            if r.name not in keywords[k.lower()]:
                keywords[k.lower()].append(r.name)
    pairs: dict[tuple[str, str], list[str]] = {}
    for k, owners in keywords.items():
        for x in owners:
            for y in owners:
                if x != y:
                    pairs.setdefault((x, y), []).append(k)
    for r in results:
        for (x, y), ks in sorted(pairs.items()):
            if x == r.name:
                r.warn("plugin.json", f"关键字 {'、'.join(ks)} 和 {y} 撞了（用户可以在设置里改，但最好换一个）")
    if only is not None:
        results = [r for r in results if r.name in only]
    return results, None


def changed_names(tokens: list[str]) -> set[str]:
    names: set[str] = set()
    for t in tokens:
        t = t.strip().replace("\\", "/")
        if not t:
            continue
        parts = t.split("/")
        if parts[0] == "plugins" and len(parts) >= 2:
            names.add(parts[1])
        elif "/" not in t:
            names.add(t)
    return names


def check_bumped(results: list[Result], base: str) -> None:
    """改过内容的插件必须升 version。"""
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True)

    if git("rev-parse", "--verify", "--quiet", base).returncode != 0:
        print(f"提示：找不到 {base}，跳过版本号检查", file=sys.stderr)
        return
    for r in results:
        if r.manifest is None:
            continue
        old = git("show", f"{base}:plugins/{r.name}/plugin.json")
        if old.returncode != 0:
            continue  # 新插件
        if git("diff", "--quiet", base, "--", f"plugins/{r.name}").returncode == 0:
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


def summary_markdown(results: list[Result]) -> str:
    lines = ["## 插件检查", ""]
    if not results:
        return "\n".join(lines + ["这次没有改到插件。", ""])
    lines += ["| 插件 | 版本 | 运行方式 | 权限（粗体 = 审核时多看一眼） | 结果 |", "|---|---|---|---|---|"]
    for r in results:
        m = r.manifest or {}
        names, paths = permissions_of(m) if m else ([], [])
        shown = [f"**{n}**" if n in RISKY else n for n in names]
        runtime = m.get("runtime")
        how = "零代码" if not isinstance(runtime, dict) else f"{runtime.get('mode', '?')} · {runtime.get('program', '?')}"
        state = "有错误" if r.errors else ("有警告" if r.warnings else "通过")
        lines.append(f"| `{r.name}` | {m.get('version', '?')} | {how} | {'、'.join(shown) or '无'} | {state} |")
    for r in results:
        m = r.manifest or {}
        _, paths = permissions_of(m) if m else ([], [])
        if paths or r.errors or r.warnings:
            lines += ["", f"### `{r.name}`"]
            if paths:
                lines.append("读这些文件：" + "、".join(f"`{p}`" for p in paths))
            lines += [f"- 错误：{t}" for t in r.errors]
            lines += [f"- 警告：{t}" for t in r.warnings]
    lines += ["", "审核者：权限里的粗体项，对照 README 里的说明和代码，看是不是真的需要。", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="检查 plugins/ 下的插件")
    ap.add_argument("--changed", nargs="*", metavar="PATH", help="只检查这些插件（id、文件夹或其中的文件路径）")
    ap.add_argument("--base", metavar="REF", help="和这个 git 版本比，改过内容的插件必须升 version")
    ap.add_argument("--summary", metavar="FILE", help="另写一份给审核者看的 Markdown")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    only = changed_names(args.changed) if args.changed is not None else None
    results, _ = check_all(only)
    if args.base:
        check_bumped(results, args.base)
    for r in results:
        for text in r.warnings:
            print("警告：" + text)
    for r in results:
        for text in r.errors:
            print("错误：" + text)
    if args.summary:
        Path(args.summary).write_text(summary_markdown(results), encoding="utf-8")
    bad = sum(1 for r in results if r.errors)
    print(f"检查了 {len(results)} 个插件：{bad} 个有错误，{sum(len(r.warnings) for r in results)} 条警告")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
