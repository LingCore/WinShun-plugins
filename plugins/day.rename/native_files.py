"""Explorer file paste and WM_DROPFILES without extra runtimes or subprocesses."""
import ctypes as c
from ctypes import wintypes as w


class NativeFiles:
    def __init__(self):
        self.u = c.WinDLL("user32", use_last_error=True)
        self.s = c.WinDLL("shell32", use_last_error=True)
        self.s.DragQueryFileW.argtypes = [w.HANDLE, w.UINT, w.LPWSTR, w.UINT]
        self.s.DragQueryFileW.restype = w.UINT
        self.s.DragFinish.argtypes = [w.HANDLE]
        self.s.DragFinish.restype = None
        self.s.DragAcceptFiles.argtypes = [w.HWND, w.BOOL]
        self.s.DragAcceptFiles.restype = None
        self.u.OpenClipboard.argtypes = [w.HWND]
        self.u.OpenClipboard.restype = w.BOOL
        self.u.CloseClipboard.argtypes = []
        self.u.CloseClipboard.restype = w.BOOL
        self.u.GetClipboardData.argtypes = [w.UINT]
        self.u.GetClipboardData.restype = w.HANDLE
        self.u.GetAncestor.argtypes = [w.HWND, w.UINT]
        self.u.GetAncestor.restype = w.HWND
        self.proc_type = c.WINFUNCTYPE(c.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        self.set_proc = self.u.SetWindowLongPtrW if c.sizeof(c.c_void_p) == 8 else self.u.SetWindowLongW
        self.set_proc.argtypes = [w.HWND, c.c_int, c.c_void_p]
        self.set_proc.restype = c.c_void_p
        self.u.CallWindowProcW.argtypes = [c.c_void_p, w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        self.u.CallWindowProcW.restype = c.c_ssize_t
        self.hwnd = self.old_proc = self.callback = None

    def paths(self, handle):
        count = self.s.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
        if count > 5000:
            raise ValueError("每批最多接收 5000 个文件或文件夹。")
        result = []
        for index in range(count):
            size = self.s.DragQueryFileW(handle, index, None, 0)
            buffer = c.create_unicode_buffer(size + 1)
            self.s.DragQueryFileW(handle, index, buffer, size + 1)
            result.append(buffer.value)
        return result

    def paste(self):
        if not self.u.OpenClipboard(None):
            raise RuntimeError("剪贴板正被占用，请稍后再试。")
        try:
            handle = self.u.GetClipboardData(15)  # CF_HDROP, not arbitrary clipboard text.
            return self.paths(handle) if handle else []
        finally:
            self.u.CloseClipboard()

    def paste_text(self):
        if not self.u.OpenClipboard(None):
            raise RuntimeError("剪贴板正被占用，请稍后再试。")
        try:
            handle = self.u.GetClipboardData(13)  # CF_UNICODETEXT; only on explicit manual paste.
            if not handle:
                return ""
            kernel = c.WinDLL("kernel32", use_last_error=True)
            kernel.GlobalLock.argtypes = [w.HANDLE]
            kernel.GlobalLock.restype = c.c_void_p
            kernel.GlobalUnlock.argtypes = [w.HANDLE]
            kernel.GlobalUnlock.restype = w.BOOL
            kernel.GlobalSize.argtypes = [w.HANDLE]
            kernel.GlobalSize.restype = c.c_size_t
            size = kernel.GlobalSize(handle)
            if not 0 < size <= 2 * 1024 * 1024:
                raise ValueError("粘贴文本过大，每次请控制在 2 MiB 内。")
            pointer = kernel.GlobalLock(handle)
            if not pointer:
                raise RuntimeError("无法读取剪贴板文本")
            try:
                return c.string_at(pointer, size).decode("utf-16-le").split("\0", 1)[0]
            finally:
                kernel.GlobalUnlock(handle)
        finally:
            self.u.CloseClipboard()

    def attach(self, root, post):
        root.update_idletasks()
        self.hwnd = self.u.GetAncestor(root.winfo_id(), 2)
        def callback(hwnd, message, wp, lp):
            if message == 0x233:
                try:
                    post(("files", self.paths(wp)))
                except Exception as exc:
                    post(("error", str(exc)))
                finally:
                    self.s.DragFinish(wp)
                return 0
            return self.u.CallWindowProcW(self.old_proc, hwnd, message, wp, lp)
        self.callback = self.proc_type(callback)
        c.set_last_error(0)
        self.old_proc = self.set_proc(self.hwnd, -4, c.cast(self.callback, c.c_void_p))
        if not self.old_proc:
            raise c.WinError(c.get_last_error())
        self.s.DragAcceptFiles(self.hwnd, True)

    def detach(self):
        if self.hwnd and self.old_proc:
            self.s.DragAcceptFiles(self.hwnd, False)
            self.set_proc(self.hwnd, -4, self.old_proc)
            self.old_proc = None
