using System;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Win32;

namespace WinShun.BatchRenamer
{
    internal enum ThemePreference { System, Light, Dark }

    internal sealed class StudioPalette
    {
        public readonly bool Dark;
        public readonly Color Canvas, Surface, Input, Ink, Muted, Accent, Primary, Border, Header, Alternate, Selection, List, Error, ErrorBackground, Disabled, DisabledText;
        public StudioPalette(bool dark)
        {
            Dark = dark;
            Canvas = Hex(dark ? 0x151B22 : 0xF3F6F9); Surface = Hex(dark ? 0x1D252F : 0xFFFFFF);
            Input = Hex(dark ? 0x26313D : 0xFFFFFF); Ink = Hex(dark ? 0xE6EDF3 : 0x1E2A36);
            Muted = Hex(dark ? 0xA5B4C3 : 0x586775); Accent = Hex(dark ? 0x6BDBCA : 0x097669);
            Primary = Hex(dark ? 0x176E65 : 0x097669); Border = Hex(dark ? 0x40505F : 0xDAE2E7);
            Header = Hex(dark ? 0x283441 : 0xEFF4F7); Alternate = Hex(dark ? 0x202A35 : 0xFAFCFD);
            Selection = Hex(dark ? 0x254B49 : 0xDEF2EC); List = Hex(dark ? 0x232E3A : 0xF7FAFC);
            Error = Hex(dark ? 0xFFB1A8 : 0xC0423E); ErrorBackground = Hex(dark ? 0x492F34 : 0xFFF2F0);
            Disabled = Hex(dark ? 0x2A333D : 0xEBEFF2); DisabledText = Hex(dark ? 0x8998A6 : 0x89939C);
        }
        static Color Hex(int value) { return Color.FromArgb((value >> 16) & 255, (value >> 8) & 255, value & 255); }
    }

    internal static class StudioTheme
    {
        public static readonly StudioPalette Light = new StudioPalette(false), Dark = new StudioPalette(true);
        public static bool ReadSystemDark()
        {
            try
            {
                using (RegistryKey key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"))
                    return key != null && Convert.ToInt32(key.GetValue("AppsUseLightTheme", 1)) == 0;
            }
            catch (System.Security.SecurityException) { return false; }
            catch (UnauthorizedAccessException) { return false; }
            catch (IOException) { return false; }
            catch (FormatException) { return false; }
            catch (InvalidCastException) { return false; }
        }
        public static ThemePreference Load(string directory)
        {
            try
            {
                string value = File.ReadAllText(Path.Combine(directory, "theme.txt")).Trim(); ThemePreference mode;
                if (Enum.TryParse(value, out mode) && Enum.IsDefined(typeof(ThemePreference), mode)) return mode;
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
            return ThemePreference.System;
        }
        public static void Save(string directory, ThemePreference mode)
        {
            Directory.CreateDirectory(directory);
            string path = Path.Combine(directory, "theme.txt"), temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                File.WriteAllText(temporary, mode.ToString());
                if (File.Exists(path)) File.Replace(temporary, path, null); else File.Move(temporary, path);
            }
            finally { if (File.Exists(temporary)) File.Delete(temporary); }
        }
        public static void ApplyTree(Control root, StudioPalette palette, Color background)
        {
            bool muted = root.ForeColor.ToArgb() == Light.Muted.ToArgb() || root.ForeColor.ToArgb() == Dark.Muted.ToArgb();
            Color fill = Equals(root.Tag, "theme-surface") ? palette.Surface : background;
            StudioButton button = root as StudioButton;
            if (button != null)
            {
                button.Palette = palette; button.BackColor = button.Primary ? palette.Primary : palette.Surface;
                button.ForeColor = button.Primary ? Color.White : palette.Ink; button.FlatAppearance.BorderColor = palette.Border;
                button.Invalidate(); return;
            }
            if (root is TextBoxBase || root is ComboBox || root is NumericUpDown) fill = palette.Input;
            else if (root is CheckedListBox) fill = palette.List;
            root.BackColor = fill; root.ForeColor = muted ? palette.Muted : palette.Ink;
            ComboBox combo = root as ComboBox;
            if (combo != null) combo.FlatStyle = FlatStyle.Flat;
            StudioComboBox studioCombo = root as StudioComboBox;
            if (studioCombo != null) { studioCombo.Palette = palette; studioCombo.Invalidate(); }
            StudioNumericUpDown number = root as StudioNumericUpDown;
            if (number != null) { number.Palette = palette; number.RefreshPalette(); }
            CheckBox check = root as CheckBox;
            if (check != null) check.FlatStyle = FlatStyle.Flat;
            // Native child windows of numeric inputs manage their own layout and colors.
            if (root is NumericUpDown) return;
            foreach (Control child in root.Controls) ApplyTree(child, palette, fill);
        }
        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr window, int attribute, ref int value, int size);
        public static void ApplyTitleBar(IntPtr handle, bool dark)
        {
            try { int value = dark ? 1 : 0; if (DwmSetWindowAttribute(handle, 20, ref value, sizeof(int)) != 0) DwmSetWindowAttribute(handle, 19, ref value, sizeof(int)); }
            catch (DllNotFoundException) { }
            catch (EntryPointNotFoundException) { }
        }
    }

    internal sealed class StudioMenuColors : ProfessionalColorTable
    {
        readonly StudioPalette p;
        public StudioMenuColors(StudioPalette palette) { p = palette; UseSystemColors = false; }
        public override Color ToolStripDropDownBackground { get { return p.Surface; } }
        public override Color MenuBorder { get { return p.Border; } }
        public override Color MenuItemBorder { get { return p.Selection; } }
        public override Color MenuItemSelected { get { return p.Selection; } }
        public override Color ImageMarginGradientBegin { get { return p.Surface; } }
        public override Color ImageMarginGradientMiddle { get { return p.Surface; } }
        public override Color ImageMarginGradientEnd { get { return p.Surface; } }
        public override Color CheckBackground { get { return p.Selection; } }
        public override Color CheckSelectedBackground { get { return p.Selection; } }
        public override Color CheckPressedBackground { get { return p.Selection; } }
        public override Color SeparatorDark { get { return p.Border; } }
        public override Color SeparatorLight { get { return p.Surface; } }
    }
    internal sealed class StudioMenuRenderer : ToolStripProfessionalRenderer
    {
        readonly StudioPalette p;
        public StudioMenuRenderer(StudioPalette palette) : base(new StudioMenuColors(palette)) { p = palette; RoundedEdges = false; }
        protected override void OnRenderArrow(ToolStripArrowRenderEventArgs e) { e.ArrowColor = p.Ink; base.OnRenderArrow(e); }
        protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e) { e.TextColor = e.Item.Enabled ? p.Ink : p.DisabledText; base.OnRenderItemText(e); }
        protected override void OnRenderItemCheck(ToolStripItemImageRenderEventArgs e)
        {
            Rectangle r = e.ImageRectangle;
            using (Pen pen = new Pen(p.Accent, 2))
                e.Graphics.DrawLines(pen, new[] { new Point(r.Left + 2, r.Top + r.Height / 2), new Point(r.Left + r.Width / 2 - 1, r.Bottom - 4), new Point(r.Right - 2, r.Top + 3) });
        }
    }
}
