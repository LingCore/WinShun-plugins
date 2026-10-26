import os
"""UI state checks with a withdrawn Tk root; no network or desktop capture."""
from pathlib import Path
import sys
import tkinter as tk
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image
from main import OcrApp
import customtkinter as ctk


class UiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = OcrApp(self.root)

    def tearDown(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()

    def test_loading_does_not_upload(self):
        with patch("main.recognize") as api:
            self.app.set_image(Image.new("RGB", (40, 30)), "test")
            self.root.update_idletasks()
            self.assertEqual(self.app.image.size, (40, 30))
            api.assert_not_called()

    def test_canceled_result_never_replaces_text(self):
        self.app.text.insert("1.0", "保留我的编辑")
        self.app.set_busy(True)
        old_generation = self.app.generation
        self.app.cancel()
        self.app.events.put(("done", (old_generation, "迟到的结果", None)))
        self.app.poll()
        self.assertEqual(self.app.text.get("1.0", "end-1c"), "保留我的编辑")
        self.assertFalse(self.app.busy)

    def test_result_and_character_count(self):
        self.app.set_busy(True)
        self.app.events.put(("done", (self.app.generation, "你好 OCR", None)))
        self.app.poll()
        self.root.update()
        self.assertEqual(self.app.text.get("1.0", "end-1c"), "你好 OCR")
        self.assertEqual(self.app.count.get(), "6 字")
        self.assertFalse(self.app.busy)

    def test_error_remains_visible_after_dialog_closes(self):
        self.app.set_busy(True)
        with patch("main.messagebox.showerror"):
            self.app.events.put(("done", (self.app.generation, None, "接口错误 401：密钥无效")))
            self.app.poll()
        self.assertIn("401", self.app.status.get())
        self.assertIn("401", self.app.placeholder.cget("text"))
        self.assertFalse(self.app.busy)

    def check_automatic_result(self):
        self.app.worker.join(timeout=5)
        self.app.poll()
        self.assertEqual(self.app.text.get("1.0", "end-1c"), "自动识别结果")
        self.assertFalse(self.app.busy)

    def test_system_capture_automatically_recognizes(self):
        self.app.settings = {"endpoint": "https://example.com", "model": "vision", "apiKey": "test"}
        with patch("main.recognize", return_value="自动识别结果") as api, patch.object(self.app, "show"):
            self.app.events.put(("capture", (Image.new("RGB", (40, 30)), None)))
            self.app.poll()
            self.check_automatic_result()
            api.assert_called_once()

    def test_upload_automatically_recognizes(self):
        self.app.settings = {"endpoint": "https://example.com", "model": "vision", "apiKey": "test"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.png"
            Image.new("RGB", (40, 30)).save(path)
            with patch("main.filedialog.askopenfilename", return_value=str(path)), patch("main.recognize", return_value="自动识别结果") as api:
                self.app.upload()
                self.check_automatic_result()
                api.assert_called_once()

    def test_canceled_capture_does_not_recognize(self):
        with patch.object(self.app, "start_ocr") as start, patch.object(self.app, "show"):
            self.app.events.put(("capture", (None, None)))
            self.app.poll()
            start.assert_not_called()

    def test_auto_ocr_waits_for_canceled_worker_and_cancel_discards_it(self):
        from unittest.mock import MagicMock
        self.app.worker = MagicMock()
        self.app.worker.is_alive.return_value = True
        with patch.object(self.app, "start_ocr") as start:
            self.app.set_image(Image.new("RGB", (40, 30)), "test", auto_recognize=True)
            start.assert_not_called()
            self.assertTrue(self.app.auto_pending)
            self.app.worker.is_alive.return_value = False
            self.app.try_auto_ocr()
            start.assert_called_once()
            self.app.worker.is_alive.return_value = True
            self.app.set_image(Image.new("RGB", (40, 30)), "next", auto_recognize=True)
            self.app.cancel()
            self.app.worker.is_alive.return_value = False
            self.app.try_auto_ocr()
            self.assertFalse(self.app.auto_pending)
            start.assert_called_once()


@unittest.skipUnless(os.environ.get("WINSHUN_VISIBLE_LAYOUT_TEST") == "1", "Visible DPI test is opt-in")
class LayoutTests(unittest.TestCase):
    def test_controls_fit_small_window_at_common_dpi_scales(self):
        root = ctk.CTk()
        root.withdraw()
        app = OcrApp(root)
        try:
            root.deiconify()
            for scale in (1, 1.5, 2):
                with self.subTest(scale=scale):
                    ctk.set_widget_scaling(scale)
                    ctk.set_window_scaling(scale)
                    root.geometry("860x600")
                    root.update()
                    for widget in (app.recognize_button, app.cancel_button, app.capture_button, app.upload_button, app.status_label, app.text):
                        self.assertTrue(widget.winfo_ismapped())
                        self.assertGreater(widget.winfo_height(), 10)
                        x, y = widget.winfo_rootx() - root.winfo_rootx(), widget.winfo_rooty() - root.winfo_rooty()
                        self.assertGreaterEqual(x, 0)
                        self.assertGreaterEqual(y, 0)
                        self.assertLessEqual(x + widget.winfo_width(), root.winfo_width())
                        self.assertLessEqual(y + widget.winfo_height(), root.winfo_height())
        finally:
            ctk.set_widget_scaling(1)
            ctk.set_window_scaling(1)
            for callback in root.tk.call("after", "info"):
                root.after_cancel(callback)
            root.destroy()


if __name__ == "__main__":
    unittest.main()
