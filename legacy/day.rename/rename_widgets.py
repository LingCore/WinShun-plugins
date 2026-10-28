import tkinter as tk
import customtkinter as ctk


class FlatEntry(ctk.CTkFrame):
    """Quiet, labelled field with a single bottom rule, like the reference UI."""
    def __init__(self, parent, variable=None, caption="", width=160):
        super().__init__(parent, width=width, height=60, corner_radius=5, fg_color="#F0F2F5")
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.value = variable if variable is not None else tk.StringVar(master=self)
        self.focused = False
        self.caption = ctk.CTkLabel(self, text=caption, height=22, anchor="w", text_color="#778293",
                                   font=("Microsoft YaHei UI", 14))
        self.field = ctk.CTkEntry(self, textvariable=self.value, height=30, width=20, corner_radius=0,
                                 border_width=0, fg_color="#F0F2F5", text_color="#283445",
                                 font=("Microsoft YaHei UI", 14))
        self.field.grid(row=0, column=0, sticky="ew", padx=12, pady=(23, 6))
        self.line = ctk.CTkFrame(self, height=1, corner_radius=0, fg_color="#ADB7C6")
        self.line.place(relx=0, rely=1, relwidth=1, anchor="sw")
        self.field.bind("<FocusIn>", lambda _: self.focus_changed(True))
        self.field.bind("<FocusOut>", lambda _: self.focus_changed(False))
        self.caption.bind("<Button-1>", lambda _: self.field.focus_set())
        self.trace_id = self.value.trace_add("write", self.update_caption)
        self.update_caption()

    def focus_changed(self, focused):
        self.focused = focused
        self.line.configure(fg_color="#586ADB" if focused else "#ADB7C6")
        self.update_caption()

    def update_caption(self, *_):
        floating = self.focused or bool(self.value.get())
        self.caption.configure(font=("Microsoft YaHei UI", 11 if floating else 14), height=17 if floating else 24)
        self.caption.place(x=14, y=5 if floating else 17)
        self.caption.lift()

    def destroy(self):
        self.value.trace_remove("write", self.trace_id)
        super().destroy()

    def get(self):
        return self.field.get()

    def insert(self, index, text):
        self.field.insert(index, text)

    def configure(self, require_redraw=False, **kwargs):
        if "show" in kwargs:
            self.field.configure(show=kwargs.pop("show"))
        super().configure(require_redraw=require_redraw, **kwargs)


class CleanTextbox(ctk.CTkTextbox):
    def destroy(self):
        owned = set(getattr(self, "_tclCommands", ()) or ())
        for callback in self.tk.call("after", "info"):
            script = self.tk.call("after", "info", callback)[0]
            if self.tk.splitlist(script)[0] in owned:
                self.after_cancel(callback)
        super().destroy()


class LabeledMenu(ctk.CTkFrame):
    """Dropdown aligned with the adjacent 60px text fields."""
    def __init__(self, parent, values, variable, caption, command=None):
        super().__init__(parent, height=60, corner_radius=5, fg_color="#F0F2F5")
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=caption, anchor="w", height=17, text_color="#778293",
                     font=("Microsoft YaHei UI", 11)).grid(row=0, column=0, sticky="ew", padx=14, pady=(5, 0))
        ctk.CTkOptionMenu(self, values=values, variable=variable, command=command, width=60,
                     height=30, corner_radius=0, fg_color="#F0F2F5", button_color="#F0F2F5",
                     button_hover_color="#E3E7EE", dropdown_fg_color="#FFFFFF", text_color="#283445",
                     dropdown_text_color="#283445", font=("Microsoft YaHei UI", 14),
                     dropdown_font=("Microsoft YaHei UI", 13)).grid(row=1, column=0, sticky="ew", padx=6)
        ctk.CTkFrame(self, height=1, corner_radius=0, fg_color="#ADB7C6").place(relx=0, rely=1, relwidth=1, anchor="sw")


class PromptBox(CleanTextbox):
    def __init__(self, parent):
        super().__init__(parent, height=80, corner_radius=0, border_width=0, fg_color="#FFFFFF",
                         text_color="#283445", font=("Microsoft YaHei UI", 14), wrap="word")
        self.hint = ctk.CTkLabel(self, text="用一句话描述命名规则，例如：中文转英文、保留日期、统一文件标题…",
                                font=("Microsoft YaHei UI", 13), text_color="#778293", anchor="nw", wraplength=760)
        self.hint.place(x=9, y=8)
        self.hint.bind("<Button-1>", lambda _: self.focus_set())
        self.bind("<KeyRelease>", lambda _: self.update_hint())

    def update_hint(self):
        if self.get():
            self.hint.place_forget()
        else:
            self.hint.place(x=9, y=8)

    def get(self, *args):
        return super().get(*(args or ("1.0", "end-1c")))

    def insert(self, index, text, *args):
        super().insert("1.0" if index == 0 else index, text, *args)
        self.update_hint()
