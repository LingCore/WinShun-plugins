"""Windows Snipping Tool via Win+Shift+S; only accept a newly copied image."""
import ctypes as c
from ctypes import wintypes as w
import threading
import time

from PIL import Image, ImageGrab


class MOUSEINPUT(c.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
                ("dwFlags", w.DWORD), ("time", w.DWORD), ("extra", c.c_size_t)]


class KEYBDINPUT(c.Structure):
    _fields_ = [("vk", w.WORD), ("scan", w.WORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("extra", c.c_size_t)]


class HARDWAREINPUT(c.Structure):
    _fields_ = [("msg", w.DWORD), ("low", w.WORD), ("high", w.WORD)]


class INPUTUNION(c.Union):
    _fields_ = [("mouse", MOUSEINPUT), ("keyboard", KEYBDINPUT), ("hardware", HARDWAREINPUT)]


class INPUT(c.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", w.DWORD), ("data", INPUTUNION)]


class SystemApi:
    def __init__(self):
        self.user = c.WinDLL("user32", use_last_error=True)
        self.user.SendInput.argtypes = [w.UINT, c.POINTER(INPUT), c.c_int]
        self.user.SendInput.restype = w.UINT
        self.user.GetClipboardSequenceNumber.argtypes = []
        self.user.GetClipboardSequenceNumber.restype = w.DWORD
        self.user.GetAsyncKeyState.argtypes = [c.c_int]
        self.user.GetAsyncKeyState.restype = w.SHORT

    def sequence(self):
        return self.user.GetClipboardSequenceNumber()

    def escape_down(self):
        return bool(self.user.GetAsyncKeyState(0x1B) & 0x8000)

    def launch(self):
        # Correct INPUT union size matters: 40 bytes on x64, 28 on x86.
        keys = ((0x5B, 0), (0x10, 0), (0x53, 0), (0x53, 2), (0x10, 2), (0x5B, 2))
        inputs = (INPUT * len(keys))()
        for entry, (key, flags) in zip(inputs, keys):
            entry.type = 1
            entry.keyboard = KEYBDINPUT(key, 0, flags, 0, 0)
        if self.user.SendInput(len(inputs), inputs, c.sizeof(INPUT)) != len(inputs):
            # Release only our shortcut keys if injection was partially accepted.
            released = (INPUT * 3)()
            for entry, key in zip(released, (0x53, 0x10, 0x5B)):
                entry.type = 1
                entry.keyboard = KEYBDINPUT(key, 0, 2, 0, 0)
            self.user.SendInput(3, released, c.sizeof(INPUT))
            raise RuntimeError("无法调起系统截图，请确认 Windows 的 Win+Shift+S 快捷键可用。")


class SystemCapture:
    def __init__(self, api=None, grab=None, clock=None, stop=None):
        self.api = api or SystemApi()
        self.grab = grab or ImageGrab.grabclipboard
        self.clock = clock or time.monotonic
        self.stop = stop or threading.Event()

    def run(self, timeout=60):
        baseline = self.api.sequence()
        self.api.launch()
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            if self.stop.is_set() or self.api.escape_down():
                return None
            sequence = self.api.sequence()
            if sequence != baseline:
                try:
                    image = self.grab()
                    # Retrying on a racing clipboard change prevents mixing events.
                    if isinstance(image, Image.Image) and self.api.sequence() == sequence:
                        if image.width * image.height > 40_000_000:
                            raise ValueError("截图超过 4000 万像素，请缩小截图区域。")
                        return image.convert("RGB")
                    if not isinstance(image, Image.Image):
                        baseline = sequence  # Text/file-list changes are not screenshots.
                except (OSError, RuntimeError):
                    pass  # Clipboard may briefly be locked by Snipping Tool.
            if self.stop.wait(0.08):
                return None
        raise RuntimeError("等待系统截图超时。请检查 Win+Shift+S 是否可用，完成截图后需复制到剪贴板；Esc 可取消。")
