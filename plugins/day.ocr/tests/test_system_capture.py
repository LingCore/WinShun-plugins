"""System capture lifecycle with synthetic clipboard contents; no live shortcut."""
import ctypes
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image
from system_capture import SystemApi, SystemCapture, INPUT


class CaptureTests(unittest.TestCase):
    def capture(self, sequences, image):
        api = MagicMock()
        api.sequence.side_effect = sequences
        api.escape_down.return_value = False
        stop = MagicMock()
        stop.is_set.return_value = False
        stop.wait.return_value = False
        capture = SystemCapture(api, MagicMock(return_value=image), stop=stop)
        return capture, api

    def test_new_image_keeps_exact_pixels(self):
        image = Image.new("RGB", (3840, 2160), "white")
        image.putpixel((1500, 600), (10, 20, 30))
        capture, api = self.capture([10, 10, 11, 11], image)
        result = capture.run()
        self.assertEqual(result.size, (3840, 2160))
        self.assertEqual(result.getpixel((1500, 600)), (10, 20, 30))
        api.launch.assert_called_once()
        capture.grab.assert_called_once()

    def test_old_clipboard_image_is_never_read(self):
        capture, api = self.capture([10, 10], Image.new("RGB", (1, 1)))
        api.escape_down.side_effect = [False, True]
        self.assertIsNone(capture.run())
        capture.grab.assert_not_called()

    def test_file_list_is_not_treated_as_image(self):
        capture, api = self.capture([10, 11], ["C:/private.png"])
        api.escape_down.side_effect = [False, True]
        self.assertIsNone(capture.run())

    def test_locked_clipboard_is_retried(self):
        capture, api = self.capture([10, 11, 11, 11], None)
        capture.grab.side_effect = [OSError("locked"), Image.new("RGB", (40, 30))]
        self.assertEqual(capture.run().size, (40, 30))

    def test_clipboard_race_is_retried(self):
        capture, api = self.capture([10, 11, 12, 12, 12], None)
        capture.grab.side_effect = [Image.new("RGB", (1, 1)), Image.new("RGB", (40, 30))]
        self.assertEqual(capture.run().size, (40, 30))

    def test_shutdown_cancels_and_timeout_is_visible(self):
        capture, api = self.capture([10], None)
        capture.stop = threading.Event()
        capture.stop.set()
        self.assertIsNone(capture.run())
        capture, api = self.capture([10, 10], None)
        capture.clock = MagicMock(side_effect=[0, 1, 61])
        with self.assertRaisesRegex(RuntimeError, "超时"):
            capture.run()

    def test_pointer_sized_bindings_and_shortcut_key_releases(self):
        api = SystemApi()
        self.assertEqual(ctypes.sizeof(INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
        api.user = MagicMock()
        def send(count, inputs, size):
            self.assertEqual(count, 6)
            self.assertEqual(size, ctypes.sizeof(INPUT))
            self.assertEqual([(x.keyboard.vk, x.keyboard.flags) for x in inputs],
                             [(0x5B, 0), (0x10, 0), (0x53, 0), (0x53, 2), (0x10, 2), (0x5B, 2)])
            return count
        api.user.SendInput.side_effect = send
        api.launch()


if __name__ == "__main__":
    unittest.main()
