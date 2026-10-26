import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN))
import rename_core as core
from ai_names import AiError, generate
from rename_protocol import serve as rename_serve


class RenameTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.journal = self.root / "data" / "last.json"

    def tearDown(self):
        self.directory.cleanup()

    def file(self, name, content=None):
        path = self.root / name
        path.write_text(content or name, encoding="utf-8")
        return path

    def test_rules_and_extension_preservation(self):
        a, b = self.file("报告 01.txt"), self.file("报告 02.txt")
        plan = core.make_plan([a, b], "replace", {"rules": [("报告", "Report"), (" ", "_")]})
        self.assertEqual([i.target.name for i in plan], ["Report_01.txt", "Report_02.txt"])
        plan = core.make_plan([a], "insert", {"text": "副本_", "where": "开头"})
        self.assertEqual(plan[0].target.name, "副本_报告 01.txt")
        plan = core.make_plan([a, b], "number", {"start": "5", "step": "2", "width": "3", "template": "图片_{n}"})
        self.assertEqual([i.target.name for i in plan], ["图片_005.txt", "图片_007.txt"])
        folder = self.root / "资料.v1"
        folder.mkdir()
        self.assertEqual(core.make_plan([folder], "insert", {"text": "_新", "where": "末尾"})[0].target.name, "资料.v1_新")

    def test_local_smart_rules_and_regex(self):
        path = self.file("０１__  HELLO  World.txt")
        item = core.make_plan([path], "smart", {"normalize": True, "spaces": True, "remove_number": True, "case": "全部小写"})[0]
        self.assertEqual(item.target.name, "hello world.txt")
        item = core.make_plan([path], "replace", {"rules": [("[", "")], "regex": True})[0]
        self.assertIn("规则无效", item.error)
        item = core.make_plan([path], "replace", {"rules": [("txt", "md")], "extension": True})[0]
        self.assertTrue(item.target.name.endswith(".md"))

    def test_chinese_and_alphabet_numbering(self):
        expected = [(0, "零"), (10, "十"), (11, "十一"), (20, "二十"), (101, "一百零一"),
                    (10001, "一万零一"), (10010, "一万零一十"), (10000001, "一千万零一")]
        for value, text in expected:
            self.assertEqual(core.format_number(value, "中文小写数字"), text)
        self.assertEqual(core.format_number(123, "中文大写数字"), "壹佰贰拾叁")
        self.assertEqual(core.format_number(26, "英文小写字母"), "z")
        self.assertEqual(core.format_number(27, "英文大写字母"), "AA")
        self.assertEqual(core.format_number(703, "英文大写字母"), "AAA")
        with self.assertRaises(ValueError):
            core.format_number(0, "英文大写字母")

    def test_insert_sequence_and_file_information_are_local(self):
        path = self.file("photo.txt", "abcd")
        item = core.make_plan([path], "insert", {"insert_kind": "序号", "start": "27", "number_type": "英文小写字母",
                                                "insert_before": "[", "insert_after": "]", "where": "开头"})[0]
        self.assertEqual(item.target.name, "[aa]photo.txt")
        item = core.make_plan([path], "insert", {"insert_kind": "文件信息", "info": "文件大小", "insert_before": "_", "where": "末尾"})[0]
        self.assertEqual(item.target.name, "photo_4B.txt")
        item = core.make_plan([path], "insert", {"insert_kind": "文件信息", "info": "修改日期", "insert_after": "_"})[0]
        self.assertRegex(item.target.name, r"^\d{8}_photo\.txt$")
        self.assertEqual(path.read_text(), "abcd")

    def test_invalid_names_duplicates_existing_and_nested(self):
        for name in ("", "CON.txt", "con .txt", "a/b", "a\\b", "a.", "a ", "LPT¹.png", "x" * 256):
            with self.subTest(name=name):
                self.assertTrue(core.validate_name(name))
        a, b = self.file("a.txt"), self.file("b.txt")
        items = core.make_plan([a, b], "manual", {}, {str(a): "same.txt", str(b): "SAME.TXT"})
        self.assertTrue(all(i.error for i in items))
        self.assertTrue(core.make_plan([a], "manual", {}, {str(a): "b.txt"})[0].error)
        folder = self.root / "folder"
        folder.mkdir()
        child = folder / "child.txt"
        child.touch()
        self.assertTrue(any(i.error for i in core.make_plan([folder, child], "insert", {"text": "x"})))

    def test_swap_and_case_only_and_undo_preserve_contents(self):
        a, b = self.file("a.txt", "A"), self.file("b.txt", "B")
        items = core.make_plan([a, b], "manual", {}, {str(a): "b.txt", str(b): "A.txt"})
        self.assertFalse(any(i.error for i in items))
        self.assertEqual(core.execute(items, self.journal), 2)
        self.assertEqual((self.root / "b.txt").read_text(), "A")
        self.assertEqual((self.root / "A.txt").read_text(), "B")
        self.assertEqual(core.restore(self.journal), 2)
        self.assertEqual(a.read_text(), "A")
        self.assertEqual(b.read_text(), "B")
        self.assertFalse(self.journal.exists())
        self.assertEqual(core.execute(core.make_plan([a], "manual", {}, {str(a): "A.TXT"}), self.journal), 1)
        self.assertIn("A.TXT", [p.name for p in self.root.iterdir()])
        core.restore(self.journal)
        self.assertIn("a.txt", [p.name for p in self.root.iterdir()])

    def test_failure_rolls_back_and_retains_unrelated_files(self):
        a, b = self.file("a.txt"), self.file("b.txt")
        items = core.make_plan([a, b], "insert", {"text": "new-"})
        real_move = core.move
        calls = 0
        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise PermissionError("locked")
            real_move(source, target)
        with patch("rename_core.move", side_effect=fail_second), self.assertRaisesRegex(core.RenameError, "已恢复原名称"):
            core.execute(items, self.journal)
        self.assertEqual(a.read_text(), "a.txt")
        self.assertEqual(b.read_text(), "b.txt")
        self.assertFalse(list(self.root.glob(".wsrename-*")))

    def test_crash_can_be_recovered_in_next_process(self):
        a, b = self.file("a.txt"), self.file("b.txt")
        real_move = core.move
        calls = 0
        def crash(source, target):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise KeyboardInterrupt()
            real_move(source, target)
        with patch("rename_core.move", side_effect=crash), self.assertRaises(KeyboardInterrupt):
            core.execute(core.make_plan([a, b], "insert", {"text": "new-"}), self.journal)
        self.assertTrue(self.journal.exists())
        self.assertFalse(a.exists())
        self.assertEqual(core.restore(self.journal), 2)
        self.assertEqual(a.read_text(), "a.txt")
        self.assertEqual(b.read_text(), "b.txt")

    def test_racing_destination_is_never_overwritten(self):
        a = self.file("a.txt", "original")
        target = self.root / "new-a.txt"
        real_move = core.move
        def race(source, destination):
            if Path(destination) == target:
                target.write_text("other app")
            real_move(source, destination)
        with patch("rename_core.move", side_effect=race), self.assertRaises(core.RenameError):
            core.execute(core.make_plan([a], "insert", {"text": "new-"}), self.journal)
        self.assertEqual(a.read_text(), "original")
        self.assertEqual(target.read_text(), "other app")

    def test_undo_refuses_occupied_original(self):
        a = self.file("a.txt")
        core.execute(core.make_plan([a], "insert", {"text": "new-"}), self.journal)
        a.write_text("another file")
        with self.assertRaises(core.RenameError):
            core.restore(self.journal)
        self.assertEqual(a.read_text(), "another file")
        self.assertTrue((self.root / "new-a.txt").exists())

    def test_journal_directory_and_ancestors_are_rejected_before_any_rename(self):
        for ancestor, existing in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(ancestor=ancestor, existing=existing):
                container = self.root / f"case-{ancestor}-{existing}"
                data = container / "data"
                data.mkdir(parents=True)
                source = container if ancestor else data
                sentinel = source / "keep.txt"
                sentinel.write_text("keep", encoding="utf-8")
                other = self.file(f"other-{ancestor}-{existing}.txt", "other")
                journal = data / "last.json"
                before = b'{"state": "complete", "entries": []}' if existing else None
                if before is not None:
                    journal.write_bytes(before)
                plan = core.make_plan([other, source], "insert", {"text": "new-"})
                self.assertFalse(any(item.error for item in plan))
                with self.assertRaisesRegex(core.RenameError, "恢复记录"):
                    core.execute(plan, journal)
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
                self.assertEqual(other.read_text(encoding="utf-8"), "other")
                self.assertTrue(all(not item.target.exists() for item in plan))
                self.assertEqual(journal.read_bytes() if journal.exists() else None, before)

    def test_journal_and_temporary_journal_cannot_be_renamed(self):
        self.journal.parent.mkdir()
        before = b'{"state": "complete", "entries": []}'
        self.journal.write_bytes(before)
        temporary = self.journal.with_suffix(".tmp")
        temporary.write_bytes(b"previous temporary log")
        for source in (self.journal, temporary):
            with self.subTest(source=source.name):
                plan = core.make_plan([source], "insert", {"text": "new-"})
                with self.assertRaisesRegex(core.RenameError, "恢复记录"):
                    core.execute(plan, self.journal)
                self.assertEqual(self.journal.read_bytes(), before)
                self.assertEqual(temporary.read_bytes(), b"previous temporary log")
                self.assertFalse(plan[0].target.exists())

    def test_restore_rejects_moving_its_own_journal_directory(self):
        source = self.root / "current"
        source.mkdir()
        (source / "keep.txt").write_text("keep", encoding="utf-8")
        original = self.root / "original"
        journal = source / "data" / "last.json"
        core.write_journal(journal, {"version": 1, "state": "complete", "entries": [{
            "original": str(original), "target": str(source),
            "identity": core.identity(source), "locations": [str(source)]}]})
        before = journal.read_bytes()
        with self.assertRaisesRegex(core.RenameError, "恢复记录"):
            core.restore(journal)
        self.assertEqual(journal.read_bytes(), before)
        self.assertEqual((source / "keep.txt").read_text(encoding="utf-8"), "keep")
        self.assertFalse(original.exists())

    def test_sibling_of_journal_directory_can_be_renamed_and_restored(self):
        source = self.root / "documents"
        source.mkdir()
        (source / "keep.txt").write_text("keep", encoding="utf-8")
        plan = core.make_plan([source], "insert", {"text": "new-"})
        self.assertEqual(core.execute(plan, self.journal), 1)
        self.assertEqual(core.restore(self.journal), 1)
        self.assertEqual((source / "keep.txt").read_text(encoding="utf-8"), "keep")


