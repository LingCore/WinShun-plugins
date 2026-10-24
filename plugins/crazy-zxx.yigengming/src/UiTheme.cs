using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace WinShun.BatchRenamer
{
    internal sealed class StudioButton : Button
    {
        bool hover, pressed;
        public bool Primary { get; set; }
        public StudioPalette Palette { get; set; }
        public StudioButton()
        {
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            UseCompatibleTextRendering = false; FlatStyle = FlatStyle.Flat;
            Palette = StudioTheme.Light;
        }
        public override Size GetPreferredSize(Size proposedSize)
        {
            Size text = TextRenderer.MeasureText(Text, Font, Size.Empty, TextFormatFlags.NoPadding | TextFormatFlags.SingleLine);
            int gap = Math.Max(12, (int)Math.Round(16 * DeviceDpi / 96.0));
            return new Size(Math.Max(MinimumSize.Width, text.Width + Padding.Horizontal + gap), Math.Max(MinimumSize.Height, text.Height + gap / 2));
        }
        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = false; pressed = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnMouseDown(MouseEventArgs e) { if (e.Button == MouseButtons.Left) pressed = true; Invalidate(); base.OnMouseDown(e); }
        protected override void OnMouseUp(MouseEventArgs e) { pressed = false; Invalidate(); base.OnMouseUp(e); }
        protected override void OnMouseCaptureChanged(EventArgs e) { pressed = false; Invalidate(); base.OnMouseCaptureChanged(e); }
        protected override void OnEnabledChanged(EventArgs e) { hover = pressed = false; Invalidate(); base.OnEnabledChanged(e); }
        protected override void OnKeyDown(KeyEventArgs e) { if (e.KeyCode == Keys.Space) { pressed = true; Invalidate(); } base.OnKeyDown(e); }
        protected override void OnKeyUp(KeyEventArgs e) { pressed = false; Invalidate(); base.OnKeyUp(e); }
        protected override void OnLostFocus(EventArgs e) { pressed = false; Invalidate(); base.OnLostFocus(e); }
        protected override void OnPaintBackground(PaintEventArgs e)
        {
            // The rounded outline leaves corners uncovered. Always erase them using the
            // parent surface, rather than Button's rectangular BackColor or the old frame.
            e.Graphics.Clear(Parent == null ? Palette.Canvas : Parent.BackColor);
        }
        protected override void OnPaint(PaintEventArgs e)
        {
            OnPaintBackground(e);
            Color fill = Enabled ? BackColor : Palette.Disabled;
            if (Enabled && (hover || pressed)) fill = Blend(fill, pressed ? Color.Black : (fill.GetBrightness() < .6F ? Color.White : Color.FromArgb(9, 118, 105)), pressed ? .08F : .07F);
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            Rectangle bounds = new Rectangle(0, 0, Width - 1, Height - 1);
            using (GraphicsPath path = Rounded(new RectangleF(.5F, .5F, Width - 1F, Height - 1F), Math.Max(4, DeviceDpi / 24)))
            using (SolidBrush brush = new SolidBrush(fill))
            {
                e.Graphics.FillPath(brush, path);
                if (FlatAppearance.BorderSize > 0)
                    using (Pen pen = new Pen(Enabled ? FlatAppearance.BorderColor : Palette.Border)) e.Graphics.DrawPath(pen, path);
            }
            // GDI text stays on the native pixel grid; shape antialiasing is independent of text rendering.
            TextRenderer.DrawText(e.Graphics, Text, Font, bounds, Enabled ? ForeColor : Palette.DisabledText, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis | TextFormatFlags.NoPadding);
            if (Focused && ShowFocusCues) ControlPaint.DrawFocusRectangle(e.Graphics, Rectangle.Inflate(bounds, -4, -4), ForeColor, fill);
        }
        static Color Blend(Color a, Color b, float amount)
        { return Color.FromArgb((int)(a.R + (b.R - a.R) * amount), (int)(a.G + (b.G - a.G) * amount), (int)(a.B + (b.B - a.B) * amount)); }
        static GraphicsPath Rounded(RectangleF r, int radius)
        {
            int d = radius * 2; GraphicsPath path = new GraphicsPath();
            path.AddArc(r.X, r.Y, d, d, 180, 90); path.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            path.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90); path.AddArc(r.X, r.Bottom - d, d, d, 90, 90); path.CloseFigure(); return path;
        }
    }
    internal sealed class StudioGrid : DataGridView
    { public StudioGrid() { DoubleBuffered = true; } }

    internal sealed class StudioComboBox : ComboBox
    {
        public StudioPalette Palette = StudioTheme.Light;
        public StudioComboBox() { DrawMode = DrawMode.OwnerDrawFixed; FlatStyle = FlatStyle.Flat; }
        protected override void OnFontChanged(EventArgs e)
        { base.OnFontChanged(e); ItemHeight = Font.Height + Math.Max(2, DeviceDpi / 48); }
        protected override void OnDrawItem(DrawItemEventArgs e)
        {
            bool selected = (e.State & DrawItemState.Selected) != 0;
            Color fill = selected ? Palette.Selection : Palette.Input;
            using (SolidBrush brush = new SolidBrush(fill)) e.Graphics.FillRectangle(brush, e.Bounds);
            string text = e.Index >= 0 && e.Index < Items.Count ? GetItemText(Items[e.Index]) : Text;
            Rectangle bounds = Rectangle.Inflate(e.Bounds, -3, 0);
            TextRenderer.DrawText(e.Graphics, text, Font, bounds, Enabled ? Palette.Ink : Palette.DisabledText, TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix);
            if ((e.State & DrawItemState.Focus) != 0) ControlPaint.DrawFocusRectangle(e.Graphics, bounds, Palette.Ink, fill);
        }
        void PaintClosed(Graphics graphics)
        {
            Color fill = Enabled ? Palette.Input : Palette.Disabled;
            using (SolidBrush brush = new SolidBrush(fill)) graphics.FillRectangle(brush, ClientRectangle);
            using (Pen pen = new Pen(Focused ? Palette.Accent : Palette.Border)) graphics.DrawRectangle(pen, 0, 0, Width - 1, Height - 1);
            int arrowWidth = Math.Max(22, DeviceDpi / 4), gap = Math.Max(4, DeviceDpi / 24);
            Rectangle text = new Rectangle(gap, 1, Math.Max(1, Width - arrowWidth - gap), Height - 2);
            TextRenderer.DrawText(graphics, Text, Font, text, Enabled ? Palette.Ink : Palette.DisabledText, TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix);
            int x = Width - arrowWidth / 2, y = Height / 2, size = Math.Max(3, DeviceDpi / 32);
            using (SolidBrush brush = new SolidBrush(Enabled ? Palette.Muted : Palette.DisabledText))
                graphics.FillPolygon(brush, new[] { new Point(x - size, y - size / 2), new Point(x + size, y - size / 2), new Point(x, y + size / 2 + 1) });
        }
        protected override void WndProc(ref Message message)
        {
            base.WndProc(ref message);
            if (message.Msg == 0x000F && IsHandleCreated)
                using (Graphics graphics = CreateGraphics()) PaintClosed(graphics);
            else if ((message.Msg == 0x0317 || message.Msg == 0x0318) && message.WParam != IntPtr.Zero)
                using (Graphics graphics = Graphics.FromHdc(message.WParam)) PaintClosed(graphics);
        }
        protected override void OnSelectedIndexChanged(EventArgs e) { base.OnSelectedIndexChanged(e); Invalidate(); }
        protected override void OnGotFocus(EventArgs e) { base.OnGotFocus(e); Invalidate(); }
        protected override void OnLostFocus(EventArgs e) { base.OnLostFocus(e); Invalidate(); }
    }

    internal sealed class StudioNumericUpDown : NumericUpDown
    {
        public StudioPalette Palette = StudioTheme.Light;
        SpinPainter spin;
        public StudioNumericUpDown() { BorderStyle = BorderStyle.FixedSingle; }
        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            foreach (Control child in Controls)
                if (!(child is TextBox)) { spin = new SpinPainter(child, this); break; }
        }
        protected override void OnHandleDestroyed(EventArgs e)
        { if (spin != null) { spin.ReleaseHandle(); spin = null; } base.OnHandleDestroyed(e); }
        internal void RefreshPalette() { Invalidate(true); }
        sealed class SpinPainter : NativeWindow
        {
            readonly Control child;
            readonly StudioNumericUpDown owner;
            public SpinPainter(Control control, StudioNumericUpDown parent) { child = control; owner = parent; AssignHandle(control.Handle); }
            void Paint(Graphics graphics)
            {
                StudioPalette p = owner.Palette; Rectangle r = child.ClientRectangle;
                using (SolidBrush brush = new SolidBrush(owner.Enabled ? p.Input : p.Disabled)) graphics.FillRectangle(brush, r);
                using (Pen pen = new Pen(p.Border)) { graphics.DrawLine(pen, 0, 0, 0, r.Height); graphics.DrawLine(pen, 0, r.Height / 2, r.Width, r.Height / 2); }
                int x = r.Width / 2, s = Math.Max(3, owner.DeviceDpi / 32);
                using (SolidBrush brush = new SolidBrush(owner.Enabled ? p.Muted : p.DisabledText))
                {
                    int y = r.Height / 4;
                    graphics.FillPolygon(brush, new[] { new Point(x - s, y + s / 2), new Point(x + s, y + s / 2), new Point(x, y - s / 2 - 1) });
                    y = r.Height * 3 / 4;
                    graphics.FillPolygon(brush, new[] { new Point(x - s, y - s / 2), new Point(x + s, y - s / 2), new Point(x, y + s / 2 + 1) });
                }
            }
            protected override void WndProc(ref Message message)
            {
                base.WndProc(ref message);
                if (message.Msg == 0x000F && child.IsHandleCreated)
                    using (Graphics graphics = child.CreateGraphics()) Paint(graphics);
                else if ((message.Msg == 0x0317 || message.Msg == 0x0318) && message.WParam != IntPtr.Zero)
                    using (Graphics graphics = Graphics.FromHdc(message.WParam)) Paint(graphics);
            }
        }
    }
}
