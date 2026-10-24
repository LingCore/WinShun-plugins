import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import customtkinter as ctk

PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN))
spec = importlib.util.spec_from_file_location("rename_ui", PLUGIN / "main.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class RenameUiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)
        self.root = ctk.CTk()
        self.root.withdraw()
        self.app = ui.RenameApp(self.root, native=False)
        self.app.journal = self.folder / "data" / "last.json"

    def tearDown(self):
        ui.cancel_callbacks(self.root)
        self.root.destroy()
        self.directory.cleanup()

    def add(self, name):
        path = self.folder / name
        path.write_text(name, encoding="utf-8")
        self.app.add_paths([path])
        return path

    def test_preview_is_local_and_does_not_rename(self):
        path = self.add("old.txt")
        with patch.object(ui, "generate") as network:
            self.app.rules[0][0].set("old")
            self.app.rules[0][1].set("new")
            self.app.refresh()
            self.assertEqual(self.app.plan[0].target.name, "new.txt")
            self.assertTrue(path.exists())
            self.assertFalse((self.folder / "new.txt").exists())
            network.assert_not_called()

    def test_execute_once_and_undo_with_same_file_content(self):
        path = self.add("old.txt")
        self.app.mode.set("插入内容")
        self.app.insert_text.set("new-")
        self.app.apply_names()
        self.assertEqual((self.folder / "new-old.txt").read_text(), "old.txt")
        self.assertFalse(path.exists())
        self.assertFalse(any(i.changed for i in self.app.plan))
        self.app.undo()
        self.assertEqual(path.read_text(), "old.txt")

    def test_natural_and_insertion_sort(self):
        self.add("file10.txt")
        self.add("file2.txt")
        self.assertEqual([p.name for p in self.app.paths], ["file2.txt", "file10.txt"])
        self.app.order.set("按添加顺序")
        self.assertEqual([p.name for p in self.app.paths], ["file10.txt", "file2.txt"])

    def test_manual_paste_fills_down_without_renaming_files(self):
        paths = [self.add("a.txt"), self.add("b.txt"), self.add("c.txt")]
        self.app.select_mode("手动编辑")
        self.app.refresh()
        self.app.tree.selection_set("1")
        self.app.paste_names("新的乙.txt\r\n新的丙.txt\r\n")
        self.assertEqual([i.target.name for i in self.app.plan], ["a.txt", "新的乙.txt", "新的丙.txt"])
        self.assertTrue(all(p.exists() for p in paths))
        self.app.paste_names("1.txt\n2.txt\n3.txt\n4.txt")
        self.assertTrue(all(p.exists() for p in paths))

    def test_reference_insert_and_number_options_reach_preview(self):
        self.add("photo.txt")
        self.app.select_mode("插入内容")
        self.app.insert_kind.set("序号")
        self.app.number_type.set("中文小写数字")
        self.app.insert_after.set("_")
        self.app.switch_insert()
        self.app.refresh()
        self.assertEqual(self.app.plan[0].target.name, "一_photo.txt")
        self.app.select_mode("自动编号")
        self.app.number_layout.set("替换原名")
        self.app.number_type.set("英文大写字母")
        self.app.number_before.set("报告_")
        self.app.number_after.set("")
        self.app.refresh()
        self.assertEqual(self.app.plan[0].target.name, "报告_A.txt")

    def test_metadata_date_format_prefix_suffix_preserve_original(self):
        original = self.add("报告.PDF")
        self.app.select_mode("插入内容")
        self.app.insert_kind.set("文件信息")
        self.app.info.set("创建日期")
        self.app.where.set("末尾")
        self.app.insert_before.set("_归档_")
        self.app.insert_after.set("_原件")
        self.app.date_format.set("YYYY-MM-DD_HH-mm-ss")
        self.app.switch_insert()
        self.app.refresh()
        self.assertRegex(self.app.plan[0].target.name, r"^报告_归档_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_原件\.PDF$")
        self.assertEqual(original.read_text(encoding="utf-8"), "报告.PDF")

    def test_ai_generates_preview_without_mutating_files(self):
        path = self.add("old.txt")
        self.app.mode.set("智能重命名")
        self.app.switch_mode()
        self.app.ai_instruction.insert(0, "使用中文")
        self.app.settings = {"endpoint": "https://example.com", "model": "text", "apiKey": "test"}
        with patch.object(ui, "generate", return_value=["新名字"]) as network:
            self.app.generate_ai()
            self.app.worker.join(timeout=5)
            self.app.poll()
        self.assertEqual(self.app.plan[0].target.name, "新名字.txt")
        self.assertTrue(path.exists())
        network.assert_called_once()

    @unittest.skipUnless(os.environ.get("WINSHUN_VISIBLE_LAYOUT_TEST") == "1", "Visible DPI test is opt-in to avoid disturbing the desktop")
    def test_footer_fits_minimum_window_at_common_scaling(self):
        self.root.deiconify()
        try:
            for scale in (1, 1.5, 2):
                with self.subTest(scale=scale):
                    ctk.set_widget_scaling(scale)
                    ctk.set_window_scaling(scale)
                    self.root.geometry("940x620")
                    self.root.update()
                    import tkinter as tk
                    settled = tk.BooleanVar(value=False)
                    self.root.after(500, lambda: (self.root.deiconify(), self.root.geometry("940x620"), settled.set(True)))
                    self.root.wait_variable(settled)
                    self.root.update()
                    for widget in (self.app.execute_button, self.app.undo_button, self.app.tree, self.app.status_label):
                        self.assertTrue(widget.winfo_ismapped(), str(widget))
                        self.assertGreater(widget.winfo_height(), 8)
                        self.assertLessEqual(widget.winfo_rootx() - self.root.winfo_rootx() + widget.winfo_width(), self.root.winfo_width())
                        self.assertLessEqual(widget.winfo_rooty() - self.root.winfo_rooty() + widget.winfo_height(), self.root.winfo_height())
                    for mode in ui.MODES:
                        self.app.mode.set(mode)
                        self.app.switch_mode()
                        self.root.update()
                        self.assertTrue(self.app.pages[mode].winfo_ismapped())
        finally:
            ctk.set_widget_scaling(1)
            ctk.set_window_scaling(1)


if __name__ == "__main__":
    unittest.main()