class RenameAiTests(unittest.TestCase):
    def test_only_names_and_instruction_are_uploaded(self):
        def opener(request, timeout):
            body = json.loads(request.data)
            self.assertEqual(request.full_url, "https://text.example/v1/chat/completions")
            content = json.loads(body["messages"][1]["content"])
            self.assertEqual(content, {"instruction": "使用中文", "names": ["test"]})
            self.assertNotIn("image_url", request.data.decode())
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": '{"names":["测试"]}'}, "finish_reason": "stop"}]}).encode())
        result = generate(["test"], "使用中文", {"endpoint": "https://text.example/v1", "model": "text-model", "apiKey": "test"}, opener)
        self.assertEqual(result, ["测试"])

    def test_bad_count_is_rejected_without_file_changes(self):
        response = {"choices": [{"message": {"content": '{"names":[]}'}}]}
        with self.assertRaises(AiError):
            generate(["test"], "中文", {"endpoint": "https://example.com", "model": "text", "apiKey": "test"},
                     lambda *a, **k: io.BytesIO(json.dumps(response).encode()))

    def test_resident_protocol_has_correct_identity_and_data_directory(self):
        events, output = [], io.StringIO()
        messages = [{"id": 1, "method": "initialize", "params": {"dataDir": "data", "settings": {}}},
                    {"id": 2, "method": "query"}, {"id": 3, "method": "shutdown"}]
        rename_serve(io.StringIO("\n".join(json.dumps(m) for m in messages)), output, events.append)
        self.assertEqual(json.loads(output.getvalue().splitlines()[0])["result"]["name"], "day.rename")
        self.assertIn(("data_dir", "data"), events)


if __name__ == "__main__":
    unittest.main()
