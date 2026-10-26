using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace WinShun.BatchRenamer
{
    public sealed class MainForm : Form
    {
        StudioPalette palette = StudioTheme.Light;
        Color Ink { get { return palette.Ink; } }
        Color Muted { get { return palette.Muted; } }
        Color Accent { get { return palette.Accent; } }
        Color Canvas { get { return palette.Canvas; } }
        readonly Func<bool> readSystemTheme;
        readonly ContextMenuStrip themeMenu = new ContextMenuStrip(), more = new ContextMenuStrip();
        Button themeButton;
        bool themeUpdateQueued;
        internal ThemePreference ThemeMode { get; private set; }
        internal bool IsDarkTheme { get { return palette.Dark; } }
        readonly List<SourceItem> sources = new List<SourceItem>();
        readonly List<Rule> rules = new List<Rule>();
        readonly FileEngine engine;
        readonly string dataDir;
        readonly Panel body = new Panel(), renameTools = new Panel(), createTools = new Panel();
        readonly Label title = new Label(), subtitle = new Label(), status = new Label(), stats = new Label(), details = new Label();
        readonly Button renameTab, createTab, execute;
        readonly DataGridView grid = new StudioGrid();
        readonly Label emptyState = new Label();
        readonly TableLayoutPanel layout = new TableLayoutPanel();
        readonly SplitContainer workspaceSplit = new SplitContainer();
        readonly TableLayoutPanel ruleLayout = new TableLayoutPanel();
        readonly ToolTip tips = new ToolTip();
        FlowLayoutPanel fileActions;
        readonly CheckedListBox ruleList = new CheckedListBox();
        readonly TableLayoutPanel editor = new TableLayoutPanel();
        readonly ComboBox ruleType = new StudioComboBox(), importKind = new StudioComboBox(), sort = new StudioComboBox(), createKind = new StudioComboBox(), createMode = new StudioComboBox();
        readonly TextBox folder = new TextBox(), template = new TextBox(), names = new TextBox();
        readonly NumericUpDown count = new StudioNumericUpDown();
        readonly CheckBox recursive = new CheckBox();
        readonly System.Windows.Forms.Timer debounce = new System.Windows.Forms.Timer();
        OperationPlan plan;
        bool creating, busy, changingEditor;
        System.Threading.CancellationTokenSource previewCancellation;
        int generation;
        string seed = Guid.NewGuid().ToString("N");
        string selectAfterPreview;
        DateTime planDate = DateTime.Now;
        public bool IsBusy { get { return busy; } }
        [DllImport("shlwapi.dll", CharSet = CharSet.Unicode)] static extern int StrCmpLogicalW(string a, string b);

        public MainForm(string data) : this(data, StudioTheme.ReadSystemDark) { }
        internal MainForm(string data, Func<bool> systemThemeReader)
        {
            dataDir = data; engine = new FileEngine(data); readSystemTheme = systemThemeReader;
            ThemeMode = StudioTheme.Load(data);
            engine.Progress = delegate(int done, int total)
            {
                if ((done % 32 == 0 || done == total) && IsHandleCreated && !IsDisposed)
                    BeginInvoke(new Action(delegate { if (busy) status.Text = "正在处理 " + done + " / " + total + "…"; }));
            };
            SuspendLayout();
            AutoScaleDimensions = new SizeF(96F, 96F); AutoScaleMode = AutoScaleMode.Dpi;
            Text = "易更名 · WinShun"; Size = new Size(1360, 860); MinimumSize = new Size(1060, 700);
            StartPosition = FormStartPosition.CenterScreen; BackColor = Canvas; ForeColor = Ink;
            Font = new Font("Microsoft YaHei UI", 10.5F, FontStyle.Regular, GraphicsUnit.Point);
            string iconFile = Path.Combine(CommunityHost.PluginDirectory, "app.ico");
            if (File.Exists(iconFile)) Icon = new Icon(iconFile);
            Panel main = new Panel { Dock = DockStyle.Fill, Padding = new Padding(12, 0, 12, 0) }; Controls.Add(main);
            layout.Dock = DockStyle.Fill; layout.ColumnCount = 1; layout.RowCount = 4; layout.BackColor = Canvas; layout.Margin = Padding.Empty;
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 52)); layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 50)); layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 48));
            main.Controls.Add(layout);
            Panel header = new Panel { Dock = DockStyle.Fill, Margin = Padding.Empty };
            title.Text = "易更名"; title.Font = new Font(Font.FontFamily, 13.5F, FontStyle.Bold, GraphicsUnit.Point); title.AutoSize = true; title.Location = new Point(6, 14); header.Controls.Add(title);
            FlowLayoutPanel modes = new FlowLayoutPanel { Location = new Point(160, 10), Size = new Size(300, 34), WrapContents = false };
            renameTab = MakeButton("批量重命名", delegate { Switch(false); }, true); createTab = MakeButton("批量创建", delegate { Switch(true); }, false);
            modes.Controls.Add(renameTab); modes.Controls.Add(createTab); header.Controls.Add(modes);
            FlowLayoutPanel presets = new FlowLayoutPanel { Dock = DockStyle.Right, Width = 390, FlowDirection = FlowDirection.RightToLeft, Padding = new Padding(0, 10, 0, 0), WrapContents = false };
            themeMenu.Font = Font;
            foreach (ThemePreference mode in Enum.GetValues(typeof(ThemePreference)))
            {
                ThemePreference choice = mode;
                ToolStripMenuItem item = new ToolStripMenuItem(ThemeName(mode)) { Tag = mode };
                item.Click += delegate { SetThemeMode(choice); }; themeMenu.Items.Add(item);
            }
            themeButton = MakeButton("主题 · 跟随系统 ▾", delegate { themeMenu.Show(themeButton, new Point(0, themeButton.Height)); }, false);
            presets.Controls.Add(themeButton); presets.Controls.Add(MakeButton("保存规则", SavePreset, false)); presets.Controls.Add(MakeButton("载入规则", LoadPreset, false)); header.Controls.Add(presets);
            layout.Controls.Add(header, 0, 0);
            Panel tools = new Panel { Dock = DockStyle.Fill, BackColor = Color.White, Tag = "theme-surface", Padding = new Padding(8, 6, 8, 6), Margin = new Padding(0, 0, 0, 8) };
            layout.Controls.Add(tools, 0, 1);
            renameTools.Dock = DockStyle.Fill; createTools.Dock = DockStyle.Fill; tools.Controls.Add(renameTools); tools.Controls.Add(createTools); createTools.Visible = false;
            BuildRenameTools(); BuildCreateTools();

            body.Dock = DockStyle.Fill; body.Margin = Padding.Empty; layout.Controls.Add(body, 0, 2);
            workspaceSplit.Dock = DockStyle.Fill; workspaceSplit.BackColor = Canvas; workspaceSplit.SplitterWidth = 8; workspaceSplit.FixedPanel = FixedPanel.Panel2;
            workspaceSplit.Size = new Size(1320, 700); workspaceSplit.Panel1MinSize = 460; workspaceSplit.Panel2MinSize = 320;
            workspaceSplit.SplitterDistance = 952; body.Controls.Add(workspaceSplit);
            BuildPreview(workspaceSplit.Panel1); BuildRules(workspaceSplit.Panel2);
            Panel footer = new Panel { Dock = DockStyle.Fill, Margin = Padding.Empty };
            layout.Controls.Add(footer, 0, 3);
            FlowLayoutPanel actions = new FlowLayoutPanel { Dock = DockStyle.Left, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink, Padding = new Padding(0, 9, 0, 0), WrapContents = false };
            execute = MakeButton("执行重命名", ExecuteClick, true); execute.MinimumSize = new Size(112, 30); actions.Controls.Add(execute);
            actions.Controls.Add(MakeButton("撤销最近操作", UndoClick, false));
            more.Font = Font;
            more.Items.Add("导出预览 CSV", null, delegate { if (!busy) ExportPreview(); });
            more.Items.Add("重新生成随机值", null, delegate { if (!busy) { seed = Guid.NewGuid().ToString("N"); Schedule(); } });
            more.Items.Add(new ToolStripSeparator()); more.Items.Add("恢复中断操作", null, delegate { if (!busy) RecoverClick(); });
            Button moreButton = null; moreButton = MakeButton("更多 ⋯", delegate { more.Show(moreButton, new Point(0, -more.PreferredSize.Height)); }, false); actions.Controls.Add(moreButton);
            footer.Controls.Add(actions);
            stats.ForeColor = Muted; stats.Dock = DockStyle.Right; stats.Width = 152; stats.TextAlign = ContentAlignment.MiddleRight; footer.Controls.Add(stats);
            status.Dock = DockStyle.Fill; status.ForeColor = Muted; status.AutoEllipsis = true; status.TextAlign = ContentAlignment.MiddleLeft; status.Padding = new Padding(10, 0, 8, 0); status.Text = "拖入文件，添加规则后即可预览。"; footer.Controls.Add(status); status.BringToFront();
            debounce.Interval = 280; debounce.Tick += async delegate { debounce.Stop(); await RefreshPreview(); };
            AllowDrop = true;
            DragEnter += delegate(object sender, DragEventArgs e) { if (!busy && e.Data.GetDataPresent(DataFormats.FileDrop)) e.Effect = DragDropEffects.Copy; };
            DragDrop += async delegate(object sender, DragEventArgs e) { if (!busy) { Switch(false); await AddPaths((string[])e.Data.GetData(DataFormats.FileDrop)); } };
            FormClosing += delegate(object sender, FormClosingEventArgs e) { if (busy) { e.Cancel = true; MessageBox.Show(this, "操作进行中，请等待完成后关闭。", "正在处理", MessageBoxButtons.OK, MessageBoxIcon.Information); } };
            FormClosed += delegate { if (previewCancellation != null) previewCancellation.Cancel(); debounce.Dispose(); tips.Dispose(); more.Dispose(); themeMenu.Dispose(); };
            Shown += delegate
            {
                ApplyDensity();
                try { if (engine.Pending().Count > 0) status.Text = "检测到未完成操作，请先点击“更多 → 恢复中断操作”。"; }
                catch (Exception ex) { Error(ex); }
            };
            DpiChanged += delegate { BeginInvoke(new Action(ApplyDensity)); };
            RefreshRules(-1); UpdateStats(); ApplyTheme(); ResumeLayout(true);
        }
        Button MakeButton(string text, Action action, bool primary)
        {
            Button b = new StudioButton { Primary = primary, Text = text, AutoSize = true, Height = 30, MinimumSize = new Size(28, 30), Padding = new Padding(5, 0, 5, 0), Cursor = Cursors.Hand, BackColor = primary ? palette.Primary : palette.Surface, ForeColor = primary ? Color.White : Ink, Margin = new Padding(0, 0, 6, 0) };
            b.FlatAppearance.BorderColor = primary ? Accent : Color.FromArgb(218, 226, 231); b.FlatAppearance.BorderSize = primary ? 0 : 1;
            b.Click += delegate { if (!busy) action(); }; return b;
        }
        static void Options(ComboBox box, string[] texts, int selected)
        { box.DropDownStyle = ComboBoxStyle.DropDownList; box.Items.AddRange(texts); box.SelectedIndex = selected; }
        void BuildRenameTools()
        {
            FlowLayoutPanel top = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false };
            top.Controls.Add(MakeButton("＋ 文件", AddFiles, true));
            top.Controls.Add(MakeButton("＋ 文件夹", AddFolder, false));
            top.Controls.Add(MakeButton("导入目录内容", ImportContents, false));
            recursive.Text = "含子目录"; recursive.AutoSize = true; recursive.Margin = new Padding(10, 5, 8, 0); top.Controls.Add(recursive);
            Options(importKind, new[] { "文件和文件夹", "仅文件", "仅文件夹" }, 0); importKind.Width = 130; importKind.Margin = new Padding(0, 3, 0, 0); top.Controls.Add(importKind);
            top.Controls.Add(new Label { Text = "也可直接拖入文件或文件夹", AutoSize = true, ForeColor = Muted, Margin = new Padding(18, 6, 0, 0) });
            renameTools.Controls.Add(top);
        }
        void BuildCreateTools()
        {
            TableLayoutPanel table = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 5, RowCount = 2 };
            table.Margin = Padding.Empty; table.RowStyles.Add(new RowStyle(SizeType.Absolute, 32)); table.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 70)); table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 94)); table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 125)); table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 125));
            createTools.Controls.Add(table);
            table.Controls.Add(FieldLabel("目标目录"), 0, 0); folder.Dock = DockStyle.Fill; table.Controls.Add(folder, 1, 0); table.Controls.Add(MakeButton("选择…", PickCreateFolder, false), 2, 0);
            Options(createKind, new[] { "创建文件", "创建文件夹" }, 0); createKind.Dock = DockStyle.Fill; table.Controls.Add(createKind, 3, 0);
            Options(createMode, new[] { "模板 + 数量", "按行创建" }, 0); createMode.Dock = DockStyle.Fill; table.Controls.Add(createMode, 4, 0);
            table.Controls.Add(FieldLabel("名称模板"), 0, 1); template.Text = "新建_{n:000}.txt"; template.Dock = DockStyle.Fill; table.Controls.Add(template, 1, 1);
            names.Multiline = true; names.ScrollBars = ScrollBars.Vertical; names.Dock = DockStyle.Fill; names.Visible = false;
            count.Minimum = 1; count.Maximum = Planner.MaxItems; count.Value = 10; count.Dock = DockStyle.Fill; table.Controls.Add(count, 2, 1);
            Label hint = FieldLabel("{n:000} 序号 · {date:yyyyMMdd} 日期"); hint.AutoSize = false; hint.AutoEllipsis = true; hint.Dock = DockStyle.Fill; table.SetColumnSpan(hint, 2); table.Controls.Add(hint, 3, 1);
            tips.SetToolTip(hint, "名称可使用 {n:000} 序号和 {date:yyyyMMdd} 日期。\r\n右侧组合规则同样适用于创建。");
            folder.TextChanged += delegate { Schedule(); }; template.TextChanged += delegate { Schedule(); }; names.TextChanged += delegate { Schedule(); }; count.ValueChanged += delegate { Schedule(); }; createKind.SelectedIndexChanged += delegate { Schedule(); };
            createMode.SelectedIndexChanged += delegate
            {
                if (createMode.SelectedIndex == 1)
                {
                    table.Controls.Remove(template); table.Controls.Add(names, 1, 1); names.Visible = true; count.Enabled = false;
                    if (names.Text.Length == 0) names.Text = "第一项.txt\r\n第二项.txt\r\n第三项.txt";
                }
                else { table.Controls.Remove(names); table.Controls.Add(template, 1, 1); template.Visible = true; count.Enabled = true; }
                StudioTheme.ApplyTree(table, palette, palette.Surface); UpdateToolsHeight(); Schedule();
            };
            folder.Text = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        }
        Label FieldLabel(string text) { return new Label { Text = text, AutoSize = true, ForeColor = Muted, Margin = new Padding(0, 5, 4, 3), UseCompatibleTextRendering = false }; }
        void BuildPreview(Panel panel)
        {
            panel.BackColor = Color.White; panel.Tag = "theme-surface";
            TableLayoutPanel table = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 3, Margin = Padding.Empty };
            // An implicit AutoSize column retains the header's previous preferred width,
            // leaving its right-docked actions outside the viewport after narrowing.
            table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            table.RowStyles.Add(new RowStyle(SizeType.Absolute, 42)); table.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); table.RowStyles.Add(new RowStyle(SizeType.Absolute, 29)); panel.Controls.Add(table);
            Panel previewHeader = new Panel { Dock = DockStyle.Fill, Margin = Padding.Empty };
            previewHeader.Controls.Add(new Label { Text = "文件预览", Font = new Font(Font, FontStyle.Bold), Dock = DockStyle.Fill, AutoEllipsis = true, TextAlign = ContentAlignment.MiddleLeft, Padding = new Padding(10, 0, 6, 0) });
            fileActions = new FlowLayoutPanel { Dock = DockStyle.Right, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink, WrapContents = false, Padding = new Padding(0, 6, 0, 0) };
            Options(sort, new[] { "名称自然排序 ↑", "名称自然排序 ↓", "完整路径排序" }, 0); sort.Width = 145; sort.Margin = new Padding(0, 2, 5, 0); fileActions.Controls.Add(sort);
            fileActions.Controls.Add(MakeButton("排序", SortSources, false));
            Button up = MakeButton("↑", delegate { MoveSource(-1); }, false), down = MakeButton("↓", delegate { MoveSource(1); }, false);
            tips.SetToolTip(up, "上移选中项目"); tips.SetToolTip(down, "下移选中项目"); fileActions.Controls.Add(up); fileActions.Controls.Add(down);
            fileActions.Controls.Add(MakeButton("移除", RemoveSelected, false)); fileActions.Controls.Add(MakeButton("清空", delegate { sources.Clear(); Schedule(); }, false));
            previewHeader.Controls.Add(fileActions); table.Controls.Add(previewHeader, 0, 0);
            grid.Dock = DockStyle.Fill; grid.BorderStyle = BorderStyle.None; grid.BackgroundColor = Color.White; grid.ReadOnly = true; grid.AllowUserToAddRows = false; grid.AllowUserToDeleteRows = false; grid.AllowUserToResizeRows = false;
            grid.RowHeadersVisible = false; grid.SelectionMode = DataGridViewSelectionMode.FullRowSelect; grid.AutoGenerateColumns = false; grid.EnableHeadersVisualStyles = false; grid.ColumnHeadersHeight = 38; grid.RowTemplate.Height = 33;
            grid.ColumnHeadersHeight = 32; grid.RowTemplate.Height = 30; grid.ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.DisableResizing;
            grid.Font = Font; grid.DefaultCellStyle.Font = Font; grid.ColumnHeadersDefaultCellStyle.Font = Font;
            grid.ColumnHeadersDefaultCellStyle.BackColor = Color.FromArgb(239, 244, 247); grid.ColumnHeadersDefaultCellStyle.ForeColor = Ink; grid.ColumnHeadersDefaultCellStyle.SelectionBackColor = Color.FromArgb(239, 244, 247); grid.ColumnHeadersBorderStyle = DataGridViewHeaderBorderStyle.None;
            grid.DefaultCellStyle.SelectionBackColor = Color.FromArgb(222, 242, 236); grid.DefaultCellStyle.SelectionForeColor = Ink; grid.DefaultCellStyle.Padding = new Padding(6, 0, 6, 0);
            grid.DefaultCellStyle.ForeColor = Ink; grid.AlternatingRowsDefaultCellStyle.BackColor = Color.FromArgb(250, 252, 253); grid.CellBorderStyle = DataGridViewCellBorderStyle.SingleHorizontal; grid.GridColor = Color.FromArgb(237, 241, 245);
            grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "index", HeaderText = "#", Width = 45 });
            grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "kind", HeaderText = "类型", Width = 62 });
            grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "old", HeaderText = "原名称", AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill, FillWeight = 100 });
            grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "new", HeaderText = "新名称", AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill, FillWeight = 120 });
            grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "state", HeaderText = "状态", Width = 88 });
            foreach (DataGridViewColumn column in grid.Columns) column.SortMode = DataGridViewColumnSortMode.NotSortable;
            grid.SelectionChanged += delegate
            {
                if (grid.CurrentRow == null || plan == null || grid.CurrentRow.Index >= plan.Entries.Count) return;
                PlanEntry e = plan.Entries[grid.CurrentRow.Index]; details.Text = (String.IsNullOrEmpty(e.Error) ? e.Destination : e.Error) ?? "";
            };
            table.Controls.Add(grid, 0, 1);
            emptyState.Text = "将文件或文件夹拖到这里\r\n\r\n添加规则后，新名称会实时显示在右侧列。"; emptyState.Dock = DockStyle.Fill; emptyState.BackColor = Color.White; emptyState.ForeColor = Muted; emptyState.TextAlign = ContentAlignment.MiddleCenter; grid.Controls.Add(emptyState);
            details.ForeColor = Muted; details.Dock = DockStyle.Fill; details.Padding = new Padding(10, 0, 8, 0); details.TextAlign = ContentAlignment.MiddleLeft; details.AutoEllipsis = true; table.Controls.Add(details, 0, 2);
        }
        void BuildRules(Panel panel)
        {
            panel.BackColor = Color.White; panel.Tag = "theme-surface"; panel.Padding = new Padding(12, 10, 12, 8);
            TableLayoutPanel table = ruleLayout; table.Dock = DockStyle.Fill; table.ColumnCount = 1; table.RowCount = 6; table.Margin = Padding.Empty;
            table.RowStyles.Add(new RowStyle(SizeType.Absolute, 28)); table.RowStyles.Add(new RowStyle(SizeType.Absolute, 37)); table.RowStyles.Add(new RowStyle(SizeType.Absolute, 96)); table.RowStyles.Add(new RowStyle(SizeType.Absolute, 35)); table.RowStyles.Add(new RowStyle(SizeType.Absolute, 28)); table.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); panel.Controls.Add(table);
            table.Controls.Add(new Label { Text = "组合规则", Font = new Font(Font, FontStyle.Bold), AutoSize = true }, 0, 0);
            FlowLayoutPanel add = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false };
            Options(ruleType, new[] { "序号", "大小写转换", "文字替换", "插入文字", "随机字符", "截取 / 删除", "正则匹配", "名称模板", "去除首尾空白" }, 0); ruleType.Width = 200; ruleType.Margin = new Padding(0, 2, 6, 0); add.Controls.Add(ruleType);
            add.Controls.Add(MakeButton("＋ 添加", delegate { AddRule(Rule.New(new[] { "Sequence", "Case", "Replace", "Insert", "Random", "Slice", "Regex", "Template", "Trim" }[ruleType.SelectedIndex])); }, true)); table.Controls.Add(add, 0, 1);
            ruleList.Dock = DockStyle.Fill; ruleList.BorderStyle = BorderStyle.None; ruleList.BackColor = Color.FromArgb(247, 250, 252); ruleList.CheckOnClick = false; ruleList.IntegralHeight = false; ruleList.HorizontalScrollbar = true;
            ruleList.SelectedIndexChanged += delegate { if (!changingEditor) BuildEditor(); };
            ruleList.ItemCheck += delegate(object sender, ItemCheckEventArgs e)
            { if (!changingEditor && e.Index < rules.Count) { rules[e.Index].Enabled = e.NewValue == CheckState.Checked; Schedule(); } };
            table.Controls.Add(ruleList, 0, 2);
            FlowLayoutPanel order = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false, Margin = Padding.Empty };
            Button up = MakeButton("↑", delegate { MoveRule(-1); }, false); order.Controls.Add(up);
            Button down = MakeButton("↓", delegate { MoveRule(1); }, false); order.Controls.Add(down);
            order.Controls.Add(MakeButton("移除规则", delegate { int i = ruleList.SelectedIndex; if (i >= 0) { rules.RemoveAt(i); RefreshRules(Math.Min(i, rules.Count - 1)); Schedule(); } }, false));
            table.Controls.Add(order, 0, 3);
            table.Controls.Add(new Label { Text = "规则参数", Font = new Font(Font, FontStyle.Bold), AutoSize = true, Margin = new Padding(0, 4, 0, 0) }, 0, 4);
            Panel scroll = new Panel { Dock = DockStyle.Fill, AutoScroll = true }; table.Controls.Add(scroll, 0, 5);
            editor.Dock = DockStyle.Top; editor.AutoSize = true; editor.ColumnCount = 2;
            editor.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 78)); editor.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); scroll.Controls.Add(editor);
            editor.SizeChanged += delegate { foreach (Label label in editor.Controls.OfType<Label>().Where(x => editor.GetColumnSpan(x) == 2)) label.MaximumSize = new Size(Math.Max(1, editor.ClientSize.Width), 0); };
        }
        public void AddRule(Rule rule) { rules.Add(rule); RefreshRules(rules.Count - 1); Schedule(); }
        void RefreshRules(int select)
        {
            changingEditor = true; ruleList.Items.Clear();
            foreach (Rule rule in rules) ruleList.Items.Add(rule.Label, rule.Enabled);
            ruleList.SelectedIndex = select; changingEditor = false;
            if (ruleLayout.RowStyles.Count > 2) ruleLayout.RowStyles[2].Height = Math.Min(154, Math.Max(74, rules.Count * 24 + 12)) * DeviceDpi / 96F;
            BuildEditor();
        }
        void UpdateRuleLabel(Rule rule)
        {
            int i = rules.IndexOf(rule); if (i < 0) return;
            changingEditor = true; ruleList.Items[i] = rule.Label; changingEditor = false; Schedule();
        }
        void MoveRule(int direction)
        {
            int i = ruleList.SelectedIndex, j = i + direction;
            if (i < 0 || j < 0 || j >= rules.Count) return;
            Rule rule = rules[i]; rules.RemoveAt(i); rules.Insert(j, rule); RefreshRules(j); Schedule();
        }
        void BuildEditor()
        {
            editor.SuspendLayout();
            foreach (Control control in editor.Controls.Cast<Control>().ToList()) control.Dispose();
            editor.Controls.Clear(); editor.RowStyles.Clear(); editor.RowCount = 0;
            int i = ruleList.SelectedIndex;
            if (i < 0 || i >= rules.Count)
            {
                AddEditorRow("", new Label { Text = "添加一条规则开始。\r\n\r\n勾选启用，使用 ↑ ↓ 调整顺序。\r\n主名称默认保留文件扩展名。", AutoSize = true, ForeColor = Muted, MaximumSize = new Size(240, 0) });
                StudioTheme.ApplyTree(editor, palette, palette.Surface); editor.ResumeLayout(); return;
            }
            Rule r = rules[i];
            AddChoice("作用范围", new[] { "主名称（保留扩展名）", "完整名称", "仅扩展名（不含点）" }, new[] { "Name", "FullName", "Extension" }, r.Target, v => r.Target = v, r);
            if (r.Type == "Sequence" || r.Type == "Insert" || r.Type == "Random")
            {
                AddChoice("放置方式", new[] { "后缀", "前缀", "指定位置", "替换原内容" }, new[] { "Suffix", "Prefix", "Position", "Replace" }, r.Mode, v => r.Mode = v, r);
                if (r.Mode == "Position") AddNumber("位置", r.Position, -10000, 10000, v => r.Position = (int)v, r);
            }
            switch (r.Type)
            {
                case "Sequence":
                    AddNumber("起始序号", r.Start, -1000000000, 1000000000, v => r.Start = (long)v, r);
                    AddNumber("步长", r.Step, -1000000, 1000000, v => r.Step = (long)v, r);
                    AddNumber("补零位数", r.Digits, 1, 18, v => r.Digits = (int)v, r);
                    AddText("分隔符", r.Text, v => r.Text = v, r); break;
                case "Case": AddChoice("转换方式", new[] { "全部大写", "全部小写", "单词首字母大写", "大小写反转" }, new[] { "Upper", "Lower", "Title", "Swap" }, r.Mode, v => r.Mode = v, r); break;
                case "Replace": AddText("查找文字", r.Pattern, v => r.Pattern = v, r); AddText("替换为", r.Replacement, v => r.Replacement = v, r); AddCheck("忽略大小写", r.IgnoreCase, v => r.IgnoreCase = v, r); break;
                case "Insert": AddText("插入文字", r.Text, v => r.Text = v, r); break;
                case "Random":
                    AddNumber("随机长度", r.Length, 1, 128, v => r.Length = (int)v, r);
                    AddText("可用字符", r.Charset, v => r.Charset = v, r); AddText("分隔符", r.Text, v => r.Text = v, r); break;
                case "Slice":
                    AddChoice("处理方式", new[] { "保留截取部分", "删除截取部分" }, new[] { "Keep", "Remove" }, r.Mode, v => r.Mode = v, r);
                    AddNumber("起始位置", r.Position, -10000, 10000, v => r.Position = (int)v, r);
                    AddNumber("字符数量", r.Length, 0, 10000, v => r.Length = (int)v, r); break;
                case "Regex":
                    AddChoice("匹配方式", new[] { "匹配并替换", "提取匹配内容" }, new[] { "Replace", "Extract" }, r.Mode, v => r.Mode = v, r);
                    AddText("表达式", r.Pattern, v => r.Pattern = v, r); AddText("替换 / 提取", r.Replacement, v => r.Replacement = v, r);
                    AddCheck("忽略大小写", r.IgnoreCase, v => r.IgnoreCase = v, r); break;
                case "Template": AddText("名称模板", r.Text, v => r.Text = v, r); break;
            }
            string help = "位置从 0 开始；负数从末尾倒数。\r\n所有规则按列表顺序依次应用。";
            if (r.Type == "Regex") help = "支持 .NET 正则：$1、${组名}、$0。\r\n没有匹配时保留原内容。";
            if (r.Type == "Template") help = "{name} 当前内容  {original} 原主名称\r\n{ext} 原扩展名  {parent} 原父目录\r\n{n:000} 从 1 开始  {date:yyyyMMdd}";
            if (r.Type == "Random") help = "预览和执行使用同一组随机值。\r\n点击“更多 → 重新生成随机值”生成另一组。";
            if (r.Type == "Sequence" && r.Mode != "Position") help = "序号按预览列表顺序生成。\r\n组合规则从上到下依次执行。";
            AddEditorRow("", new Label { Text = help, AutoSize = true, ForeColor = Muted, MaximumSize = new Size(270, 0), Margin = new Padding(0, 12, 0, 0) });
            StudioTheme.ApplyTree(editor, palette, palette.Surface); editor.ResumeLayout();
        }
        void AddEditorRow(string label, Control control)
        {
            int row = editor.RowCount++; editor.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            control.Dock = DockStyle.Top; control.Margin = new Padding(0, 2, 0, 4);
            if (label.Length > 0) editor.Controls.Add(FieldLabel(label), 0, row);
            else editor.SetColumnSpan(control, 2);
            if (label.Length == 0 && control is Label) control.MaximumSize = new Size(Math.Max(1, editor.ClientSize.Width), 0);
            editor.Controls.Add(control, label.Length > 0 ? 1 : 0, row);
        }
        void AddText(string label, string value, Action<string> change, Rule rule)
        { TextBox text = new TextBox { Text = value ?? "" }; text.TextChanged += delegate { change(text.Text); UpdateRuleLabel(rule); }; AddEditorRow(label, text); }
        void AddNumber(string label, decimal value, decimal min, decimal max, Action<decimal> change, Rule rule)
        { NumericUpDown n = new StudioNumericUpDown { Minimum = min, Maximum = max, Value = Math.Min(max, Math.Max(min, value)) }; n.ValueChanged += delegate { change(n.Value); UpdateRuleLabel(rule); }; AddEditorRow(label, n); }
        void AddChoice(string label, string[] text, string[] values, string value, Action<string> change, Rule rule)
        { ComboBox combo = new StudioComboBox(); Options(combo, text, Math.Max(0, Array.IndexOf(values, value))); combo.SelectedIndexChanged += delegate { change(values[combo.SelectedIndex]); UpdateRuleLabel(rule); if (label == "放置方式") BeginInvoke(new Action(delegate { if (!IsDisposed) BuildEditor(); })); }; AddEditorRow(label, combo); }
        void AddCheck(string label, bool value, Action<bool> change, Rule rule)
        { CheckBox check = new CheckBox { Text = label, Checked = value, AutoSize = true }; check.CheckedChanged += delegate { change(check.Checked); UpdateRuleLabel(rule); }; AddEditorRow("", check); }

        public void OpenRequest(string command, string query)
        {
            Switch(command == "create");
            string path = (query ?? "").Trim().Trim('"');
            if (path.Length > 0)
            {
                if (creating && Directory.Exists(path)) folder.Text = Fs.Normalize(path);
                else if (!creating) AddRequestPaths(path);
            }
            if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
            Show(); Activate();
        }
        async void AddRequestPaths(string path) { await AddPaths(new[] { path }); }
        void Switch(bool create)
        {
            creating = create; createTools.Visible = create; renameTools.Visible = !create;
            execute.Text = create ? "执行创建" : "执行重命名";
            ApplyModeStyle(); UpdateToolsHeight();
            Schedule();
        }
        void ApplyModeStyle()
        {
            foreach (Button tab in new[] { renameTab, createTab })
            {
                bool selected = tab == (creating ? createTab : renameTab);
                tab.BackColor = selected ? palette.Selection : Canvas; tab.ForeColor = selected ? Accent : Muted;
                tab.FlatAppearance.BorderSize = 0; tab.Font = new Font(Font, selected ? FontStyle.Bold : FontStyle.Regular);
            }
            if (fileActions != null) fileActions.Visible = !creating;
        }
        static string ThemeName(ThemePreference mode)
        { return mode == ThemePreference.Dark ? "深色" : mode == ThemePreference.Light ? "浅色" : "跟随系统"; }
        internal void SetThemeMode(ThemePreference mode)
        {
            ThemeMode = mode; ApplyTheme();
            try { StudioTheme.Save(dataDir, mode); }
            catch (IOException ex) { status.Text = "主题已切换，但无法保存设置：" + ex.Message; }
            catch (UnauthorizedAccessException ex) { status.Text = "主题已切换，但无法保存设置：" + ex.Message; }
        }
        void ApplyTheme()
        {
            palette = (ThemeMode == ThemePreference.Dark || (ThemeMode == ThemePreference.System && readSystemTheme())) ? StudioTheme.Dark : StudioTheme.Light;
            SuspendLayout();
            StudioTheme.ApplyTree(this, palette, Canvas);
            grid.BackgroundColor = palette.Surface; grid.GridColor = palette.Canvas;
            grid.DefaultCellStyle.BackColor = palette.Surface; grid.DefaultCellStyle.ForeColor = Ink;
            grid.DefaultCellStyle.SelectionBackColor = palette.Selection; grid.DefaultCellStyle.SelectionForeColor = Ink;
            grid.ColumnHeadersDefaultCellStyle.BackColor = palette.Header; grid.ColumnHeadersDefaultCellStyle.ForeColor = Ink;
            grid.ColumnHeadersDefaultCellStyle.SelectionBackColor = palette.Header; grid.ColumnHeadersDefaultCellStyle.SelectionForeColor = Ink;
            grid.AlternatingRowsDefaultCellStyle.BackColor = palette.Alternate;
            ruleList.BackColor = palette.List; emptyState.BackColor = palette.Surface;
            foreach (DataGridViewRow row in grid.Rows)
                StylePlanRow(row, plan != null && row.Index < plan.Entries.Count && !String.IsNullOrEmpty(plan.Entries[row.Index].Error));
            foreach (ContextMenuStrip menu in new[] { themeMenu, more })
            {
                menu.BackColor = palette.Surface; menu.ForeColor = Ink; menu.Renderer = new StudioMenuRenderer(palette);
                foreach (ToolStripItem item in menu.Items) { item.BackColor = palette.Surface; item.ForeColor = Ink; }
            }
            foreach (ToolStripMenuItem item in themeMenu.Items) item.Checked = (ThemePreference)item.Tag == ThemeMode;
            themeButton.Text = "主题 · " + ThemeName(ThemeMode) + " ▾";
            ApplyModeStyle();
            if (IsHandleCreated) StudioTheme.ApplyTitleBar(Handle, palette.Dark);
            ResumeLayout(true); Invalidate(true);
        }
        void StylePlanRow(DataGridViewRow row, bool error)
        {
            row.DefaultCellStyle.BackColor = error ? palette.ErrorBackground : Color.Empty;
            row.Cells["new"].Style.ForeColor = Accent; row.Cells["new"].Style.SelectionForeColor = Accent;
            row.Cells["state"].Style.ForeColor = error ? palette.Error : Ink;
            row.Cells["state"].Style.SelectionForeColor = error ? palette.Error : Ink;
        }
        protected override void OnHandleCreated(EventArgs e)
        { base.OnHandleCreated(e); StudioTheme.ApplyTitleBar(Handle, palette.Dark); }
        protected override void WndProc(ref Message message)
        {
            int id = message.Msg; base.WndProc(ref message);
            // Windows broadcasts these when Personalization changes. Queue onto the UI
            // message loop, so native controls finish handling the notification first.
            if ((id == 0x001A || id == 0x031A || id == 0x0015) && ThemeMode == ThemePreference.System && themeButton != null && IsHandleCreated && !IsDisposed && !Disposing && !themeUpdateQueued)
            {
                themeUpdateQueued = true;
                BeginInvoke(new Action(delegate
                {
                    themeUpdateQueued = false;
                    if (!IsDisposed && ThemeMode == ThemePreference.System) ApplyTheme();
                }));
            }
        }
        void UpdateToolsHeight()
        {
            if (layout.RowStyles.Count > 1) layout.RowStyles[1].Height = (creating ? (createMode.SelectedIndex == 1 ? 122 : 88) : 50) * DeviceDpi / 96F;
        }
        void ApplyDensity()
        {
            if (IsDisposed) return;
            float scale = DeviceDpi / 96F;
            layout.RowStyles[0].Height = 52 * scale; layout.RowStyles[3].Height = 48 * scale; UpdateToolsHeight();
            workspaceSplit.SplitterWidth = Math.Max(4, (int)Math.Round(8 * scale));
            workspaceSplit.Panel1MinSize = (int)Math.Round(460 * scale); workspaceSplit.Panel2MinSize = (int)Math.Round(320 * scale);
            int distance = workspaceSplit.ClientSize.Width - (int)Math.Round(360 * scale) - workspaceSplit.SplitterWidth;
            workspaceSplit.SplitterDistance = Math.Max(workspaceSplit.Panel1MinSize, Math.Min(distance, workspaceSplit.ClientSize.Width - workspaceSplit.Panel2MinSize - workspaceSplit.SplitterWidth));
            grid.RowTemplate.Height = (int)Math.Round(30 * scale); grid.ColumnHeadersHeight = (int)Math.Round(32 * scale);
            foreach (DataGridViewRow row in grid.Rows) row.Height = grid.RowTemplate.Height;
            grid.Columns["index"].Width = (int)Math.Round(45 * scale); grid.Columns["kind"].Width = (int)Math.Round(62 * scale); grid.Columns["state"].Width = (int)Math.Round(88 * scale);
            grid.DefaultCellStyle.Padding = new Padding((int)Math.Round(6 * scale), 0, (int)Math.Round(6 * scale), 0);
            int[] ruleHeights = { 28, 37, 0, 35, 28 };
            for (int i = 0; i < ruleHeights.Length; i++) ruleLayout.RowStyles[i].Height = (i == 2 ? Math.Min(154, Math.Max(74, rules.Count * 24 + 12)) : ruleHeights[i]) * scale;
        }
        async void AddFiles()
        { using (OpenFileDialog dialog = new OpenFileDialog { Multiselect = true, Title = "选择需要重命名的文件", Filter = "所有文件|*.*" }) if (dialog.ShowDialog(this) == DialogResult.OK) await AddPaths(dialog.FileNames); }
        async void AddFolder()
        { using (FolderBrowserDialog dialog = new FolderBrowserDialog { Description = "添加文件夹本身（导入子项请用“导入目录内容”）" }) if (dialog.ShowDialog(this) == DialogResult.OK) await AddPaths(new[] { dialog.SelectedPath }); }
        void PickCreateFolder()
        { using (FolderBrowserDialog dialog = new FolderBrowserDialog { Description = "选择创建项目的目标目录", SelectedPath = folder.Text }) if (dialog.ShowDialog(this) == DialogResult.OK) folder.Text = dialog.SelectedPath; }
        async void ImportContents()
        {
            using (FolderBrowserDialog dialog = new FolderBrowserDialog { Description = "导入该目录中的文件和文件夹" })
            {
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                bool recurse = recursive.Checked; int kind = importKind.SelectedIndex; string root = dialog.SelectedPath;
                await RunBusy("正在扫描目录…", async delegate
                {
                    List<string> paths = await Task.Run(() => Enumerate(root, recurse, kind));
                    AppendSources(paths);
                });
                Schedule();
            }
        }
        static List<string> Enumerate(string root, bool recurse, int kind)
        {
            Fs.Guard(root); List<string> result = new List<string>(); Stack<string> stack = new Stack<string>(); stack.Push(root);
            while (stack.Count > 0)
            {
                string current = stack.Pop();
                foreach (string path in Directory.EnumerateFileSystemEntries(current).OrderBy(x => x, Fs.Comparer))
                {
                    FileAttributes attr = File.GetAttributes(path); if ((attr & FileAttributes.ReparsePoint) != 0) continue;
                    bool directory = (attr & FileAttributes.Directory) != 0;
                    if (kind == 0 || (kind == 1 && !directory) || (kind == 2 && directory)) result.Add(path);
                    if (result.Count > Planner.MaxItems) throw new IOException("目录内容超过 10000 项，请缩小导入范围。");
                    if (recurse && directory) stack.Push(path);
                }
            }
            return result;
        }
        public async Task AddPaths(IEnumerable<string> paths)
        {
            List<string> copy = paths.ToList();
            try { AppendSources(copy); await RefreshPreview(); } catch (Exception ex) { Error(ex); }
        }
        void AppendSources(IEnumerable<string> paths)
        {
            List<SourceItem> pending = new List<SourceItem>(); HashSet<string> seen = new HashSet<string>(sources.Select(x => x.Path), Fs.Comparer);
            foreach (string path in paths)
            {
                string full = Fs.Normalize(path);
                if (!Fs.Exists(full)) throw new FileNotFoundException("路径不存在：" + full);
                if (seen.Add(full)) pending.Add(new SourceItem { Path = full, IsDirectory = Directory.Exists(full) });
            }
            if (sources.Count + pending.Count > Planner.MaxItems) throw new IOException("每批最多 10000 项。");
            sources.AddRange(pending);
        }
        void RemoveSelected()
        {
            HashSet<string> selected = new HashSet<string>(grid.SelectedRows.Cast<DataGridViewRow>().Select(x => Convert.ToString(x.Tag)), Fs.Comparer);
            sources.RemoveAll(x => selected.Contains(x.Path)); Schedule();
        }
        void MoveSource(int direction)
        {
            if (creating || grid.CurrentRow == null) return;
            int i = sources.FindIndex(x => Fs.Comparer.Equals(x.Path, Convert.ToString(grid.CurrentRow.Tag))), j = i + direction;
            if (i < 0) return;
            if (j < 0 || j >= sources.Count) return;
            SourceItem item = sources[i]; sources.RemoveAt(i); sources.Insert(j, item); selectAfterPreview = item.Path; Schedule();
        }
        void SortSources()
        {
            int mode = sort.SelectedIndex;
            sources.Sort((a, b) => mode == 2 ? Fs.Comparer.Compare(a.Path, b.Path) : (mode == 1 ? -1 : 1) * StrCmpLogicalW(Path.GetFileName(a.Path), Path.GetFileName(b.Path)));
            Schedule();
        }
        void Schedule()
        {
            if (busy || debounce == null || IsDisposed) return;
            if (previewCancellation != null) previewCancellation.Cancel();
            generation++; plan = null; if (execute != null) execute.Enabled = false;
            debounce.Stop(); debounce.Start();
        }
        public async Task RefreshPreview()
        {
            if (busy || IsDisposed) return;
            if (previewCancellation != null) previewCancellation.Cancel();
            System.Threading.CancellationTokenSource cancellation = new System.Threading.CancellationTokenSource();
            previewCancellation = cancellation;
            debounce.Stop(); int revision = ++generation;
            bool create = creating; string root = folder.Text, pattern = template.Text, randomSeed = seed;
            List<Rule> pipeline = rules.Select(x => x.Copy()).ToList(); List<SourceItem> input = sources.Select(x => new SourceItem { Path = x.Path, IsDirectory = x.IsDirectory }).ToList();
            List<string> createNames = createMode.SelectedIndex == 0 ? Enumerable.Repeat(pattern, (int)count.Value).ToList() : names.Lines.Where(x => !String.IsNullOrWhiteSpace(x)).ToList();
            bool directory = createKind.SelectedIndex == 1; DateTime date = planDate;
            try
            {
                status.Text = "正在生成预览…";
                OperationPlan result = await Task.Run(() => create ? Planner.Create(root, createNames, directory, pipeline, randomSeed, date, cancellation.Token) : Planner.Rename(input, pipeline, randomSeed, date, cancellation.Token));
                if (revision != generation || IsDisposed) return;
                plan = result; RenderPlan();
            }
            catch (OperationCanceledException) { }
            catch (Exception ex) { if (revision == generation) { plan = null; Error(ex); } }
            finally { if (previewCancellation == cancellation) previewCancellation = null; cancellation.Dispose(); }
        }
        void RenderPlan()
        {
            HashSet<string> selected = new HashSet<string>(grid.SelectedRows.Cast<DataGridViewRow>().Select(x => Convert.ToString(x.Tag)), Fs.Comparer);
            if (selectAfterPreview != null) { selected.Clear(); selected.Add(selectAfterPreview); selectAfterPreview = null; }
            grid.SuspendLayout(); grid.Rows.Clear();
            if (plan != null)
            {
                for (int i = 0; i < plan.Entries.Count; i++)
                {
                    PlanEntry e = plan.Entries[i]; bool error = !String.IsNullOrEmpty(e.Error);
                    int row = grid.Rows.Add(i + 1, e.IsDirectory ? "文件夹" : "文件", creating ? "待创建" : Path.GetFileName(e.Source), e.Name, error ? "有冲突" : creating ? "待创建" : e.Changed ? "待重命名" : "未变化");
                    grid.Rows[row].Tag = creating ? e.Destination : e.Source;
                    StylePlanRow(grid.Rows[row], error);
                    foreach (DataGridViewCell cell in grid.Rows[row].Cells) cell.ToolTipText = error ? e.Error : e.Source + "\r\n→ " + e.Destination;
                }
                int errors = plan.Entries.Count(x => !String.IsNullOrEmpty(x.Error));
                status.Text = !String.IsNullOrEmpty(plan.Error) ? plan.Error : plan.Entries.Count + " 项 · " + plan.ChangedCount + " 项变更 · " + errors + " 项错误" + (errors > 0 ? "，请修正规则或移除冲突项。" : "，确认预览后执行。");
                execute.Enabled = plan.Valid && plan.ChangedCount > 0 && !busy;
                grid.ClearSelection();
                DataGridViewRow current = grid.Rows.Cast<DataGridViewRow>().FirstOrDefault(x => selected.Contains(Convert.ToString(x.Tag)));
                if (current == null && grid.Rows.Count > 0) current = grid.Rows[0];
                if (current != null)
                {
                    grid.CurrentCell = current.Cells[0];
                    foreach (DataGridViewRow row in grid.Rows) row.Selected = row == current || selected.Contains(Convert.ToString(row.Tag));
                }
            }
            grid.ResumeLayout(); UpdateStats();
            emptyState.Visible = grid.Rows.Count == 0;
        }
        void UpdateStats() { stats.Text = (creating && plan != null ? plan.Entries.Count : sources.Count) + " 项 · " + rules.Count(x => x.Enabled) + " 条规则"; }
        async void ExecuteClick()
        {
            await RefreshPreview(); if (plan == null || !plan.Valid || plan.ChangedCount == 0) return;
            OperationPlan snapshot = plan;
            if (MessageBox.Show(this, "即将" + (snapshot.Create ? "创建 " : "重命名 ") + snapshot.ChangedCount + " 个项目。\r\n请确认列表中的新名称。操作完成后可撤销。", "确认批量操作", MessageBoxButtons.OKCancel, MessageBoxIcon.Question) != DialogResult.OK) return;
            await RunBusy("正在执行，请稍候…", async delegate
            {
                await Task.Run(() => engine.Execute(snapshot));
                if (!snapshot.Create) foreach (SourceItem source in sources)
                {
                    PlanEntry match = snapshot.Entries.FirstOrDefault(x => Fs.Comparer.Equals(x.Source, source.Path));
                    if (match != null) source.Path = match.Destination;
                }
                MessageBox.Show(this, "已完成 " + snapshot.ChangedCount + " 项变更。", "操作完成", MessageBoxButtons.OK, MessageBoxIcon.Information);
            });
            await RefreshPreview();
        }
        async void UndoClick()
        {
            try
            {
                Transaction last = engine.LastUndoable(); if (last == null) { MessageBox.Show(this, "没有可撤销的操作。", "撤销"); return; }
                if (MessageBox.Show(this, "撤销最近一次" + (last.Kind == "Create" ? "创建" : "重命名") + "（" + last.Entries.Count + " 项）？\r\n新建项有内容时会拒绝删除。", "确认撤销", MessageBoxButtons.OKCancel, MessageBoxIcon.Question) != DialogResult.OK) return;
                await RunBusy("正在撤销…", async delegate
                {
                    Transaction tx = await Task.Run(() => engine.UndoLast());
                    if (tx.Kind == "Rename") foreach (SourceItem source in sources)
                    {
                        PlanEntry e = tx.Entries.FirstOrDefault(x => Fs.Comparer.Equals(x.Destination, source.Path)); if (e != null) source.Path = e.Source;
                    }
                    MessageBox.Show(this, "最近一次操作已撤销。", "撤销完成");
                });
                await RefreshPreview();
            }
            catch (Exception ex) { Error(ex); }
        }
        async void RecoverClick()
        {
            await RunBusy("正在恢复中断操作…", async delegate { await Task.Run(() => engine.RecoverPending()); MessageBox.Show(this, "中断操作已恢复；已完成的操作保持现状。", "恢复完成"); });
            await RefreshPreview();
        }
        async Task RunBusy(string text, Func<Task> action)
        {
            if (busy) return; busy = true; generation++; debounce.Stop(); if (previewCancellation != null) previewCancellation.Cancel(); status.Text = text; body.Enabled = false; renameTools.Enabled = false; createTools.Enabled = false; execute.Enabled = false; UseWaitCursor = true;
            try { await action(); }
            catch (Exception ex) { Error(ex); }
            finally { busy = false; body.Enabled = true; renameTools.Enabled = true; createTools.Enabled = true; UseWaitCursor = false; }
        }
        void Error(Exception ex) { status.Text = ex.Message; MessageBox.Show(this, ex.Message, "未能完成", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
        void SavePreset()
        {
            using (SaveFileDialog dialog = new SaveFileDialog { Filter = "规则方案 (*.json)|*.json", FileName = "重命名规则.json" })
            { if (dialog.ShowDialog(this) != DialogResult.OK) return; try { Json.AtomicWrite(dialog.FileName, new Preset { Version = 1, Rules = rules }); } catch (Exception ex) { Error(ex); } }
        }
        void LoadPreset()
        {
            using (OpenFileDialog dialog = new OpenFileDialog { Filter = "规则方案 (*.json)|*.json" })
            {
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                try
                {
                    Preset preset = Json.Decode<Preset>(File.ReadAllText(dialog.FileName));
                    if (preset == null || preset.Version != 1 || preset.Rules == null || preset.Rules.Count > 100 || preset.Rules.Any(x => x == null)) throw new IOException("规则方案格式不受支持。");
                    rules.Clear(); rules.AddRange(preset.Rules); RefreshRules(rules.Count > 0 ? 0 : -1); Schedule();
                }
                catch (Exception ex) { Error(ex); }
            }
        }
        void ExportPreview()
        {
            if (plan == null || plan.Entries.Count == 0) return;
            using (SaveFileDialog dialog = new SaveFileDialog { Filter = "CSV 文件|*.csv", FileName = "重命名预览.csv" })
            {
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                try
                {
                    // Prefix formula-leading cells to make spreadsheet previews safe to open.
                    Func<string, string> csv = v => { v = v ?? ""; if (v.Length > 0 && "=+-@\t\r".IndexOf(v[0]) >= 0) v = "'" + v; return "\"" + v.Replace("\"", "\"\"") + "\""; };
                    File.WriteAllLines(dialog.FileName, new[] { "原路径,目标路径,类型,错误" }.Concat(plan.Entries.Select(e => String.Join(",", new[] { e.Source, e.Destination, e.IsDirectory ? "文件夹" : "文件", e.Error }.Select(csv)))), new System.Text.UTF8Encoding(true));
                    status.Text = "预览已导出。";
                }
                catch (Exception ex) { Error(ex); }
            }
        }
        public async Task RenderDemo(string output)
        {
            string fixture = Path.Combine(Path.GetDirectoryName(output), "demo-files"); Directory.CreateDirectory(fixture);
            string[] sample = { "IMG_20261001.JPG", "IMG_20261002.JPG", "IMG_20261003.JPG", "IMG_20261004.JPG", "IMG_20261005.JPG", "IMG_20261006.JPG", "IMG_20261007.JPG", "IMG_20261008.JPG" };
            foreach (string file in sample) { string path = Path.Combine(fixture, file); if (!File.Exists(path)) File.WriteAllText(path, "demo"); }
            await AddPaths(sample.Select(x => Path.Combine(fixture, x)));
            AddRule(new Rule { Type = "Replace", Pattern = "IMG_", Replacement = "旅行_", Target = "Name" });
            AddRule(new Rule { Type = "Case", Mode = "Lower", Target = "Extension" });
            AddRule(new Rule { Type = "Sequence", Start = 1, Step = 1, Digits = 3, Text = "_", Target = "Name", Mode = "Suffix" });
            await RefreshPreview();
            using (Bitmap bitmap = new Bitmap(Width, Height)) { DrawToBitmap(bitmap, new Rectangle(0, 0, Width, Height)); bitmap.Save(output, System.Drawing.Imaging.ImageFormat.Png); }
        }
    }
}
