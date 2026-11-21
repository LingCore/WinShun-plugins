"""条目的 notes：Release 的说明拆成中文、英文，检查、index、自动更新和 tools/notes.py 都认它。

不联网：GitHub 接口和下载都换成假的。
"""
import argparse
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check
import entry as entry_tool
import index
import notes as notes_tool
import registry
import test_community_native as fixtures
import update

CAPTURE_BODY = (
    "截图时界面卡住超过 0.3 秒，诊断日志会记下当时程序各个线程在做什么。功能和权限没有变化。"
    "设置 → 插件 → 插件库中安装或更新。最低主程序版本为 0.18.0。\n\n"
    "When the interface stops answering for more than 0.3 s during a capture, the diagnostics record "
    "what each thread was doing. No change in features or permissions. "
    "Install or update through Settings → Plugins → Library. Requires WinShun 0.18.0.\n\n"
    "源码 · Source: LingCore/WinShun 1ab46575\n")
ZH = "新插件：把设置备份自动传到 WebDAV（坚果云、Nextcloud）。最低主程序版本为 0.26.0。"
EN = "A new plugin: keeps the settings backup on WebDAV (Nextcloud, 坚果云). Requires WinShun 0.26.0."


class InstallSentenceTest(unittest.TestCase):
    def test_install_sentence_alone_gives_no_notes(self):
        self.assertIsNone(registry.split_notes("Win顺 设置 → 插件 → 从压缩包安装，选 a.b-1.1.0.wsplugin。"))

    def test_install_sentence_dropped_rest_kept(self):
        notes = registry.split_notes("Win顺 设置 → 插件 → 从压缩包安装，选这个 .wsplugin 文件。 需要 Win顺 0.22.0 及以上版本。")
        self.assertEqual(notes["zh"], "需要 Win顺 0.22.0 及以上版本。")


class SplitNotes(unittest.TestCase):
    def test_bilingual_official_body(self):
        notes = registry.split_notes(CAPTURE_BODY)
        zh, en = CAPTURE_BODY.split("\n\n")[:2]
        self.assertEqual(notes, {"zh": zh, "en": en})  # 保留“设置 → 插件 → …”那句；源码那行没了
        self.assertNotIn("Source", notes["zh"] + notes["en"])

    def test_crlf_gives_the_same_result(self):
        self.assertEqual(registry.split_notes(CAPTURE_BODY.replace("\n", "\r\n")), registry.split_notes(CAPTURE_BODY))

    def test_one_cjk_word_in_the_english_paragraph_stays_english(self):
        notes = registry.split_notes(f"{ZH}\n\n{EN}\n\n源码 · Source: LingCore/WinShun 1572a53871")
        self.assertEqual(notes, {"zh": ZH, "en": EN})

    def test_english_words_in_the_chinese_paragraph_stay_chinese(self):
        zh = "连按两次 `Win+E` 出两个窗口的原因找到了（LingCore/WinShun#331）：现在 Win+E 打开的窗口一律并成标签页。"
        en = "A window opened by `Win+E` now always becomes a tab (LingCore/WinShun#331)."
        self.assertEqual(registry.split_notes(f"{zh}\n\n{en}"), {"zh": zh, "en": en})

    def test_chinese_only_body_goes_to_both(self):
        notes = registry.split_notes("v1.0.1：修复回车后不复制的问题。\r\n")
        self.assertEqual(notes, {"zh": "v1.0.1：修复回车后不复制的问题。", "en": "v1.0.1：修复回车后不复制的问题。"})

    def test_english_only_body_goes_to_both(self):
        notes = registry.split_notes("Fixed the crash when the clipboard is empty.\n\n- Faster start-up\n- Smaller package")
        self.assertEqual(notes["zh"], notes["en"])
        self.assertTrue(notes["en"].startswith("Fixed the crash") and notes["en"].endswith("Smaller package"))

    def test_side_with_only_headings_borrows_the_other_side(self):
        body = "### Fixed\r\n\r\n- 修复彩蛋看不到的问题：整屏蒙黑。\r\n- 修复 COM 没有初始化。\r\n\r\n**sha256** `1ec9`  `x.wsplugin`\r\n"
        notes = registry.split_notes(body)
        self.assertEqual(notes["en"], notes["zh"])
        self.assertEqual(notes["zh"], "- 修复彩蛋看不到的问题：整屏蒙黑。\n- 修复 COM 没有初始化。")

    def test_provenance_and_checksum_lines_are_dropped(self):
        body = "\n\n".join([ZH, EN, "源码 · Source: LingCore/WinShun 1ab46575", "Source: LingCore/WinShun 1ab46575",
                           "[完整源码 / Source](https://github.com/LingCore/WinShun/tree/6a9e109)",
                           "**sha256** `6cdae7c3`  `x.wsplugin`", "SHA256：`a707`", "---"])
        self.assertEqual(registry.split_notes(body), {"zh": ZH, "en": EN})
        self.assertEqual(registry.split_notes(f"{ZH}\n{EN}\n源码 · Source: x/y 1"), {"zh": f"{ZH}\n{EN}", "en": f"{ZH}\n{EN}"})
        self.assertIsNone(registry.split_notes("源码 · Source: LingCore/WinShun 1ab46575\n"))

    def test_markdown_inside_paragraphs_is_kept(self):
        zh = "### 修复\n\n- 修复回车后不复制：`Ctrl+C` 现在有效。\n- **注意**：需要重启。"
        en = "### Fixed\n\n- Enter no longer fails to copy; `Ctrl+C` works now.\n- **Note**: restart required."
        notes = registry.split_notes(zh + "\n\n" + en)
        self.assertEqual(notes, {"zh": zh, "en": en})

    def test_blank_lines_inside_a_code_fence_do_not_split(self):
        text = "运行下面的命令：\n```\nws plugin\n\nws list\n```\n\nRun the commands above."
        self.assertEqual(registry.paragraphs(text), ["运行下面的命令：\n```\nws plugin\n\nws list\n```", "Run the commands above."])

    def test_empty_bodies_have_no_notes(self):
        for body in (None, "", "  \r\n\r\n \n", 5, "---", "源码 · Source: LingCore/WinShun 1ab46575"):
            with self.subTest(body=body):
                self.assertIsNone(registry.split_notes(body))

    def test_notes_of_a_release(self):
        self.assertEqual(registry.notes_of({"body": ZH}), {"zh": ZH, "en": ZH})
        self.assertIsNone(registry.notes_of({"body": None}))
        self.assertIsNone(registry.notes_of({}))
        self.assertIsNone(registry.notes_of(None))


