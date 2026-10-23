# 浏览器书签 · Browser bookmarks: a once Win顺 plugin in Python on the
# winshun.py SDK. Reads the Bookmarks files of Chrome and Edge (every
# profile) and of the file named in the settings, and lists the bookmarks
# whose title, folder or address has every word typed. Enter opens the
# address (a declarative `url`: no second process for the action).
import glob
import json
import os
from urllib.parse import unquote

import winshun

WS_FILES = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data", "*", "Bookmarks"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data", "*", "Bookmarks"),
]


def bookmark_files(settings):
    files = []
    for pattern in WS_FILES:
        files += glob.glob(pattern)
    extra = (settings.get("extraFile") or "").strip()
    if extra and os.path.isfile(extra):
        files.append(extra)
    return files


def browser_of(path):
    lower = path.lower()
    if "\\google\\chrome\\" in lower:
        return "Chrome"
    if "\\microsoft\\edge\\" in lower:
        return "Edge"
    for name in ("Brave", "Vivaldi", "Chromium", "Opera", "Yandex", "Arc"):
        if "\\" + name.lower() in lower:
            return name
    return "书签文件" if winshun.locale() != "en" else "Bookmarks file"


def walk(node, folder, out, browser):
    """Every url under `node`, with the folder it is in."""
    if node.get("type") == "url":
        out.append((node.get("name", ""), node.get("url", ""), folder, browser))
        return
    name = node.get("name", "")
    sub = folder + " › " + name if folder and name else (name or folder)
    for child in node.get("children") or []:
        walk(child, sub, out, browser)


def load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    browser = browser_of(path)
    for root in (data.get("roots") or {}).values():
        if isinstance(root, dict):
            walk(root, "", out, browser)
    return out


def main():
    q = winshun.query()
    settings = winshun.settings()
    words = [w.lower() for w in q.text.split() if w]
    entries = []
    for path in bookmark_files(settings):
        entries += load(path)
    rows = []
    seen = set()
    for title, url, folder, browser in entries:
        # Shown and matched decoded ("…/dotFiles#安装", not "%E5%AE%89%E8%A3%85"); opened as it is.
        shown = unquote(url, errors="replace")
        haystack = (title + "\n" + url + "\n" + shown + "\n" + folder).lower()
        if any(w not in haystack for w in words):
            continue
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        # Title matches rank above address-only matches.
        score = 80 if all(w in title.lower() for w in words) else 60
        rows.append(winshun.item(
            "bm-%d" % len(rows),
            title or shown,
            " · ".join(s for s in (browser, folder, shown) if s),
            # The site's own icon, as the browser shows it; Win顺 fetches it
            # (from the site's home page only) and keeps it.
            icon=("site:" + url) if url.lower().startswith(("https://", "http://")) else "glyph:U+E734",
            score=score,
            url=url,
            copy=url,
            match=title + " " + shown,
        ))
        if len(rows) >= 50:
            break
    rows.sort(key=lambda r: -r["score"])
    if not rows:
        zh = winshun.locale() != "en"
        if not entries:
            rows.append(winshun.item("none", "没有找到书签文件" if zh else "No bookmarks file found",
                                     "装了 Chrome 或 Edge 就会自动读；其他浏览器的在设置里指定" if zh
                                     else "Chrome's and Edge's are read on their own; name another browser's in the settings",
                                     icon="glyph:U+E734", valid=False))
        else:
            rows.append(winshun.item("none", "没有匹配的书签" if zh else "No matching bookmark", q.text,
                                     icon="glyph:U+E734", valid=False))
    winshun.reply(rows, cache=60)


if __name__ == "__main__":
    main()
