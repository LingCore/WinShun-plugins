using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Windows.Forms;
using WinShun.BatchRenamer;

static class UiTests
{
    [DllImport("user32.dll")] static extern IntPtr GetThreadDpiAwarenessContext();
    [DllImport("user32.dll")] static extern bool AreDpiAwarenessContextsEqual(IntPtr a, IntPtr b);
    [DllImport("user32.dll")] static extern uint GetDpiForWindow(IntPtr window);
    [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr window, int message, IntPtr wParam, IntPtr lParam);
    static int checks, exitCode;
    static T Get<T>(MainForm form, string name) { return (T)typeof(MainForm).GetField(name, BindingFlags.NonPublic | BindingFlags.Instance).GetValue(form); }
    static object Call(MainForm form, string method, params object[] args) { return typeof(MainForm).GetMethod(method, BindingFlags.NonPublic | BindingFlags.Instance).Invoke(form, args); }
    static void Check(bool value, string message) { if (!value) throw new Exception(message); checks++; Console.WriteLine("PASS UI " + message); }
    static async Task CheckPreviewToolbarResize(MainForm form)
    {
        Size original = form.Size;
        SplitContainer split = Get<SplitContainer>(form, "workspaceSplit");
        FlowLayoutPanel actions = Get<FlowLayoutPanel>(form, "fileActions");
        int originalMinimum = split.Panel1MinSize, originalDistance = split.SplitterDistance;
        bool fits = true, shiftsLeft = true; int previousLeft = Int32.MaxValue;
        try
        {
            foreach (int logicalWidth in new[] { 1360, 1260, 1160, 1060 })
            {
                form.Width = (int)Math.Round(logicalWidth * form.DeviceDpi / 96F);
                form.PerformLayout(); await Task.Delay(20);
                Control header = actions.Parent;
                Console.WriteLine("Toolbar resize: window=" + form.Width + ", preview=" + split.Panel1.ClientSize.Width + ", header=" + header.Width + ", actions=" + actions.Bounds);
                fits &= header.Right <= header.Parent.ClientSize.Width && header.Parent.Right <= split.Panel1.ClientSize.Width && actions.Left >= 0 && actions.Right <= split.Panel1.ClientSize.Width && actions.Controls.Cast<Control>().All(x => x.Right <= actions.ClientSize.Width);
                shiftsLeft &= actions.Left < previousLeft; previousLeft = actions.Left;
            }
            Check(fits, "preview actions remain within the workspace throughout window narrowing");
            Check(shiftsLeft, "preview toolbar follows the right edge and moves left as window narrows");
            split.Panel1MinSize = (int)Math.Round(100 * form.DeviceDpi / 96F);
            int required = actions.Width;
            bool boundary = true;
            foreach (int available in new[] { required + 1, required, required - 1 })
            {
                split.SplitterDistance = available; form.PerformLayout(); await Task.Delay(20);
                boundary &= actions.Parent.ClientSize.Width == available && actions.Right == available && (available >= required ? actions.Left >= 0 : actions.Left < 0);
            }
            Check(boundary, "toolbar clipping starts only when the entire preview row is narrower than its actions");
            split.SplitterDistance = required + (int)Math.Round(120 * form.DeviceDpi / 96F);
            form.PerformLayout(); await Task.Delay(20);
            Check(actions.Left > 0 && actions.Right <= split.Panel1.ClientSize.Width && actions.Controls.Cast<Control>().All(x => x.Visible && x.Right <= actions.ClientSize.Width), "widening the preview pane restores every toolbar action");
        }
        finally { form.Size = original; split.Panel1MinSize = originalMinimum; split.SplitterDistance = originalDistance; form.PerformLayout(); }
    }
    static void CheckButtonPainting()
    {
        using (Panel parent = new Panel())
        using (StudioButton button = new StudioButton { Text = "执行", Size = new Size(160, 44), Primary = true })
        using (Bitmap bitmap = new Bitmap(160, 44))
        using (Graphics graphics = Graphics.FromImage(bitmap))
        {
            parent.Controls.Add(button); graphics.Clear(Color.Magenta);
            foreach (StudioPalette palette in new[] { StudioTheme.Light, StudioTheme.Dark, StudioTheme.Light })
            {
                parent.BackColor = palette.Surface; button.Palette = palette; button.BackColor = palette.Primary;
                bool cornersClean = true;
                foreach (string state in new[] { "normal", "hover", "press", "release", "disabled", "enabled", "leave" })
                {
                    if (state == "hover") typeof(StudioButton).GetMethod("OnMouseEnter", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(button, new object[] { EventArgs.Empty });
                    if (state == "press" || state == "release") typeof(StudioButton).GetMethod(state == "press" ? "OnMouseDown" : "OnMouseUp", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(button, new object[] { new MouseEventArgs(MouseButtons.Left, 1, 10, 10, 0) });
                    if (state == "disabled" || state == "enabled") button.Enabled = state == "enabled";
                    if (state == "leave") typeof(StudioButton).GetMethod("OnMouseLeave", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(button, new object[] { EventArgs.Empty });
                    typeof(StudioButton).GetMethod("OnPaint", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(button, new object[] { new PaintEventArgs(graphics, button.ClientRectangle) });
                    foreach (Point corner in new[] { new Point(0, 0), new Point(159, 0), new Point(0, 43), new Point(159, 43) })
                        cornersClean &= bitmap.GetPixel(corner.X, corner.Y).ToArgb() == palette.Surface.ToArgb();
                    cornersClean &= bitmap.GetPixel(80, 5).ToArgb() != palette.Surface.ToArgb();
                }
                Check(cornersClean, "rounded button clears stale corners through pointer, disabled and theme states (" + (palette.Dark ? "dark" : "light") + ")");
            }
        }
    }
    [STAThread]
    public static int Main(string[] args)
    {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        Console.OutputEncoding = new System.Text.UTF8Encoding(false);
        string root = Path.Combine(CommunityHost.PluginDirectory, "tests", ".runs", "ui-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(root);
        Application.ThreadException += delegate(object sender, System.Threading.ThreadExceptionEventArgs e) { Console.Error.WriteLine(e.Exception); exitCode = 1; Application.Exit(); };
        try
        {
            bool systemDark = false;
            using (MainForm form = new MainForm(Path.Combine(root, "data"), delegate { return systemDark; }))
            {
                form.Opacity = 0; form.ShowInTaskbar = false;
                form.Shown += async delegate
                {
                    try
                    {
                        float scale = form.DeviceDpi / 96F;
                        Check(AreDpiAwarenessContextsEqual(GetThreadDpiAwarenessContext(), new IntPtr(-4)), "native thread uses PerMonitorV2 DPI awareness");
                        Check(GetDpiForWindow(form.Handle) == form.DeviceDpi, "WinForms DPI matches the native window DPI");
                        Console.WriteLine("DPI " + form.DeviceDpi + ", font=" + form.Font.SizeInPoints + "pt");
                        Check(Get<Panel>(form, "body").Height > form.ClientSize.Height * .78, "workspace occupies at least 78 percent of client height");
                        Check(Get<SplitContainer>(form, "workspaceSplit").Panel2.Width >= 320 * scale - 2, "rules pane keeps its logical width at high DPI");
                        string a = Path.Combine(root, "A.TXT"), b = Path.Combine(root, "B.TXT"); File.WriteAllText(a, "A"); File.WriteAllText(b, "B");
                        await form.AddPaths(new[] { a, b });
                        Check(Get<DataGridView>(form, "grid").Rows.Count == 2, "import creates two preview rows");
                        DataGridView grid = Get<DataGridView>(form, "grid"); grid.CurrentCell = grid.Rows[1].Cells[0]; grid.ClearSelection(); grid.Rows[1].Selected = true;
                        Call(form, "MoveSource", -1); await form.RefreshPreview();
                        Check(Get<OperationPlan>(form, "plan").Entries[0].Source == b && Convert.ToString(grid.CurrentRow.Tag) == b, "source reorder keeps the moved item selected");
                        Call(form, "MoveSource", 1); await form.RefreshPreview();
                        form.AddRule(new Rule()); await form.RefreshPreview();
                        Check(Get<OperationPlan>(form, "plan").Entries[0].Name == "A_001.TXT", "rule edits update preview");
                        form.AddRule(new Rule { Type = "Case", Target = "Extension", Mode = "Lower" });
                        CheckedListBox list = Get<CheckedListBox>(form, "ruleList"); list.SelectedIndex = 0;
                        TextBox separator = Get<TableLayoutPanel>(form, "editor").Controls.OfType<TextBox>().Single();
                        separator.Text = "_copy_";
                        Check(!separator.IsDisposed && Get<TableLayoutPanel>(form, "editor").Controls.Contains(separator), "typing keeps parameter editor alive");
                        Check(list.SelectedIndex == 0 && list.GetItemChecked(0) && list.GetItemChecked(1), "label refresh retains selection and check states");
                        await form.RefreshPreview();
                        Check(Get<OperationPlan>(form, "plan").Entries[0].Name == "A_copy_001.txt", "multiple rules compose in the UI");
                        OperationPlan beforeTheme = Get<OperationPlan>(form, "plan"); int selectedRow = grid.CurrentRow.Index;
                        Check(form.ThemeMode == ThemePreference.System && !form.IsDarkTheme, "fresh settings follow the system theme");
                        ContextMenuStrip themeMenu = Get<ContextMenuStrip>(form, "themeMenu");
                        ((ToolStripMenuItem)themeMenu.Items[2]).PerformClick();
                        Check(form.IsDarkTheme && grid.BackgroundColor == StudioTheme.Dark.Surface && grid.DefaultCellStyle.ForeColor == StudioTheme.Dark.Ink, "manual dark theme covers preview background and text");
                        Check(((ToolStripMenuItem)themeMenu.Items[2]).Checked && themeMenu.Items.OfType<ToolStripMenuItem>().Count(x => x.Checked) == 1, "theme menu changes mode and marks exactly one preference");
                        Check(separator.BackColor == StudioTheme.Dark.Input && list.BackColor == StudioTheme.Dark.List, "dark theme covers rule inputs and list");
                        Check(Object.ReferenceEquals(beforeTheme, Get<OperationPlan>(form, "plan")) && grid.CurrentRow.Index == selectedRow && !separator.IsDisposed && separator.Text == "_copy_", "theme switching preserves preview, selection and live editor");
                        list.SelectedIndex = 1; list.SelectedIndex = 0;
                        Check(Get<TableLayoutPanel>(form, "editor").Controls.OfType<TextBox>().Single().BackColor == StudioTheme.Dark.Input, "newly rebuilt parameter editors inherit dark theme");
                        ComboBox themedCombo = Get<ComboBox>(form, "ruleType");
                        using (Bitmap rendered = new Bitmap(themedCombo.Width, themedCombo.Height))
                        {
                            themedCombo.DrawToBitmap(rendered, themedCombo.ClientRectangle);
                            Check(rendered.GetPixel(3, rendered.Height - 4).ToArgb() == StudioTheme.Dark.Input.ToArgb() && rendered.GetPixel(rendered.Width - 5, rendered.Height - 4).ToArgb() == StudioTheme.Dark.Input.ToArgb(), "native combo face and arrow area render dark without white patches");
                        }
                        NumericUpDown themedNumber = Get<TableLayoutPanel>(form, "editor").Controls.OfType<NumericUpDown>().First();
                        decimal oldNumber = themedNumber.Value; themedNumber.UpButton(); themedNumber.DownButton();
                        Check(themedNumber.Value == oldNumber && themedNumber.BackColor == StudioTheme.Dark.Input, "themed numeric spin buttons preserve native value behavior");
                        using (MainForm restored = new MainForm(Path.Combine(root, "data"), delegate { return false; }))
                            Check(restored.ThemeMode == ThemePreference.Dark && restored.IsDarkTheme, "manual theme preference survives reopening");
                        form.SetThemeMode(ThemePreference.System); systemDark = true;
                        SendMessage(form.Handle, 0x001A, IntPtr.Zero, IntPtr.Zero); await Task.Delay(80);
                        Check(form.IsDarkTheme, "system setting notification updates an open window to dark");
                        systemDark = false; SendMessage(form.Handle, 0x031A, IntPtr.Zero, IntPtr.Zero); await Task.Delay(80);
                        Check(!form.IsDarkTheme, "system theme notification updates an open window to light");
                        form.SetThemeMode(ThemePreference.Light); systemDark = true;
                        SendMessage(form.Handle, 0x001A, IntPtr.Zero, IntPtr.Zero); await Task.Delay(80);
                        Check(!form.IsDarkTheme, "manual light mode overrides system dark changes");
                        form.SetThemeMode(ThemePreference.System); Check(form.IsDarkTheme, "returning to system mode immediately reads current system theme");
                        form.SetThemeMode(ThemePreference.Light); CheckButtonPainting();
                        FlowLayoutPanel fileActions = Get<FlowLayoutPanel>(form, "fileActions");
                        Check(fileActions.Controls.Cast<Control>().All(x => x.Right <= fileActions.ClientSize.Width), "preview toolbar has no clipped actions");
                        await CheckPreviewToolbarResize(form);
                        FlowLayoutPanel addRule = (FlowLayoutPanel)Get<ComboBox>(form, "ruleType").Parent;
                        Check(addRule.Controls.Cast<Control>().All(x => x.Right <= addRule.ClientSize.Width), "rule add button fits its panel at high DPI");
                        Check(grid.RowTemplate.Height >= form.Font.Height + 6 * scale, "grid row height accommodates native font at current DPI");
                        list.SetItemChecked(1, false); await form.RefreshPreview();
                        Check(Get<OperationPlan>(form, "plan").Entries[0].Name.EndsWith(".TXT"), "checkbox disables only its own rule");
                        Call(form, "MoveRule", 1);
                        Check(list.SelectedIndex == 1 && list.GetItemChecked(1), "move rule preserves selection and enabled state");
                        Get<System.Collections.Generic.List<Rule>>(form, "rules").Clear(); Call(form, "RefreshRules", -1);
                        string output = Path.Combine(root, "output"); Directory.CreateDirectory(output);
                        Call(form, "Switch", true);
                        Get<TextBox>(form, "folder").Text = output;
                        Get<TextBox>(form, "template").Text = "文件_{n:00}_{date:yyyyMMdd}.txt";
                        Get<NumericUpDown>(form, "count").Value = 3;
                        await form.RefreshPreview();
                        OperationPlan create = Get<OperationPlan>(form, "plan");
                        Check(create.Valid && create.Create && create.Entries.Count == 3, "creation tab uses template and count");
                        Check(create.Entries[0].Name.StartsWith("文件_01_"), "creation expands numbered template");
                        File.WriteAllText(create.Entries[1].Destination, "existing"); await form.RefreshPreview();
                        Check(!Get<OperationPlan>(form, "plan").Valid && !Get<Button>(form, "execute").Enabled, "collision disables execute");
                        form.SetThemeMode(ThemePreference.Dark);
                        Check(grid.Rows[1].DefaultCellStyle.BackColor == StudioTheme.Dark.ErrorBackground && grid.Rows[1].Cells["state"].Style.ForeColor == StudioTheme.Dark.Error && Get<ComboBox>(form, "createKind").BackColor == StudioTheme.Dark.Input, "dark creation mode retains readable conflict highlights and controls");
                        form.SetThemeMode(ThemePreference.Light);
                        File.Delete(create.Entries[1].Destination);
                        Get<ComboBox>(form, "createMode").SelectedIndex = 1;
                        Get<TextBox>(form, "names").Text = "一.txt\r\n\r\n二.txt\r\n三.txt";
                        await form.RefreshPreview();
                        Check(Get<OperationPlan>(form, "plan").Entries.Count == 3, "line creation ignores empty lines");
                        Get<ComboBox>(form, "createKind").SelectedIndex = 1; await form.RefreshPreview();
                        Check(Get<OperationPlan>(form, "plan").Entries.All(x => x.IsDirectory), "folder creation uses folder operations");
                        Get<ComboBox>(form, "createMode").SelectedIndex = 0; Get<ComboBox>(form, "createKind").SelectedIndex = 0;
                        Get<TextBox>(form, "template").Text = "项目_{n:000}.txt"; Get<NumericUpDown>(form, "count").Value = 8;
                        form.AddRule(new Rule { Type = "Insert", Mode = "Prefix", Text = "资料_" }); await form.RefreshPreview();
                        Check(Get<OperationPlan>(form, "plan").Entries[0].Name == "资料_项目_001.txt", "creation tab also applies rename rules");
                        Control ruleOrder = Get<TableLayoutPanel>(form, "ruleLayout").GetControlFromPosition(0, 3);
                        Check(ruleOrder.Controls.Cast<Control>().All(x => x.Bottom <= ruleOrder.ClientSize.Height), "rule reorder and remove buttons retain complete bottom borders");
                        if (args.Length > 0)
                        {
                            string screenshot = Path.GetFullPath(args[0]); Directory.CreateDirectory(Path.GetDirectoryName(screenshot));
                            using (Bitmap bitmap = new Bitmap(form.Width, form.Height)) { form.DrawToBitmap(bitmap, new Rectangle(0, 0, form.Width, form.Height)); bitmap.Save(screenshot); }
                            form.SetThemeMode(ThemePreference.Dark);
                            using (Bitmap bitmap = new Bitmap(form.Width, form.Height)) { form.DrawToBitmap(bitmap, new Rectangle(0, 0, form.Width, form.Height)); bitmap.Save(Path.Combine(Path.GetDirectoryName(screenshot), "create-preview-dark.png")); }
                            form.SetThemeMode(ThemePreference.Light);
                        }
                        form.Size = form.MinimumSize; form.PerformLayout(); await form.RefreshPreview();
                        Check(Get<Button>(form, "execute").Width >= 100 * scale && Get<DataGridView>(form, "grid").Width >= 400 * scale, "minimum window retains usable preview and execute controls");
                        Check(Get<ComboBox>(form, "ruleType").Parent.Controls.Cast<Control>().All(x => x.Right <= x.Parent.ClientSize.Width), "minimum window retains fully visible rule controls");
                        Check(Get<Button>(form, "execute").Parent.Controls.Cast<Control>().All(x => x.Right <= x.Parent.ClientSize.Width), "footer execute, undo and more buttons remain fully visible");
                        Console.WriteLine("RESULT " + checks + " UI checks passed");
                    }
                    catch (Exception ex) { Console.Error.WriteLine(ex); exitCode = 1; }
                    finally { form.Close(); }
                };
                Application.Run(form);
            }
        }
        catch (Exception ex) { Console.Error.WriteLine(ex); exitCode = 1; }
        if (exitCode == 0) Directory.Delete(root, true);
        return exitCode;
    }
}