class CapNotes(unittest.TestCase):
    def test_short_text_is_untouched(self):
        self.assertEqual(registry.cap_notes("x" * registry.NOTES_MAX), "x" * registry.NOTES_MAX)

    def test_cut_at_a_paragraph_boundary(self):
        paragraphs = [f"第 {i} 段：" + "字" * 90 for i in range(60)]
        capped = registry.split_notes("\n\n".join(paragraphs))["zh"]
        self.assertLessEqual(len(capped), registry.NOTES_MAX)
        self.assertTrue(capped.endswith("…"))
        kept = capped[:-1].split("\n\n")
        self.assertEqual(kept, paragraphs[: len(kept)])  # 整段整段地留，没有切在段中间

    def test_cut_at_a_line_boundary_when_one_paragraph_is_too_long(self):
        lines = [f"- 第 {i} 条：" + "字" * 40 for i in range(100)]
        capped = registry.cap_notes("\n".join(lines))
        self.assertLessEqual(len(capped), registry.NOTES_MAX)
        self.assertEqual(capped[:-1].split("\n"), lines[: len(capped[:-1].split("\n"))])

    def test_one_endless_line_is_cut_hard(self):
        capped = registry.cap_notes("a" * 5000)
        self.assertEqual(len(capped), registry.NOTES_MAX)
        self.assertEqual(capped, "a" * (registry.NOTES_MAX - 1) + "…")

    def test_both_sides_are_capped(self):
        body = "中" * 3000 + "\n\n" + "e" * 3000
        notes = registry.split_notes(body)
        self.assertTrue(all(len(t) <= registry.NOTES_MAX and t.endswith("…") for t in notes.values()))


def release(body, published="2026-11-06T00:00:00Z"):
    return {"draft": False, "prerelease": False, "published_at": published, "body": body,
            "assets": [{"name": "community.native-1.0.0.wsplugin"}]}


