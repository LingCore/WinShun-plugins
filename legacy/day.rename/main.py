"""WinShun Batch Rename: local preview first, optional AI, explicit file mutation."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from ai_names import AiError, endpoint_url, generate
from native_files import NativeFiles
from rename_icons import icon
from rename_widgets import FlatEntry, PromptBox, CleanTextbox, LabeledMenu
from rename_protocol import serve
from rename_core import RenameError, execute, key, make_plan, natural_key, restore, split_name

BG, WHITE, INK, MUTED, ACCENT = "#F5F6F8", "#FCFDFE", "#283445", "#697586", "#586ADB"
MODES = {"查找替换": "replace", "智能重命名": "smart", "插入内容": "insert", "自动编号": "number", "手动编辑": "manual"}
NUMBER_TYPES = ["阿拉伯数字", "中文小写数字", "中文大写数字", "英文小写字母", "英文大写字母"]


def cancel_callbacks(root):
    owners = {}
    def visit(widget):
        for command in getattr(widget, "_tclCommands", ()) or ():
            owners[command] = widget
        for child in list(widget.children.values()):
            visit(child)
    visit(root)
    for callback in root.tk.call("after", "info"):
        script = root.tk.call("after", "info", callback)[0]
        command = root.tk.splitlist(script)[0]
        owners.get(command, root).after_cancel(callback)


class RenameApp:
    def __init__(self, root, standalone=False, native=True):
        ctk.set_appearance_mode("light")
        self.root, self.standalone = root, standalone
        self.paths, self.plan, self.manual, self.ai_preview = [], [], {}, None
        self.insertion = {}
        self.next_insertion = 0
        self.events = queue.Queue()
        self.settings = {}
        self.generation = 0
        self.busy = False
        self.pending = None
        self.native = None
        self.settings_window = None
        self.shown_once = False
        self.show_request = None
        self.journal = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "WinShun" / "plugins" / "day.rename.data" / "last-rename.json"
        self.root.title("批量重命名")
        self.root.geometry("1000x700")
        self.root.minsize(900, 620)
        self.root.configure(fg_color=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(3, weight=1)
        self.mode = tk.StringVar(value="查找替换")
        self.extension = tk.BooleanVar(value=False)
        self.ignore_case = tk.BooleanVar(value=False)
        self.regex = tk.BooleanVar(value=False)
        self.normalize = tk.BooleanVar(value=True)
        self.spaces = tk.BooleanVar(value=True)
        self.separators = tk.BooleanVar(value=False)
        self.remove_number = tk.BooleanVar(value=False)
        self.case = tk.StringVar(value="保持大小写")
        self.insert_text = tk.StringVar()
        self.insert_kind = tk.StringVar(value="文本")
        self.insert_before = tk.StringVar()
        self.insert_after = tk.StringVar()
        self.info = tk.StringVar(value="修改日期")
        self.date_format = tk.StringVar(value="YYYYMMDD")
        self.number_type = tk.StringVar(value="阿拉伯数字")
        self.number_before = tk.StringVar()
        self.number_after = tk.StringVar(value="_")
        self.number_layout = tk.StringVar(value="保留原名")
        self.smart_view = tk.StringVar(value="本地整理")
        self.model_caption = tk.StringVar(value="选择模型")
        self.where = tk.StringVar(value="开头")
        self.position = tk.StringVar(value="0")
        self.start = tk.StringVar(value="1")
        self.step = tk.StringVar(value="1")
        self.width = tk.StringVar(value="3")
        self.template = tk.StringVar(value="{n}_{name}")
        self.order = tk.StringVar(value="按名称升序")
        self.status = tk.StringVar(value="添加文件，预览新名称后执行")
        self.count = tk.StringVar(value="已选 0 个文件")
        self.rules = []
        self.build()
        for variable in (self.extension, self.ignore_case, self.regex, self.normalize, self.spaces,
                         self.separators, self.remove_number, self.case, self.insert_text, self.where,
                         self.position, self.start, self.step, self.width, self.template,
                         self.insert_before, self.insert_after, self.info, self.date_format,
                         self.number_type, self.number_before, self.number_after):
            variable.trace_add("write", self.changed)
        self.order.trace_add("write", self.sort_files)
        self.root.bind("<Control-v>", self.paste)
        self.root.bind("<Control-o>", lambda _: self.add_files())
        self.root.bind("<Delete>", self.delete_key)
        if native:
            self.native = NativeFiles()
            self.native.attach(root, self.events.put)
        self.root.after(70, self.poll)

    def label(self, parent, text, size=13, color=INK):
        return ctk.CTkLabel(parent, text=text, text_color=color, font=("Microsoft YaHei UI", size))

    def button(self, parent, text, command, primary=False, width=100):
        return ctk.CTkButton(parent, text=text, command=command, width=width, height=38,
                            corner_radius=8, border_width=0 if primary else 1,
                            border_color="#E7E9F0", fg_color=ACCENT if primary else WHITE,
                            hover_color="#5364D7" if primary else "#EBEDF5",
                            text_color="white" if primary else "#526074",
                            font=("Microsoft YaHei UI", 13))

    def entry(self, parent, variable=None, placeholder="", width=160):
        return FlatEntry(parent, variable, placeholder, width)

    def segmented(self, parent, values, variable, command):
        return ctk.CTkSegmentedButton(parent, values=values, variable=variable, command=command,
                   height=34, corner_radius=4, border_width=1, fg_color="#D3DAE5",
                   selected_color="#E3E8FA", selected_hover_color="#DBE2F8",
                   unselected_color=WHITE, unselected_hover_color="#F0F2F7",
                   text_color="#536177", font=("Microsoft YaHei UI", 13))

    def menu(self, parent, values, variable, width=150):
        return ctk.CTkOptionMenu(parent, values=values, variable=variable, width=width, height=38,
                   corner_radius=4, fg_color="#EFF0F2", button_color="#EFF0F2",
                   button_hover_color="#E5E7EC", dropdown_fg_color="#FFFFFF", dropdown_text_color=INK,
                   text_color="#455369", font=("Microsoft YaHei UI", 13), dropdown_font=("Microsoft YaHei UI", 13))

    def check(self, parent, text, variable):
        return ctk.CTkCheckBox(parent, text=text, variable=variable, checkbox_width=17,
                             checkbox_height=17, corner_radius=3, border_width=2,
                             text_color="#526074", fg_color=ACCENT, font=("Microsoft YaHei UI", 12))

    def build(self):
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(13, 10))
        brand = ctk.CTkFrame(header, width=28, height=28, corner_radius=7, fg_color=ACCENT)
        brand.pack(side="left", padx=(0, 9))
        brand.pack_propagate(False)
        ctk.CTkLabel(brand, text="", image=icon("manual", "#FFFFFF", 18)).pack(expand=True)
        ctk.CTkLabel(header, text="批量重命名", font=("Microsoft YaHei UI", 17, "bold"), text_color=INK).pack(side="left")
        badge = ctk.CTkFrame(header, fg_color="#EDEFF5", corner_radius=6)
        badge.pack(side="left", padx=14)
        self.label(badge, "pl / cmm", 11, "#697586").pack(padx=9, pady=2)
        ctk.CTkButton(header, text="AI 模型设置", command=self.open_settings, width=100, height=32,
                      fg_color="transparent", hover_color="#EDEFF6", text_color="#58667C",
                      font=("Microsoft YaHei UI", 12)).pack(side="right")
        self.tabs = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=0)
        self.tabs.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 0))
        self.tab_buttons, self.tab_lines = {}, {}
        for index, name in enumerate(MODES):
            self.tabs.grid_columnconfigure(index, weight=1, uniform="tabs")
            button = ctk.CTkButton(self.tabs, text=name, image=icon(MODES[name]), compound="left", height=42, corner_radius=7,
                        fg_color="transparent", hover_color="#ECEFF4", text_color="#657185",
                        font=("Microsoft YaHei UI", 13), command=lambda n=name: self.select_mode(n))
            button.grid(row=0, column=index, sticky="ew", padx=3)
            line = ctk.CTkFrame(self.tabs, height=1, fg_color=BG, corner_radius=0)
            line.grid(row=1, column=index, sticky="ew", padx=25)
            self.tab_buttons[name], self.tab_lines[name] = button, line
        self.controls = ctk.CTkFrame(self.root, fg_color=WHITE, corner_radius=0, height=234)
        self.controls.grid(row=2, column=0, sticky="ew", pady=(0, 0))
        self.controls.grid_propagate(False)
        self.controls.grid_columnconfigure(0, weight=1)
        self.pages = {}
        for name in MODES:
            frame = ctk.CTkFrame(self.controls, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew", padx=24, pady=(16, 6))
            self.pages[name] = frame
        self.controls.grid_rowconfigure(0, weight=1)
        self.build_replace(self.pages["查找替换"])
        self.build_smart(self.pages["智能重命名"])
        self.build_insert(self.pages["插入内容"])
        self.build_number(self.pages["自动编号"])
        self.build_manual(self.pages["手动编辑"])
        self.control_bottom = ctk.CTkFrame(self.controls, fg_color="transparent")
        self.control_bottom.grid(row=1, column=0, sticky="ew", padx=24, pady=(2, 14))
        self.check(self.control_bottom, "替换文件扩展名", self.extension).pack(side="left")
        self.control_hint = self.label(self.control_bottom, "名称预览不会修改文件", 12, MUTED)
        self.add_rule_button = self.button(self.control_bottom, "＋ 添加替换规则", self.add_rule, width=136)

        area = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0, border_width=0)
        area.grid(row=3, column=0, sticky="nsew")
        ctk.CTkFrame(area, height=1, corner_radius=0, fg_color="#DFE2E8").grid(row=0, column=0, columnspan=2, sticky="new")
        area.grid_columnconfigure(0, weight=1)
        area.grid_rowconfigure(0, weight=1)
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Rename.Treeview", background=WHITE, fieldbackground=WHITE, foreground=INK,
                        borderwidth=0, rowheight=42, font=("Microsoft YaHei UI", -14))
        style.configure("Rename.Treeview.Heading", background="#EDF0F5", foreground="#59677D",
                        relief="flat", font=("Microsoft YaHei UI", -13, "bold"))
        style.map("Rename.Treeview", background=[("selected", "#E7EBFE")], foreground=[("selected", INK)])
        self.tree = ttk.Treeview(area, columns=("old", "new", "state", "folder"), displaycolumns=("old", "new", "state"), show="headings", style="Rename.Treeview", selectmode="extended")
        for column, title, width in (("old", "原名称", 330), ("new", "新名称 · 执行前预览", 450), ("state", "检查", 160), ("folder", "所在位置", 230)):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, minwidth=70, stretch=True)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        self.scrollbar = ctk.CTkScrollbar(area, command=self.tree.yview, width=12, fg_color=BG, button_color="#D8DCE5")
        self.scrollbar.grid(row=0, column=1, sticky="ns", pady=12, padx=(0, 6))
        self.tree.configure(yscrollcommand=self.scrollbar.set)
        self.table_style = style
        ctk.ScalingTracker.add_widget(self.scale_table, self.root)
        self.scale_table(ctk.ScalingTracker.get_widget_scaling(self.root), 1)
        self.tree.tag_configure("error", foreground="#B03C4C", background="#FFF3F4")
        self.tree.tag_configure("change", foreground=INK, background="#F3F6FF")
        self.tree.tag_configure("unchanged", foreground="#697586")
        self.tree.bind("<Double-1>", self.edit_row)
        self.tree.bind("<<TreeviewSelect>>", self.row_selected)
        self.empty = ctk.CTkFrame(area, fg_color=BG, corner_radius=0)
        illustration = tk.Canvas(self.empty, width=55, height=46, bg=BG, highlightthickness=0)
        illustration.pack(pady=(0, 12))
        illustration.create_polygon(17, 4, 33, 4, 43, 14, 43, 41, 17, 41, fill="#D2D5DD", outline="")
        illustration.create_polygon(33, 4, 33, 14, 43, 14, fill=BG, outline="")
        self.label(self.empty, "拖放 / 粘贴文件(夹)到这里", 14, "#778293").pack()
        self.empty.place(relx=.5, rely=.5, anchor="center")
        self.empty.bind("<Button-1>", lambda _: self.add_files())

        footer = ctk.CTkFrame(self.root, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=18, pady=(10, 5))
        footer.grid_columnconfigure(0, weight=1)
        actions = ctk.CTkFrame(footer, fg_color="transparent")
        actions.grid(row=0, column=0, sticky="ew")
        for text, command, symbol, width in (("添加文件", self.add_files, "file", 92), ("文件夹", self.add_folder, "folder", 86),
                                              ("移除", self.remove_selected, "remove", 65), ("清空", self.clear_files, "clear", 65)):
            button = self.button(actions, text, command, width=width)
            button.configure(image=icon(symbol, "#697586", 16), border_width=0, fg_color="transparent")
            button.pack(side="left", padx=(0, 2))
        self.menu(actions, ["按名称升序", "按名称降序", "按添加顺序"], self.order, 122).pack(side="left", padx=7)
        self.execute_button = self.button(footer, "执行重命名", self.apply_names, True, 126)
        self.execute_button.configure(image=icon("play", "#FFFFFF", 15), fg_color="#7181EF", text_color_disabled="#A6ABB5")
        self.execute_button.grid(row=0, column=2, sticky="e")
        self.undo_button = self.button(footer, "撤销 / 恢复", self.undo, width=110)
        self.undo_button.configure(border_width=0, fg_color="transparent", image=icon("undo", "#8A909B", 15))
        self.undo_button.grid(row=0, column=1, sticky="e", padx=8)
        status_row = ctk.CTkFrame(self.root, fg_color="transparent")
        status_row.grid(row=5, column=0, sticky="ew", padx=25, pady=(0, 8))
        self.status_label = self.label(status_row, "", 12, MUTED)
        self.status_label.configure(textvariable=self.status)
        self.status_label.pack(side="left")
        self.count_label = self.label(status_row, "", 12, MUTED)
        self.count_label.configure(textvariable=self.count)
        self.count_label.pack(side="right")
        self.switch_mode()

    def build_replace(self, frame):
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        self.rule_area = ctk.CTkScrollableFrame(frame, fg_color=WHITE, height=100, scrollbar_button_color="#E6E8ED")
        self.rule_area.grid(row=0, column=0, columnspan=3, sticky="nsew", pady=(0, 12))
        self.rule_area.grid_columnconfigure(0, weight=1)
        self.rule_area.grid_columnconfigure(2, weight=1)
        self.add_rule()
        self.check(frame, "正则表达式", self.regex).grid(row=1, column=0, sticky="w")
        self.check(frame, "忽略大小写", self.ignore_case).grid(row=1, column=1, padx=12)

    def scale_table(self, widget_scale, _window_scale):
        # Match CTk text at the current monitor DPI; never change global scaling here.
        self.table_style.configure("Rename.Treeview", rowheight=round(42 * widget_scale),
                                   font=("Microsoft YaHei UI", -round(14 * widget_scale)))
        self.table_style.configure("Rename.Treeview.Heading", font=("Microsoft YaHei UI", -round(13 * widget_scale), "bold"))

    def add_rule(self):
        row = len(self.rules)
        find, replacement = tk.StringVar(), tk.StringVar()
        self.entry(self.rule_area, find, "查找").grid(row=row, column=0, sticky="ew", pady=4)
        self.label(self.rule_area, "→", 22, "#B6BAC4").grid(row=row, column=1, padx=20)
        self.entry(self.rule_area, replacement, "替换成").grid(row=row, column=2, sticky="ew", pady=4)
        self.rules.append((find, replacement))
        find.trace_add("write", self.changed)
        replacement.trace_add("write", self.changed)

    def build_smart(self, frame):
        self.segmented(frame, ["本地整理", "AI 命名"], self.smart_view, self.switch_smart).pack(anchor="w", pady=(0, 12))
        self.smart_local = ctk.CTkFrame(frame, fg_color="transparent")
        self.smart_ai = ctk.CTkFrame(frame, fg_color="transparent")
        checks = ctk.CTkFrame(self.smart_local, fg_color="transparent")
        checks.pack(fill="x", pady=(8, 14))
        for text, variable in (("整理空格", self.spaces), ("全角转半角", self.normalize), ("合并分隔符", self.separators), ("去掉开头编号", self.remove_number)):
            self.check(checks, text, variable).pack(side="left", padx=(0, 15))
        row = ctk.CTkFrame(self.smart_local, fg_color="transparent")
        row.pack(fill="x")
        self.menu(row, ["保持大小写", "全部小写", "全部大写", "单词首字母大写"], self.case, 160).pack(side="left")
        self.label(row, "本地处理，无需连接模型", 12, MUTED).pack(side="left", padx=16)
        composer = ctk.CTkFrame(self.smart_ai, fg_color="#FFFFFF", corner_radius=16, border_width=1, border_color="#E1E3E9")
        composer.pack(fill="x", padx=20)
        self.ai_instruction = PromptBox(composer)
        self.ai_instruction.pack(fill="x", padx=13, pady=(8, 0))
        row = ctk.CTkFrame(composer, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 10))
        ctk.CTkButton(row, textvariable=self.model_caption, text="选择模型", command=self.open_settings,
                      fg_color="transparent", hover_color="#F0F2F7", text_color="#858B98", width=160, height=28,
                      anchor="w", font=("Microsoft YaHei UI", 12)).pack(side="left")
        self.ai_button = self.button(row, "AI 生成预览", self.generate_ai, True, 122)
        self.ai_button.pack(side="right")
        self.smart_local.pack(fill="x")

    def switch_smart(self, _=None):
        self.smart_local.pack_forget()
        self.smart_ai.pack_forget()
        (self.smart_ai if self.smart_view.get() == "AI 命名" else self.smart_local).pack(fill="x")
        self.changed()

    def build_insert(self, frame):
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 20))
        self.label(row, "内容：", 13).pack(side="left", padx=(0, 7))
        self.segmented(row, ["文本", "序号", "文件信息"], self.insert_kind, self.switch_insert).pack(side="left")
        self.segmented(row, ["开头", "指定位置", "末尾"], self.where, self.switch_insert).pack(side="right")
        self.label(row, "位置：", 13).pack(side="right", padx=(0, 7))
        self.insert_fields = ctk.CTkFrame(frame, fg_color="transparent")
        self.insert_fields.pack(fill="x")
        self.position_row = ctk.CTkFrame(frame, fg_color="transparent")
        self.entry(self.position_row, self.position, "指定字符位置（从 0 开始）", 220).pack(side="left", pady=(8, 0))
        self.switch_insert(building=True)

    def switch_insert(self, _=None, building=False):
        for child in self.insert_fields.winfo_children():
            child.destroy()
        kind = self.insert_kind.get()
        if kind == "文本":
            self.entry(self.insert_fields, self.insert_text, "固定文本").pack(fill="x")
        else:
            self.insert_fields.grid_columnconfigure(0, weight=1, uniform="insert")
            self.insert_fields.grid_columnconfigure(1, weight=1, uniform="insert")
            self.insert_fields.grid_columnconfigure(2, weight=1, uniform="insert")
            self.entry(self.insert_fields, self.insert_before, kind + "前面字符").grid(row=0, column=0, sticky="ew", padx=(0, 10))
            LabeledMenu(self.insert_fields, NUMBER_TYPES if kind == "序号" else ["修改日期", "创建日期", "文件大小", "扩展名", "所在文件夹", "原文件名"],
                        self.number_type if kind == "序号" else self.info, "序号类型" if kind == "序号" else "文件信息",
                        command=self.switch_insert if kind == "文件信息" else None).grid(row=0, column=1, sticky="ew", padx=8)
            self.entry(self.insert_fields, self.insert_after, kind + "后面字符").grid(row=0, column=2, sticky="ew", padx=(10, 0))
            if kind == "序号":
                details = ctk.CTkFrame(self.insert_fields, fg_color="transparent")
                details.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(7, 0))
                for title, variable in (("开始序号", self.start), ("步长", self.step), ("补零位数", self.width)):
                    self.entry(details, variable, title, 110).pack(side="left", padx=(0, 12))
            else:
                details = ctk.CTkFrame(self.insert_fields, fg_color="transparent")
                details.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(9, 0))
                self.label(details, "将文件属性插入原名称，不改变文件内容", 12, MUTED).pack(side="left")
                if self.info.get() in ("创建日期", "修改日期"):
                    self.menu(details, ["YYYYMMDD", "YYYY-MM-DD", "YYYY-MM-DD_HH-mm-ss"], self.date_format, 205).pack(side="right")
                    self.label(details, "日期格式", 12, MUTED).pack(side="right", padx=(12, 8))
        if self.where.get() == "指定位置":
            self.position_row.pack(fill="x")
        else:
            self.position_row.pack_forget()
        if not building:
            self.update_control_height()
            self.changed()

    def build_number(self, frame):
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 16))
        self.segmented(row, ["保留原名", "替换原名", "自定义模板"], self.number_layout, self.switch_number).pack(side="left")
        self.label(row, "按下方列表顺序编号", 12, MUTED).pack(side="right")
        self.number_fields = ctk.CTkFrame(frame, fg_color="transparent")
        self.number_fields.pack(fill="x")
        for column in range(3):
            self.number_fields.grid_columnconfigure(column, weight=1, uniform="number")
        self.entry(self.number_fields, self.number_before, "序号前面字符").grid(row=0, column=0, sticky="ew", padx=(0, 12))
        LabeledMenu(self.number_fields, NUMBER_TYPES, self.number_type, "序号类型").grid(row=0, column=1, sticky="ew", padx=10)
        self.entry(self.number_fields, self.number_after, "序号后面字符").grid(row=0, column=2, sticky="ew", padx=(12, 0))
        self.template_field = self.entry(frame, self.template, "命名模板 · {n} 为序号，{name} 为原名")
        details = ctk.CTkFrame(frame, fg_color="transparent")
        details.pack(fill="x", pady=(10, 0))
        for title, variable in (("开始序号", self.start), ("步长", self.step), ("补零位数", self.width)):
            self.entry(details, variable, title, 120).pack(side="left", padx=(0, 12))

    def switch_number(self, _=None):
        if self.number_layout.get() == "自定义模板":
            self.number_fields.pack_forget()
            self.template_field.pack(fill="x", after=self.pages["自动编号"].winfo_children()[0])
        else:
            self.template_field.pack_forget()
            self.number_fields.pack(fill="x", after=self.pages["自动编号"].winfo_children()[0])
        self.changed()

    def build_manual(self, frame):
        self.label(frame, "双击编辑；粘贴 Excel 单列名称可从选中行向下填充", 12, MUTED).pack(side="left")
        button = self.button(frame, "多行编辑", self.edit_all, width=90)
        button.configure(border_width=0, fg_color="transparent", height=28)
        button.pack(side="right")

    def switch_mode(self, _=None):
        for name, button in self.tab_buttons.items():
            selected = name == self.mode.get()
            button.configure(text_color=INK if selected else "#657185", fg_color=WHITE if selected else "transparent",
                             image=icon(MODES[name], INK if selected else "#657185"),
                             font=("Microsoft YaHei UI", 13, "bold" if selected else "normal"))
            self.tab_lines[name].configure(fg_color=WHITE if selected else BG)
        for name, frame in self.pages.items():
            if name == self.mode.get():
                frame.grid()
            else:
                frame.grid_remove()
        self.update_control_height()
        self.changed()

    def update_control_height(self):
        manual = self.mode.get() == "手动编辑"
        height = 48 if manual else 250 if self.mode.get() == "智能重命名" else 260 if self.mode.get() == "自动编号" else 234
        if self.mode.get() == "插入内容":
            height += 52 if self.insert_kind.get() == "序号" else 0
            height += 64 if self.where.get() == "指定位置" else 0
        self.controls.configure(height=height)
        if manual:
            self.control_bottom.grid_remove()
        else:
            self.control_bottom.grid()
        self.add_rule_button.pack_forget()
        self.control_hint.pack_forget()
        (self.add_rule_button if self.mode.get() == "查找替换" else self.control_hint).pack(side="right")

    def select_mode(self, name):
        self.mode.set(name)
        self.switch_mode()

    def changed(self, *_):
        self.generation += 1
        self.ai_preview = None
        if self.pending:
            self.root.after_cancel(self.pending)
        self.pending = self.root.after(120, self.refresh)

    def options(self):
        template = self.template.get() if self.number_layout.get() == "自定义模板" else self.number_before.get() + "{n}" + self.number_after.get() + ("{name}" if self.number_layout.get() == "保留原名" else "")
        return {"extension": self.extension.get(), "rules": [(a.get(), b.get()) for a, b in self.rules],
                "regex": self.regex.get(), "ignore_case": self.ignore_case.get(),
                "normalize": self.normalize.get(), "spaces": self.spaces.get(), "separators": self.separators.get(),
                "remove_number": self.remove_number.get(), "case": self.case.get(),
                "text": self.insert_text.get(), "where": self.where.get(), "position": self.position.get(),
                "start": self.start.get(), "step": self.step.get(), "width": self.width.get(), "template": template,
                "insert_kind": self.insert_kind.get(), "insert_before": self.insert_before.get(), "insert_after": self.insert_after.get(),
                "info": self.info.get(), "date_format": self.date_format.get(), "number_type": self.number_type.get()}

    def refresh(self):
        if self.pending:
            self.root.after_cancel(self.pending)
            self.pending = None
        mode = MODES[self.mode.get()]
        manual = self.manual
        if mode == "smart" and self.smart_view.get() == "AI 命名":
            mode, manual = "ai", self.ai_preview or {}
        self.plan = make_plan(self.paths, mode, self.options(), manual)
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        for index, item in enumerate(self.plan):
            state = item.error or ("待重命名" if item.changed else "未改变")
            self.tree.insert("", "end", iid=str(index), values=(item.source.name, item.target.name, state, str(item.source.parent)),
                             tags=("error" if item.error else "change" if item.changed else "unchanged",))
        if self.paths:
            self.empty.place_forget()
            self.tree.grid()
            self.scrollbar.grid()
        else:
            self.tree.grid_remove()
            self.scrollbar.grid_remove()
            self.empty.place(relx=.5, rely=.5, anchor="center")
        changes = sum(item.changed for item in self.plan)
        errors = sum(bool(item.error) for item in self.plan)
        self.count.set(f"{len(self.paths)} 项 · {changes} 项改动")
        can_execute = bool(changes and not errors and not self.busy)
        self.execute_button.configure(state="normal" if can_execute else "disabled", fg_color=ACCENT if can_execute else "#E2E4E9",
                                      image=icon("play", "#FFFFFF" if can_execute else "#ADB2BC", 15))
        self.undo_button.configure(state="normal" if self.journal.exists() and not self.busy else "disabled")
        if errors:
            self.status.set(f"{errors} 项需要处理，修正红色行后执行")

    def add_paths(self, paths):
        known = {key(p) for p in self.paths}
        added = 0
        for value in paths:
            path = Path(os.path.abspath(value))
            if key(path) not in known and os.path.lexists(path):
                if len(self.paths) >= 5000:
                    self.status.set("每批最多 5000 项")
                    break
                self.paths.append(path)
                self.insertion[key(path)] = self.next_insertion
                self.next_insertion += 1
                known.add(key(path))
                added += 1
        self.sort_files()
        self.status.set(f"已添加 {added} 项 · 规则仅作用于当前页")

    def sort_files(self, *_):
        if self.order.get() != "按添加顺序":
            self.paths.sort(key=lambda p: (natural_key(p.name), str(p.parent).casefold()), reverse=self.order.get() == "按名称降序")
        else:
            self.paths.sort(key=lambda p: self.insertion.get(key(p), 0))
        self.changed()
        self.refresh()

    def add_files(self):
        self.add_paths(filedialog.askopenfilenames(parent=self.root, title="添加要重命名的文件"))

    def add_folder(self):
        path = filedialog.askdirectory(parent=self.root, title="添加文件夹本身（不递归添加内容）")
        if path:
            self.add_paths([path])

    def paste(self, _=None):
        focused = self.root.focus_get()
        if focused and focused.winfo_class() in ("Entry", "Text", "TEntry"):
            return
        try:
            native = self.native or NativeFiles()
            paths = native.paste()
            if not paths:
                if self.mode.get() == "手动编辑":
                    self.paste_names(native.paste_text())
                else:
                    self.status.set("请先在资源管理器复制文件或文件夹")
            else:
                self.add_paths(paths)
        except Exception as exc:
            self.status.set(str(exc))
        return "break"

    def paste_names(self, text):
        if not self.paths:
            self.status.set("请先添加要重命名的文件")
            return
        names = text.rstrip("\r\n").splitlines()
        selected = self.tree.selection()
        start = min(int(i) for i in selected) if selected else 0
        if not names or len(names) > len(self.paths) - start or any("\t" in name for name in names):
            self.status.set("请粘贴一列名称，行数不能超过当前行到列表末尾的文件数")
            return
        self.manual.update({str(self.paths[start + i]): name for i, name in enumerate(names)})
        self.changed()
        self.refresh()
        self.status.set(f"已填入 {len(names)} 个新名称 · 检查预览后执行")

    def delete_key(self, _):
        if self.root.focus_get() == self.tree:
            self.remove_selected()
            return "break"

    def row_selected(self, _=None):
        selected = self.tree.selection()
        if len(selected) == 1:
            index = int(selected[0])
            if index < len(self.paths):
                self.status.set("所在文件夹：" + str(self.paths[index].parent))

    def remove_selected(self):
        selected = {int(i) for i in self.tree.selection()}
        self.paths = [p for i, p in enumerate(self.paths) if i not in selected]
        self.changed()
        self.refresh()

    def clear_files(self):
        self.paths.clear()
        self.insertion.clear()
        self.manual.clear()
        self.changed()
        self.refresh()
        self.status.set("列表已清空，文件未改变")

    def edit_row(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        if self.mode.get() != "手动编辑":
            self.manual = {str(i.source): i.target.name for i in self.plan}
            self.mode.set("手动编辑")
            self.switch_mode()
            self.refresh()
        item = self.plan[int(row)]
        window = ctk.CTkToplevel(self.root)
        window.title("编辑新名称")
        window.geometry("560x180")
        window.transient(self.root)
        self.label(window, item.source.name, 12, MUTED).pack(anchor="w", padx=20, pady=(18, 8))
        entry = self.entry(window)
        entry.insert(0, item.target.name)
        entry.pack(fill="x", padx=20)
        def save():
            self.manual[str(item.source)] = entry.get()
            self.changed()
            self.refresh()
            window.destroy()
        self.button(window, "应用到预览", save, True, 120).pack(anchor="e", padx=20, pady=12)

    def edit_all(self):
        self.refresh()
        if not self.paths:
            return
        window = ctk.CTkToplevel(self.root)
        window.title("批量编辑名称")
        window.geometry("660x480")
        window.transient(self.root)
        self.label(window, "每行一个完整名称，与当前列表顺序一一对应", 12).pack(anchor="w", padx=20, pady=16)
        editor = CleanTextbox(window, font=("Microsoft YaHei UI", 12))
        editor.pack(fill="both", expand=True, padx=20)
        editor.insert("1.0", "\n".join(i.target.name for i in self.plan))
        sources = list(self.paths)
        def save():
            names = editor.get("1.0", "end-1c").splitlines()
            if len(names) != len(sources) or sources != self.paths:
                messagebox.showerror("无法应用", "行数需与文件数量一致，编辑期间请勿改变文件列表。", parent=window)
                return
            self.manual = {str(p): n for p, n in zip(sources, names)}
            self.changed()
            self.refresh()
            window.destroy()
        self.button(window, "应用到预览", save, True, 120).pack(anchor="e", padx=20, pady=15)

    def generate_ai(self):
        if self.busy:
            return
        if self.smart_view.get() != "AI 命名":
            self.smart_view.set("AI 命名")
            self.switch_smart()
        if not self.paths:
            self.status.set("请先添加文件")
            return
        if not all(self.settings.get(k) for k in ("endpoint", "model", "apiKey")):
            self.open_settings()
            return
        if getattr(self, "worker", None) and self.worker.is_alive():
            self.status.set("上一 AI 请求仍在结束，请稍后重试")
            return
        if len(self.paths) > 200:
            self.status.set("AI 命名每批最多 200 项，本地规则最多 5000 项")
            return
        instruction = self.ai_instruction.get().strip()
        if not instruction:
            self.status.set("请先描述 AI 命名要求")
            return
        self.generation += 1
        generation, paths, settings = self.generation, list(self.paths), dict(self.settings)
        splits = [split_name(p, self.extension.get()) for p in paths]
        self.busy = True
        self.ai_button.configure(state="disabled", text="生成中…")
        self.status.set("AI 正在生成名称 · 文件尚未修改")
        self.refresh()
        def work():
            try:
                names = generate([base for base, suffix in splits], instruction, settings)
                preview = {str(p): n + suffix for p, n, (base, suffix) in zip(paths, names, splits)}
                self.events.put(("ai", (generation, preview, None)))
            except Exception as exc:
                self.events.put(("ai", (generation, None, str(exc) if isinstance(exc, AiError) else "AI 命名失败，请检查模型配置")))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def apply_names(self):
        if self.busy:
            return
        self.refresh()
        if any(i.error for i in self.plan) or not any(i.changed for i in self.plan):
            return
        try:
            count = execute(self.plan, self.journal)
            self.insertion = {key(i.target): self.insertion.get(key(i.source), n) for n, i in enumerate(self.plan)}
            self.paths = [i.target for i in self.plan]
            self.manual.clear()
            self.ai_preview = None
            self.generation += 1
            # Freeze the completed names so another click cannot accidentally apply the rule twice.
            self.mode.set("手动编辑")
            self.switch_mode()
            self.refresh()
            self.status.set(f"已重命名 {count} 项 · 可撤销上次批次")
        except Exception as exc:
            self.status.set(str(exc))
            self.refresh()
            messagebox.showerror("重命名未完成", str(exc), parent=self.root)

    def undo(self):
        if self.busy or not self.journal.exists():
            return
        try:
            record = json.loads(self.journal.read_text(encoding="utf-8"))
            count = restore(self.journal)
            mapping = {key(e["target"]): Path(e["original"]) for e in record["entries"]}
            self.insertion = {key(mapping.get(key(p), p)): self.insertion.get(key(p), n) for n, p in enumerate(self.paths)}
            self.paths = [mapping.get(key(p), p) for p in self.paths]
            self.manual.clear()
            self.mode.set("手动编辑")
            self.switch_mode()
            self.refresh()
            self.status.set(f"已恢复 {count} 项原名称")
        except Exception as exc:
            self.status.set(str(exc))
            messagebox.showerror("无法恢复", str(exc), parent=self.root)

    def open_settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        window = self.settings_window = ctk.CTkToplevel(self.root)
        window.title("AI 命名 · 模型连接")
        window.geometry("540x460")
        window.transient(self.root)
        self.label(window, "连接你的模型", 20).pack(anchor="w", padx=25, pady=(20, 5))
        self.label(window, "OpenAI Chat Completions 格式；本地规则无需配置", 11, MUTED).pack(anchor="w", padx=25)
        entries = {}
        for name, title, hint in (("endpoint", "API 地址", "https://your-provider.com/v1"), ("model", "模型名称", "填写模型 ID"), ("apiKey", "API Key", "输入密钥")):
            entry = self.entry(window, placeholder=title)
            if name == "apiKey":
                entry.configure(show="•")
            entry.insert(0, self.settings.get(name) or "")
            entry.pack(fill="x", padx=25, pady=(14, 0))
            entries[name] = entry
        self.label(window, "此处仅本次有效。永久保存请使用 WinShun 插件设置。", 10, MUTED).pack(anchor="w", padx=25, pady=18)
        def save():
            values = {k: e.get().strip() for k, e in entries.items()}
            try:
                endpoint_url(values["endpoint"])
                if not values["model"] or not values["apiKey"]:
                    raise AiError("请填写模型名称和 API Key")
            except AiError as exc:
                messagebox.showerror("配置无效", str(exc), parent=window)
                return
            self.settings = values
            self.model_caption.set(values["model"])
            window.destroy()
            self.status.set("AI 模型配置已更新")
        self.button(window, "应用配置", save, True, 120).pack(anchor="e", padx=25)

    def show(self):
        if not self.shown_once:
            if self.show_request is None:
                self.show_request = self.root.after(250, self._show_now)
            return
        self._show_now()

    def _show_now(self):
        self.show_request = None
        self.shown_once = True
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        if self.journal.exists():
            self.status.set("存在上次批次记录，可点击撤销 / 恢复")
        self.refresh()

    def close(self):
        self.generation += 1
        if self.standalone:
            self.destroy()
        else:
            self.root.withdraw()

    def destroy(self):
        cancel_callbacks(self.root)
        ctk.ScalingTracker.remove_widget(self.scale_table, self.root)
        if self.native:
            self.native.detach()
        self.root.destroy()

    def poll(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "show":
                    self.show()
                elif event == "settings":
                    self.settings = dict(value)
                    self.model_caption.set(self.settings.get("model") or "选择模型")
                elif event == "data_dir":
                    self.journal = Path(value) / "last-rename.json"
                elif event == "files":
                    self.add_paths(value)
                elif event == "error":
                    self.status.set(value)
                elif event == "ai":
                    generation, preview, error = value
                    self.busy = False
                    self.ai_button.configure(state="normal", text="AI 生成预览")
                    if generation == self.generation:
                        if error:
                            self.status.set(error)
                            messagebox.showerror("AI 命名失败", error, parent=self.root)
                        else:
                            self.ai_preview = preview
                            self.status.set("AI 名称已生成 · 检查预览后点击执行")
                    else:
                        self.status.set("规则或列表已改变，已丢弃之前的 AI 结果")
                    self.refresh()
                elif event == "quit":
                    self.destroy()
                    return
        except queue.Empty:
            pass
        self.root.after(70, self.poll)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--standalone", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass
    ctk.set_appearance_mode("light")
    root = ctk.CTk()
    root.withdraw()
    app = RenameApp(root, args.standalone, native=not args.self_test)
    if args.self_test:
        NativeFiles()  # Resolve Win32 bindings without reading the clipboard.
        root.update_idletasks()
        root.update()
        assert set(MODES) == set(app.pages)
        assert make_plan([], "replace", {}) == []
        result = {"ok": True, "frozen": bool(getattr(sys, "frozen", False)), "python": sys.version.split()[0],
                  "tcl": root.tk.call("info", "patchlevel"), "network_used": False, "ui": "CustomTkinter"}
        cancel_callbacks(root)
        root.destroy()
        print(json.dumps(result), flush=True)
        return
    if args.standalone:
        root.after(300, app.show)
    else:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        threading.Thread(target=serve, args=(sys.stdin, sys.stdout, app.events.put), daemon=True).start()
    root.mainloop()


if __name__ == "__main__":
    main()
