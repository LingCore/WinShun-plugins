"""Pure naming rules and recoverable, non-overwriting Windows rename batches."""
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import unicodedata
import uuid


class RenameError(Exception):
    pass


@dataclass
class Item:
    source: Path
    target: Path
    error: str = ""

    @property
    def changed(self):
        return str(self.source) != str(self.target)


def key(path):
    return os.path.normcase(os.path.abspath(path)).casefold()


def natural_key(value):
    return tuple((1, int(s)) if s.isdigit() else (0, s.casefold())
                 for s in re.split(r"(\d+)", str(value)))


def validate_name(name):
    if not name or name in (".", ".."):
        return "名称不能为空"
    if any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name):
        return "名称含 Windows 不允许的字符"
    if name.endswith((" ", ".")):
        return "名称不能以空格或句点结尾"
    if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])", name.split(".")[0].rstrip()):
        return "Windows 保留名称"
    if len(name.encode("utf-16-le")) // 2 > 255:
        return "名称超过 255 个 UTF-16 单位"
    return ""


def split_name(path, extension=False):
    if path.is_dir() or extension:
        return path.name, ""
    suffix = path.suffix
    return path.name[:-len(suffix)] if suffix else path.name, suffix


def format_number(value, kind="阿拉伯数字", width=1):
    value, width = int(value), int(width)
    if kind in ("英文小写字母", "英文大写字母"):
        if not 1 <= value <= 1_000_000_000:
            raise ValueError("字母序号从 1 开始，最大十亿")
        result = ""
        while value:
            value, digit = divmod(value - 1, 26)
            result = chr(65 + digit) + result
        return result.lower() if kind == "英文小写字母" else result
    if kind in ("中文小写数字", "中文大写数字"):
        if not 0 <= value <= 99_999_999:
            raise ValueError("中文序号范围为 0–99999999")
        digits = "零壹贰叁肆伍陆柒捌玖" if kind == "中文大写数字" else "零一二三四五六七八九"
        units = "仟佰拾" if kind == "中文大写数字" else "千百十"
        def group(number):
            output, zero = "", False
            for divisor, unit in ((1000, units[0]), (100, units[1]), (10, units[2]), (1, "")):
                digit, number = divmod(number, divisor)
                if digit:
                    if zero and output:
                        output += digits[0]
                    output += digits[digit] + unit
                    zero = False
                elif output:
                    zero = True
            return output
        high, low = divmod(value, 10000)
        result = (group(high) + "万" if high else "") + (digits[0] if high and 0 < low < 1000 else "") + group(low)
        if kind == "中文小写数字" and result.startswith("一十"):
            result = result[1:]
        return result or digits[0]
    if not 1 <= width <= 12:
        raise ValueError("编号位数应为 1–12")
    return str(value).zfill(width)


def file_information(path, options):
    kind = options.get("info", "修改日期")
    if kind in ("修改日期", "创建日期"):
        stat = path.stat()
        value = stat.st_mtime if kind == "修改日期" else getattr(stat, "st_birthtime", stat.st_ctime)
        pattern = {"YYYYMMDD": "%Y%m%d", "YYYY-MM-DD": "%Y-%m-%d", "YYYY-MM-DD_HH-mm-ss": "%Y-%m-%d_%H-%M-%S"}.get(options.get("date_format"), "%Y%m%d")
        return datetime.fromtimestamp(value).strftime(pattern)
    if kind == "文件大小":
        if path.is_dir():
            return "文件夹"
        size = path.stat().st_size
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB":
                return (f"{size:.1f}".rstrip("0").rstrip(".") if unit != "B" else str(size)) + unit
            size /= 1024
    if kind == "扩展名":
        return path.suffix.lstrip(".") if not path.is_dir() else ""
    if kind == "所在文件夹":
        return path.parent.name
    return split_name(path)[0]


def transform(name, index, mode, options, path=None):
    if mode == "replace":
        for find, replacement in options.get("rules", []):
            if not find:
                continue
            if options.get("regex"):
                name = re.sub(find, replacement, name, flags=re.I if options.get("ignore_case") else 0)
            elif options.get("ignore_case"):
                name = re.sub(re.escape(find), lambda _: replacement, name, flags=re.I)
            else:
                name = name.replace(find, replacement)
    elif mode == "smart":
        if options.get("normalize"):
            name = unicodedata.normalize("NFKC", name)
        if options.get("spaces"):
            name = re.sub(r"\s+", " ", name).strip()
        if options.get("separators"):
            name = re.sub(r"[_\- ]{2,}", "_", name)
        if options.get("remove_number"):
            name = re.sub(r"^\s*\d+[\s._\-、)）]+", "", name)
        case = options.get("case", "保持大小写")
        if case == "全部小写":
            name = name.lower()
        elif case == "全部大写":
            name = name.upper()
        elif case == "单词首字母大写":
            name = name.title()
    elif mode == "insert":
        text = options.get("text", "")
        kind = options.get("insert_kind", "文本")
        if kind == "序号":
            text = format_number(int(options.get("start", 1)) + index * int(options.get("step", 1)), options.get("number_type", "阿拉伯数字"), options.get("width", 1))
            text = options.get("insert_before", "") + text + options.get("insert_after", "")
        elif kind == "文件信息":
            if path is None:
                raise ValueError("文件信息需要源文件")
            text = options.get("insert_before", "") + file_information(path, options) + options.get("insert_after", "")
        where = options.get("where", "开头")
        position = 0 if where == "开头" else len(name) if where == "末尾" else min(len(name), max(0, int(options.get("position", 0))))
        name = name[:position] + text + name[position:]
    elif mode == "number":
        value = int(options.get("start", 1)) + index * int(options.get("step", 1))
        number = format_number(value, options.get("number_type", "阿拉伯数字"), options.get("width", 3))
        template = options.get("template", "{n}_{name}")
        # Two literal placeholders only; never evaluate Python format expressions.
        name = template.replace("{name}", name).replace("{n}", number)
    return name