class EntryFlow(unittest.TestCase):
    URL = fixtures.entry()["url"]

    def asset(self, body):
        with patch.object(registry, "fetch", return_value=fixtures.package()):
            return check.check_asset(self.URL, release=release(body), unreviewed_native=True)

    def test_asset_takes_notes_from_the_release_not_from_the_package_fields(self):
        asset = self.asset(f"{ZH}\n\n{EN}")
        self.assertEqual(asset.errors, [])
        self.assertEqual(asset.notes, {"zh": ZH, "en": EN})
        self.assertNotIn("notes", asset.fields)  # 说明后来改了，条目不算错
        self.assertIsNone(self.asset(None).notes)

    def test_make_entry_adds_notes_only_when_there_are_some(self):
        args = argparse.Namespace(auto_update=None, bundled=None, hosted=None, unreviewed_native=True, date_added=None)
        with_notes = entry_tool.make_entry(self.asset(f"{ZH}\n\n{EN}"), None, args)
        self.assertEqual(with_notes["notes"], {"zh": ZH, "en": EN})
        self.assertEqual(list(with_notes)[-1], "notes")
        self.assertNotIn("notes", entry_tool.make_entry(self.asset(""), None, args))

    def test_update_swaps_the_old_versions_notes(self):
        old = dict(fixtures.entry(), notes={"zh": "旧的说明", "en": "old notes"})
        info = {"browser_download_url": self.URL}
        with patch.object(registry, "fetch", return_value=fixtures.package()), \
                patch.object(registry, "release_by_tag", return_value=release(None)):  # 比较用的老包要问的 Release
            _, _, new = update.look(old, "1.0.0", release(f"{ZH}\n\n{EN}"), info)
            self.assertEqual(new["notes"], {"zh": ZH, "en": EN})
            _, _, new = update.look(old, "1.0.0", release(None), info)
            self.assertNotIn("notes", new)  # 新版本没有说明，就不留旧版本的

    def test_entry_fields_accept_only_a_notes_object_of_bounded_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            def errors(**change):
                e = dict(fixtures.entry(), **change)
                report = check.Report(e["id"])
                check.check_entry_fields(report, e, Path(tmp))
                return report.errors

            self.assertEqual(errors(), [])
            self.assertEqual(errors(notes={"zh": ZH, "en": EN}), [])
            self.assertEqual(errors(notes={"en": EN}), [])
            self.assertEqual(errors(notes={"zh": "x" * registry.NOTES_MAX}), [])
            for bad in ("说明", [], {}, {"zh": ""}, {"zh": " "}, {"zh": 1}, {"zh": ZH, "fr": "x"}, {"zh": "x" * (registry.NOTES_MAX + 1)}):
                with self.subTest(notes=bad):
                    self.assertTrue(errors(notes=bad))

    def test_index_item_has_notes_when_the_entry_has_them(self):
        e = fixtures.entry()
        self.assertNotIn("notes", index.item_of(e))
        self.assertEqual(index.item_of(dict(e, notes={"zh": ZH, "en": EN}))["notes"], {"zh": ZH, "en": EN})

    def test_online_check_only_warns_when_the_release_text_changed(self):
        data = fixtures.package()  # zip 里记着打包的时间：条目的 sha256 要从这一份算，不能再打一个包
        e = dict(fixtures.entry(), sha256=hashlib.sha256(data).hexdigest(), size=len(data), notes={"zh": ZH, "en": EN})
        for body, warned in ((f"{ZH}\n\n{EN}", False), ("改过的说明。", True), (None, True)):
            with self.subTest(body=body), patch.object(registry, "fetch", return_value=data), \
                    patch.object(registry, "release_by_tag", return_value=release(body)):
                report = check.Report(e["id"])
                report.entry = e
                check.check_entry_online(report)
                self.assertEqual(report.errors, [])
                self.assertEqual(any("notes" in w for w in report.warnings), warned)


class Backfill(unittest.TestCase):
    def run_tool(self, root, *args):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["notes.py", "--root", str(root), *args]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = notes_tool.main()
        return code, out.getvalue(), err.getvalue()

    def test_refresh_adds_updates_and_removes_notes_without_touching_other_fields(self):
        e = fixtures.entry()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plugins" / f"{e['id']}.json"
            registry.write_json(path, registry.ordered(e))
            before = path.read_text(encoding="utf-8")

            with patch.object(registry, "release_by_tag", return_value=release(f"{ZH}\n\n{EN}")) as api:
                self.assertEqual(self.run_tool(tmp, "--dry-run")[0], 0)
                self.assertEqual(path.read_text(encoding="utf-8"), before)  # 只看不写
                self.assertEqual(self.run_tool(tmp)[0], 0)
                api.assert_called_with("Community/Native", "v1.0.0")
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(written["notes"], {"zh": ZH, "en": EN})
            self.assertEqual({k: v for k, v in written.items() if k != "notes"}, registry.ordered(e))
            after = path.read_text(encoding="utf-8")

            with patch.object(registry, "release_by_tag", return_value=release(f"{ZH}\n\n{EN}")):
                self.assertIn("没有变化", self.run_tool(tmp)[1])
            self.assertEqual(path.read_text(encoding="utf-8"), after)

            with patch.object(registry, "release_by_tag", return_value=release("")):  # Release 说明清空了
                self.assertEqual(self.run_tool(tmp)[0], 0)
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_a_failed_fetch_keeps_the_entry_as_it_is(self):
        e = dict(fixtures.entry(), notes={"zh": ZH, "en": EN})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plugins" / f"{e['id']}.json"
            registry.write_json(path, registry.ordered(e))
            before = path.read_bytes()
            for result in (registry.FetchError("HTTP 500"), None):  # 出错；找不到这个 Release
                with self.subTest(result=result), patch.object(notes_tool.time, "sleep"), \
                        patch.object(registry, "release_by_tag", side_effect=[result] if result is None else result):
                    code, _, err = self.run_tool(tmp)
                    self.assertEqual(code, 1)
                    self.assertIn("notes 保持原样", err)
                    self.assertEqual(path.read_bytes(), before)

    def test_a_flaky_fetch_is_tried_again(self):
        e = fixtures.entry()
        with tempfile.TemporaryDirectory() as tmp:
            registry.write_json(Path(tmp) / "plugins" / f"{e['id']}.json", registry.ordered(e))
            flaky = [registry.FetchError("No such file"), release(ZH)]
            with patch.object(notes_tool.time, "sleep"), patch.object(registry, "release_by_tag", side_effect=flaky):
                self.assertEqual(self.run_tool(tmp)[0], 0)
            self.assertEqual(registry.load_json(Path(tmp) / "plugins" / f"{e['id']}.json")["notes"], {"zh": ZH, "en": ZH})


if __name__ == "__main__":
    unittest.main()
