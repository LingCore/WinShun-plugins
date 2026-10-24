"""OCR Studio for WinShun: one resident process, Tk UI, background HTTP worker."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import warnings

try:
    from PIL import Image, ImageOps, ImageTk
    import customtkinter as ctk
except ImportError:
    # Valid protocol responses still tell the user how to repair the dependency.
    if "--standalone" in sys.argv:
        ctypes.windll.user32.MessageBoxW(0, "请为 WinShun 使用的 Python 安装依赖：python -m pip install Pillow customtkinter", "OCR Studio 缺少依赖", 0)
    else:
        for line in sys.stdin:
            try:
                msg = json.loads(line)
                result = {"protocolVersion": "1", "name": "day.ocr"} if msg.get("method") == "initialize" else {"items": [{"id": "dependency", "title": "OCR Studio 需要界面与图片组件", "subtitle": "为 WinShun 使用的 Python 执行：python -m pip install Pillow customtkinter", "valid": False}]}
                if "id" in msg:
                    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)
                if msg.get("method") == "shutdown":
                    break
            except ValueError:
                pass
    raise SystemExit(1)

from ocr_api import DEFAULT_ENDPOINT, DEFAULT_MODEL, OcrError, endpoint_url, image_png, recognize
from protocol import serve
from system_capture import SystemCapture

BG = "#F4F5F7"
PANEL = "#FFFFFF"
INK = "#22242B"
MUTED = "#9398A5"
BLUE = "#5465E8"


def dpi_awareness():
    if os.name == "nt":
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            ctypes.windll.shcore.SetProcessDpiAwareness(2)


class OcrApp:
    def __init__(self, root, standalone=False):
        self.root = root
        self.standalone = standalone
        self.events = queue.Queue()
        self.settings = {"endpoint": DEFAULT_ENDPOINT, "model": DEFAULT_MODEL}
        self.image = None
        self.photo = None
        self.busy = False
        self.auto_pending = False
        self.capture_active = False
        self.capture_stop = threading.Event()
        self.generation = 0
        self.zoom = 1.0
        self.settings_window = None
        self.root.title("OCR Studio")
        self.root.geometry("1040x720")
        self.root.minsize(860, 600)
        if isinstance(self.root, ctk.CTk):
            self.root.configure(fg_color=BG)
        else:
            self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.option_add("*Font", ("Microsoft YaHei UI", 10))
        self.configure_styles()
        self.build()
        self.root.bind("<Control-o>", lambda _: self.upload())
        self.root.bind("<Control-Return>", lambda _: self.start_ocr())
        self.root.after(60, self.poll)

    def configure_styles(self):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

    def label(self, parent, text, size=10, color=INK, bg=PANEL, bold=False, **kw):
        return tk.Label(parent, text=text, font=("Microsoft YaHei UI", size, "bold" if bold else "normal"), fg=color, bg=bg, **kw)

    def button(self, parent, text, command, primary=False, width=100):
        return ctk.CTkButton(parent, text=text, command=command, width=width, height=38,
                             corner_radius=9, border_width=0 if primary else 1,
                             border_color="#E6E8EF", fg_color=BLUE if primary else PANEL,
                             hover_color="#4656D1" if primary else "#F1F3F9",
                             text_color="white" if primary else "#535966",
                             font=("Microsoft YaHei UI", 12, "bold" if primary else "normal"))

    def card(self, parent, color=PANEL):
        return ctk.CTkFrame(parent, fg_color=color, corner_radius=14, border_width=1, border_color="#E5E7ED")

    def build(self):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)
        header = tk.Frame(self.root, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=26, pady=(22, 20))
        logo = ctk.CTkFrame(header, width=42, height=42, corner_radius=11, fg_color=BLUE)
        logo.pack(side="left", padx=(0, 12))
        logo.pack_propagate(False)
        ctk.CTkLabel(logo, text="OCR", font=("Segoe UI", 12, "bold"), text_color="white").pack(expand=True)
        titles = tk.Frame(header, bg=BG)
        titles.pack(side="left")
        self.label(titles, "OCR Studio", 17, bg=BG, bold=True).pack(anchor="w")
        self.label(titles, "截取、识别，让文字触手可及", 9, MUTED, BG).pack(anchor="w", pady=(2, 0))
        self.model_label = tk.StringVar(value="尚未配置模型")
        model_badge = ctk.CTkFrame(header, fg_color="#EAEDF8", corner_radius=14, height=30)
        model_badge.pack(side="right")
        ctk.CTkLabel(model_badge, textvariable=self.model_label, text_color="#626FAD", font=("Microsoft YaHei UI", 11)).pack(padx=14, pady=3)

        body = tk.Frame(self.root, bg=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=26)
        body.grid_columnconfigure(0, weight=0, minsize=290)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        left = tk.Frame(body, bg=BG, width=290)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(0, weight=1)
        preview = self.card(left, "#F9FAFC")
        preview.grid(row=0, column=0, sticky="nsew")
        top = tk.Frame(preview, bg="#F9FAFC")
        top.pack(fill="x", padx=18, pady=(17, 4))
        self.label(top, "图片预览", 10, "#6B7281", "#F9FAFC").pack(side="left")
        self.canvas = tk.Canvas(preview, bg="#F9FAFC", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=12)
        self.canvas.bind("<Configure>", lambda _: self.render_image())
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<ButtonPress-1>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B1-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.canvas.bind("<Double-Button-1>", lambda _: self.reset_zoom())
        self.image_info = tk.StringVar(value="PNG · JPG · WebP · GIF")
        self.label(preview, "", 9, "#A4A9B5", "#F9FAFC", textvariable=self.image_info, wraplength=260).pack(pady=(0, 16))

        controls = self.card(left)
        controls.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        buttons = tk.Frame(controls, bg=PANEL)
        buttons.pack(fill="x", padx=14, pady=(14, 12))
        self.capture_button = self.button(buttons, "系统截图", self.screenshot, width=118)
        self.capture_button.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.upload_button = self.button(buttons, "上传图片", self.upload, width=118)
        self.upload_button.pack(side="left", fill="x", expand=True)
        self.label(controls, "滚轮缩放 · 拖动查看 · 双击复位", 8, MUTED).pack(pady=(0, 14))

        right = self.card(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)
        title = tk.Frame(right, bg=PANEL)
        title.grid(row=0, column=0, sticky="ew", padx=23, pady=(21, 16))
        self.label(title, "识别结果", 12, bold=True).pack(side="left")
        self.count = tk.StringVar(value="0 字")
        self.label(title, "", 9, MUTED, textvariable=self.count).pack(side="right")
        tk.Frame(right, bg="#F0F1F5", height=1).grid(row=1, column=0, sticky="ew", padx=23)
        editor = tk.Frame(right, bg=PANEL)
        editor.grid(row=2, column=0, sticky="nsew", padx=(23, 14), pady=22)
        self.text = tk.Text(editor, wrap="word", undo=True, relief="flat", borderwidth=0,
                            bg=PANEL, fg=INK, insertbackground=BLUE, selectbackground="#E3E6FC",
                            font=("Microsoft YaHei UI", 11), spacing1=3, spacing3=7, padx=0, pady=0)
        scroll = ctk.CTkScrollbar(editor, command=self.text.yview, width=12, fg_color=PANEL, button_color="#E4E6ED", button_hover_color="#CDD2DF")
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.bind("<<Modified>>", self.text_changed)
        self.text.bind("<Control-a>", self.select_all)
        self.placeholder = self.label(self.text, "识别结果将在这里呈现", 11, "#AFB3BF", justify="left")
        self.placeholder.place(x=0, y=6)
        self.placeholder.bind("<Button-1>", lambda _: self.text.focus_set())

        tk.Frame(right, bg="#F0F1F5", height=1).grid(row=3, column=0, sticky="ew", padx=23)
        toolbar = tk.Frame(right, bg=PANEL)
        toolbar.grid(row=4, column=0, sticky="ew", padx=21, pady=17)
        self.recognize_button = self.button(toolbar, "开始识别", self.start_ocr, primary=True, width=116)
        self.recognize_button.pack(side="left")
        self.cancel_button = self.button(toolbar, "取消", self.cancel, width=56)
        self.cancel_button.configure(state="disabled")
        self.cancel_button.pack(side="left", padx=8)
        self.button(toolbar, "复制全文", self.copy, width=94).pack(side="right")
        self.button(toolbar, "清空", self.clear, width=56).pack(side="right", padx=8)

        footer = tk.Frame(self.root, bg=BG)
        footer.grid(row=2, column=0, sticky="ew", padx=26, pady=(14, 17))
        ctk.CTkButton(footer, text="设置", command=self.open_settings, width=54, height=27,
                      fg_color="transparent", hover_color="#E8EBF2", text_color="#737B8C",
                      font=("Microsoft YaHei UI", 11)).pack(side="left")
        self.status = tk.StringVar(value="就绪")
        self.status_label = self.label(footer, "", 9, MUTED, BG, textvariable=self.status)
        self.status_label.pack(side="left", padx=10)
        self.label(footer, "截图或上传后自动识别", 8, "#A4A9B5", BG).pack(side="right")

    def text_changed(self, _=None):
        if not self.text.edit_modified():
            return
        value = self.text.get("1.0", "end-1c")
        self.count.set(f"{len(value)} 字")
        if value:
            self.placeholder.place_forget()
        else:
            self.placeholder.place(x=0, y=6)
        self.text.edit_modified(False)

    def select_all(self, _):
        self.text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def show(self):
        if self.capture_active:
            return
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(150, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def close(self):
        self.capture_stop.set()
        self.cancel(quiet=True)
        if self.standalone:
            self.root.destroy()
        else:
            self.root.withdraw()

    def poll(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "show":
                    self.show()
                elif event == "settings":
                    self.settings = {"endpoint": DEFAULT_ENDPOINT, "model": DEFAULT_MODEL, **value}
                    self.model_label.set(self.settings.get("model") or "尚未配置模型")
                elif event == "quit":
                    self.capture_stop.set()
                    self.root.destroy()
                    return
                elif event == "capture":
                    self.capture_active = False
                    self.show()
                    image, error = value
                    if error:
                        self.status.set("截图失败")
                        messagebox.showerror("截图失败", error, parent=self.root)
                    elif image is not None:
                        self.set_image(image, "系统截图", auto_recognize=True)
                    else:
                        self.status.set("已取消截图")
                elif event == "done":
                    generation, text, error = value
                    if generation != self.generation:
                        continue
                    self.set_busy(False)
                    if error:
                        self.status.set("识别失败 · " + error)
                        if not self.text.get("1.0", "end-1c"):
                            self.placeholder.configure(text="识别失败\n\n" + error,
                                                       wraplength=max(260, self.text.winfo_width() - 30))
                            self.placeholder.place(x=0, y=6)
                        messagebox.showerror("识别失败", error, parent=self.root)
                    else:
                        self.text.delete("1.0", "end")
                        self.text.insert("1.0", text)
                        self.text.edit_reset()
                        self.status.set("识别完成 · 结果可编辑或复制")
        except queue.Empty:
            pass
        self.try_auto_ocr()
        self.root.after(60, self.poll)

    def set_image(self, image, name, auto_recognize=False):
        self.cancel(quiet=True)
        self.image = image
        self.zoom = 1.0
        self.text.delete("1.0", "end")
        self.placeholder.configure(text="识别结果将在这里呈现")
        self.image_info.set(f"{name}  ·  {image.width} × {image.height}")
        self.render_image()
        self.status.set("图片已就绪 · 点击开始识别")
        if auto_recognize:
            self.auto_pending = True
            self.try_auto_ocr()

    def try_auto_ocr(self):
        if not self.auto_pending or self.busy or self.capture_active:
            return
        if getattr(self, "worker", None) and self.worker.is_alive():
            self.status.set("等待上一请求结束后自动识别…")
            return
        self.auto_pending = False
        self.start_ocr()

    def upload(self):
        path = filedialog.askopenfilename(parent=self.root, title="选择要识别的图片", filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.gif *.bmp"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            if os.path.getsize(path) > 32 * 1024 * 1024:
                raise OcrError("图片文件超过 32 MiB，请先缩小。")
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as source:
                    if source.width * source.height > 40_000_000:
                        raise OcrError("图片超过 4000 万像素，请先裁剪。")
                    image = ImageOps.exif_transpose(source).convert("RGB")
            self.set_image(image, os.path.basename(path), auto_recognize=True)
        except Exception:
            messagebox.showerror("无法打开图片", "图片无效、过大或无法读取。支持 PNG、JPG、WebP、GIF（首帧）和 BMP。", parent=self.root)

    def screenshot(self):
        if self.busy or self.capture_active:
            return
        self.capture_active = True
        self.capture_stop.clear()
        self.status.set("等待系统截图 · 框选后复制图片 · Esc 取消")
        self.root.withdraw()
        self.root.update_idletasks()

        def capture():
            try:
                image = SystemCapture(stop=self.capture_stop).run()
                event = image, None
            except Exception as exc:
                event = None, str(exc)
            self.events.put(("capture", event))

        # Let Windows own screen geometry and DPI; the clipboard image is not resized.
        self.root.after(300, lambda: threading.Thread(target=capture, daemon=True).start())

    def render_image(self):
        self.canvas.delete("all")
        width, height = max(self.canvas.winfo_width(), 10), max(self.canvas.winfo_height(), 10)
        if self.image is None:
            cx, cy = width // 2, height // 2 - 45
            self.canvas.create_rectangle(cx - 22, cy - 18, cx + 22, cy + 18, outline="#C4CAD8", width=2)
            self.canvas.create_oval(cx - 12, cy - 10, cx - 5, cy - 3, outline="#C4CAD8", width=2)
            self.canvas.create_line(cx - 21, cy + 13, cx - 4, cy - 1, cx + 5, cy + 7, cx + 13, cy, cx + 21, cy + 7, fill="#C4CAD8", width=2)
            self.canvas.create_text(width // 2, height // 2 - 45, text="", fill="#B9C8E2", font=("Segoe UI Symbol", 48))
            self.canvas.create_text(width // 2, height // 2 + 17, text="添加一张图片，开始识别", fill="#81899A", font=("Microsoft YaHei UI", 12))
            self.canvas.create_text(width // 2, height // 2 + 50, text="截取屏幕，或从电脑选择图片", fill=MUTED, justify="center", font=("Microsoft YaHei UI", 9))
            return
        factor = min((width - 20) / self.image.width, (height - 20) / self.image.height) * self.zoom
        # Bound preview dimensions independently of original upload resolution.
        factor = min(factor, 8192 / max(self.image.size))
        size = max(1, int(self.image.width * factor)), max(1, int(self.image.height * factor))
        self.photo = ImageTk.PhotoImage(self.image.resize(size, Image.Resampling.LANCZOS))
        self.canvas.create_image(max(width, size[0]) // 2, max(height, size[1]) // 2, image=self.photo)
        self.canvas.configure(scrollregion=(0, 0, max(width, size[0]), max(height, size[1])))
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def wheel(self, event):
        if self.image:
            self.zoom = max(0.5, min(8, self.zoom * (1.15 if event.delta > 0 else 1 / 1.15)))
            self.render_image()

    def reset_zoom(self):
        self.zoom = 1.0
        self.render_image()

    def set_busy(self, busy):
        self.busy = busy
        for button in (self.capture_button, self.upload_button, self.recognize_button):
            button.configure(state="disabled" if busy else "normal")
        self.cancel_button.configure(state="normal" if busy else "disabled")
        self.recognize_button.configure(text="识别中…" if busy else "开始识别")

    def cancel(self, quiet=False):
        self.auto_pending = False
        self.generation += 1
        if self.busy:
            self.set_busy(False)
            self.placeholder.configure(text="识别结果将在这里呈现")
            if not quiet:
                self.status.set("已取消等待 · 已发送的请求可能仍计费")

    def clear(self):
        self.cancel(quiet=True)
        self.text.delete("1.0", "end")
        self.placeholder.configure(text="识别结果将在这里呈现")
        self.status.set("结果已清空")

    def start_ocr(self):
        if self.busy:
            return
        if self.image is None:
            self.status.set("请先截图或上传图片")
            return
        if not all(str(self.settings.get(k) or "").strip() for k in ("apiKey", "endpoint", "model")):
            self.open_settings()
            self.status.set("请先配置 API 地址、模型名称和 API Key")
            return
        # Do not permit an unbounded number of canceled network workers.
        if getattr(self, "worker", None) and self.worker.is_alive():
            self.status.set("上一请求仍在结束，请稍后再试（最长 90 秒）")
            return
        try:
            host = endpoint_url(self.settings.get("endpoint"))
            png = image_png(self.image)
        except OcrError as exc:
            messagebox.showerror("无法识别", str(exc), parent=self.root)
            return
        self.generation += 1
        generation = self.generation
        settings = dict(self.settings)
        self.set_busy(True)
        if not self.text.get("1.0", "end-1c"):
            self.placeholder.configure(text="正在识别，请稍候…")
            self.placeholder.place(x=0, y=6)
        self.status.set("正在识别 · " + host.split("/")[2])

        def work():
            try:
                result = recognize(png, settings)
                event = generation, result, None
            except Exception as exc:
                event = generation, None, str(exc) if isinstance(exc, OcrError) else "识别失败，请检查接口设置后重试。"
            self.events.put(("done", event))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def copy(self):
        value = self.text.get("1.0", "end-1c")
        if not value:
            self.status.set("还没有可以复制的文字")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update_idletasks()
        self.status.set(f"已复制 {len(value)} 字")

    def open_settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        window = self.settings_window = ctk.CTkToplevel(self.root)
        window.title("模型连接")
        window.geometry("540x480")
        window.resizable(False, False)
        window.configure(fg_color=PANEL)
        window.transient(self.root)
        ctk.CTkLabel(window, text="连接你的视觉模型", font=("Microsoft YaHei UI", 20, "bold"), text_color=INK).pack(anchor="w", padx=28, pady=(24, 4))
        ctk.CTkLabel(window, text="支持 OpenAI Chat Completions 格式的图片输入接口", font=("Microsoft YaHei UI", 11), text_color=MUTED).pack(anchor="w", padx=28)
        entries = {}
        fields = (("endpoint", "API 地址", "https://your-provider.com/v1"),
                  ("model", "模型名称", "服务商提供的视觉模型 ID"),
                  ("apiKey", "API Key", "输入密钥"))
        for key, title, hint in fields:
            ctk.CTkLabel(window, text=title, font=("Microsoft YaHei UI", 12), text_color="#5D6474").pack(anchor="w", padx=28, pady=(14, 5))
            entry = ctk.CTkEntry(window, height=40, corner_radius=8, border_width=1, border_color="#E1E4EC", fg_color="#FAFBFD", text_color=INK, placeholder_text=hint, show="•" if key == "apiKey" else "")
            if self.settings.get(key):
                entry.insert(0, self.settings[key])
            entry.pack(fill="x", padx=28)
            entries[key] = entry
        ctk.CTkLabel(window, text="本次连接仅在内存中保留。永久保存请到 WinShun 插件设置。", font=("Microsoft YaHei UI", 10), text_color=MUTED).pack(anchor="w", padx=28, pady=(20, 16))

        def save():
            try:
                endpoint_url(entries["endpoint"].get())
                if not entries["model"].get().strip():
                    raise OcrError("请填写支持图片输入的模型名称。")
            except OcrError as exc:
                messagebox.showerror("配置无效", str(exc), parent=window)
                return
            self.settings.update({key: value.get().strip() for key, value in entries.items()})
            self.model_label.set(self.settings["model"])
            self.status.set("模型连接已更新")
            window.destroy()
            if self.image is not None:
                self.start_ocr()

        self.button(window, "应用配置", save, primary=True, width=116).pack(anchor="e", padx=28)



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--standalone", action="store_true", help="直接打开窗口，不连接 WinShun")
    parser.add_argument("--self-test", action="store_true", help="离线检查内置运行时，不显示窗口或联网")
    args = parser.parse_args()
    dpi_awareness()
    ctk.set_appearance_mode("light")
    root = ctk.CTk()
    if not args.standalone:
        root.withdraw()
    app = OcrApp(root, standalone=args.standalone)
    if args.self_test:
        from system_capture import SystemApi, INPUT
        SystemApi()
        assert ctypes.sizeof(INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
        test_image = Image.new("RGB", (40, 30), "white")
        app.set_image(test_image, "自检")
        root.update_idletasks()
        app.text.insert("1.0", "OCR 运行时自检")
        root.update()
        assert app.count.get() == "9 字"
        assert image_png(test_image).startswith(b"\x89PNG")
        assets = Path(ctk.__file__).parent / "assets"
        assert (assets / "themes" / "blue.json").is_file(), "缺少主题文件"
        assert (assets / "fonts" / "CustomTkinter_shapes_font.otf").is_file(), "缺少图标字体"
        result = {"ok": True, "frozen": bool(getattr(sys, "frozen", False)),
                  "python": sys.version.split()[0], "tcl": root.tk.call("info", "patchlevel"),
                  "executable": sys.executable, "ui": "CustomTkinter", "network_used": False}
        for callback in root.tk.call("after", "info"):
            root.after_cancel(callback)
        root.destroy()
        print(json.dumps(result, ensure_ascii=True), flush=True)
        return
    if not args.standalone:
        root.withdraw()
        # UTF-8 streams, no other output is ever written to stdout.
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        threading.Thread(target=serve, args=(sys.stdin, sys.stdout, app.events.put), daemon=True).start()
    root.mainloop()


if __name__ == "__main__":
    main()