def make_plan(paths, mode, options, manual=None):
    plan = []
    for index, value in enumerate(paths):
        path = Path(os.path.abspath(value))
        base, suffix = split_name(path, options.get("extension", False))
        try:
            name = (manual or {}).get(str(path), path.name) if mode in ("manual", "ai") else transform(base, index, mode, options, path) + suffix
            item = Item(path, path.with_name(name)) if not validate_name(name) else Item(path, path, validate_name(name))
        except (ValueError, re.error, OverflowError, IndexError, OSError) as exc:
            item = Item(path, path, "规则无效：" + str(exc))
        plan.append(item)
    return validate_plan(plan)


def identity(path):
    stat = Path(path).stat(follow_symlinks=False)
    return [stat.st_dev, stat.st_ino]


def validate_plan(plan):
    sources = {key(item.source) for item in plan}
    targets, ids = {}, {}
    for item in plan:
        item.error = item.error or validate_name(item.target.name)
        try:
            if not item.source.exists():
                item.error = "源文件不存在"
            elif item.source.is_symlink() or item.source.is_junction():
                item.error = "暂不支持符号链接或目录联接"
            else:
                ident = tuple(identity(item.source))
                if ident in ids:
                    item.error = ids[ident].error = "重复文件或硬链接，请只保留一个"
                ids[ident] = item
        except OSError:
            item.error = "无法读取源文件信息"
        if item.target.parent != item.source.parent:
            item.error = "只能修改名称，不能移动文件"
        target = key(item.target)
        if target in targets:
            item.error = targets[target].error = "多个项目产生相同名称"
        targets[target] = item
        if os.path.lexists(item.target) and target not in sources:
            item.error = "目标名称已存在"
        for parent in item.source.parents:
            if key(parent) in sources:
                item.error = "不能同时重命名父文件夹及其内部项目"
                break
    return plan


def write_journal(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def move(source, target):
    # Windows os.rename atomically refuses an existing destination. Never use replace.
    if os.path.lexists(target):
        raise RenameError("目标已存在：" + Path(target).name)
    os.rename(source, target)


def restore(journal):
    journal = Path(journal)
    record = json.loads(journal.read_text(encoding="utf-8"))
    found, inverse = [], []
    for entry in record["entries"]:
        matches = []
        for location in entry["locations"]:
            if any(key(location) == key(p) for p in matches):
                # Case-only renames have the same key, so prefer the real current spelling below.
                continue
            try:
                if identity(location) == entry["identity"]:
                    actual = Path(location)
                    # Resolve the stored spelling through the directory listing on Windows.
                    actual = next((p for p in actual.parent.iterdir() if key(p) == key(actual)), actual)
                    matches.append(actual)
            except OSError:
                pass
        if len(matches) != 1:
            raise RenameError("无法定位原项目，请勿移动或替换批次文件：" + Path(entry["original"]).name)
        found.append(matches[0])
        inverse.append(Item(matches[0], Path(entry["original"])))
    if any(item.error for item in validate_plan(inverse)):
        raise RenameError("原名称被占用或文件已变化，无法撤销；未修改任何项目。")
    temps = [p.with_name(".wsrename-undo-" + uuid.uuid4().hex) for p in found]
    for entry, temp in zip(record["entries"], temps):
        entry["locations"].append(str(temp))
    record["state"] = "restoring"
    write_journal(journal, record)
    for source, temp in zip(found, temps):
        move(source, temp)
    for temp, entry in zip(temps, record["entries"]):
        move(temp, entry["original"])
    journal.unlink()
    return len(found)


def execute(plan, journal):
    # Recheck everything at the moment of execution, independent of cached preview.
    validate_plan(plan)
    if any(item.error for item in plan):
        raise RenameError("请先解决预览中的冲突或无效名称。")
    changes = [item for item in plan if item.changed]
    if not changes:
        return 0
    journal = Path(journal)
    if journal.exists():
        previous = json.loads(journal.read_text(encoding="utf-8"))
        if previous.get("state") != "complete":
            raise RenameError("发现未完成批次，请先点击撤销 / 恢复。")
    entries = []
    for item in changes:
        temp = item.source.with_name(".wsrename-" + uuid.uuid4().hex)
        entries.append({"original": str(item.source), "target": str(item.target),
                        "temp": str(temp), "identity": identity(item.source),
                        "locations": [str(temp), str(item.target), str(item.source)]})
    record = {"version": 1, "state": "prepared", "entries": entries}
    write_journal(journal, record)
    try:
        for item, entry in zip(changes, entries):
            if identity(item.source) != entry["identity"]:
                raise RenameError("文件在预览后发生变化")
            move(item.source, entry["temp"])
        for entry in entries:
            move(entry["temp"], entry["target"])
        record["state"] = "complete"
        write_journal(journal, record)
    except Exception as exc:
        try:
            restore(journal)
        except Exception:
            raise RenameError("批次中断，部分项目待恢复。请点击撤销 / 恢复；恢复记录已保留。") from exc
        raise RenameError("改名失败，已恢复原名称：" + str(exc)) from exc
    return len(changes)
