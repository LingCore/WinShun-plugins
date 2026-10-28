using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Web.Script.Serialization;

namespace WinShun.BatchRenamer
{
    public sealed class Rule
    {
        public bool Enabled { get; set; }
        public string Type { get; set; }
        public string Target { get; set; }
        public string Mode { get; set; }
        public string Text { get; set; }
        public string Pattern { get; set; }
        public string Replacement { get; set; }
        public string Charset { get; set; }
        public long Start { get; set; }
        public long Step { get; set; }
        public int Digits { get; set; }
        public int Position { get; set; }
        public int Length { get; set; }
        public bool IgnoreCase { get; set; }
        public Rule()
        {
            Enabled = true; Type = "Sequence"; Target = "Name"; Mode = "Suffix";
            Text = "_"; Pattern = ""; Replacement = "";
            Charset = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789";
            Start = 1; Step = 1; Digits = 3; Length = 6;
        }
        public Rule Copy() { return (Rule)MemberwiseClone(); }
        public string Label
        {
            get
            {
                string title;
                switch (Type)
                {
                    case "Sequence": title = "序号 · " + Start + " / 步长 " + Step + " / " + Digits + " 位"; break;
                    case "Case": title = "大小写 · " + Labels.Case(Mode); break;
                    case "Replace": title = "替换 · " + Pattern + " → " + Replacement; break;
                    case "Insert": title = "插入 · " + Text; break;
                    case "Random": title = "随机字符 · " + Length + " 位"; break;
                    case "Slice": title = "截取 · " + Position + " 起 / " + Length + " 字"; break;
                    case "Regex": title = "正则 · " + Pattern; break;
                    case "Template": title = "模板 · " + Text; break;
                    default: title = "去除首尾空白"; break;
                }
                return title + "  [" + Labels.Target(Target) + "]";
            }
        }
        public override string ToString() { return Label; }
        public static Rule New(string type)
        {
            Rule r = new Rule { Type = type };
            if (type == "Case") r.Mode = "Upper";
            if (type == "Slice") { r.Mode = "Keep"; r.Length = 5; }
            if (type == "Regex") { r.Mode = "Replace"; r.Pattern = @"^(.*)$"; r.Replacement = "$1"; }
            if (type == "Replace") r.Pattern = "旧文字";
            if (type == "Insert") { r.Mode = "Prefix"; r.Text = "前缀_"; }
            if (type == "Template") { r.Text = "{name}_{n:000}"; r.Target = "Name"; }
            return r;
        }
    }

    public static class Labels
    {
        public static string Target(string value) { return value == "FullName" ? "完整名称" : value == "Extension" ? "扩展名" : "主名称"; }
        public static string Case(string value)
        {
            switch (value) { case "Lower": return "全部小写"; case "Title": return "单词首字母大写"; case "Swap": return "大小写反转"; default: return "全部大写"; }
        }
    }

    public sealed class NameContext
    {
        public string OriginalName;
        public string Parent;
        public string Key;
        public int Index;
        public bool IsDirectory;
        public DateTime Date;
        public string Seed;
        public System.Threading.CancellationToken Cancellation;
    }
    public sealed class SourceItem
    {
        public string Path { get; set; }
        public bool IsDirectory { get; set; }
    }
    public sealed class PlanEntry
    {
        public string Source { get; set; }
        public string Destination { get; set; }
        public string Name { get; set; }
        public bool IsDirectory { get; set; }
        public string Identity { get; set; }
        public string Error { get; set; }
        public bool Changed { get { return !String.Equals(Source, Destination, StringComparison.Ordinal); } }
    }
    public sealed class OperationPlan
    {
        public bool Create { get; set; }
        public List<PlanEntry> Entries { get; set; }
        public string Error { get; set; }
        public OperationPlan() { Entries = new List<PlanEntry>(); Error = ""; }
        public bool Valid { get { return String.IsNullOrEmpty(Error) && Entries.Count > 0 && Entries.All(x => String.IsNullOrEmpty(x.Error)); } }
        public int ChangedCount { get { return Entries.Count(x => Create || x.Changed); } }
    }
    public sealed class Preset
    {
        public int Version { get; set; }
        public List<Rule> Rules { get; set; }
    }
    public static class Json
    {
        public static string Encode(object value) { return new JavaScriptSerializer { MaxJsonLength = 16000000, RecursionLimit = 100 }.Serialize(value); }
        public static T Decode<T>(string value) { return new JavaScriptSerializer { MaxJsonLength = 16000000, RecursionLimit = 100 }.Deserialize<T>(value); }
        public static void AtomicWrite(string path, object value)
        {
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path));
            string temp = path + ".new";
            byte[] bytes = new System.Text.UTF8Encoding(false).GetBytes(Encode(value));
            using (FileStream stream = new FileStream(temp, FileMode.Create, FileAccess.Write, FileShare.None))
            { stream.Write(bytes, 0, bytes.Length); stream.Flush(true); }
            if (File.Exists(path)) File.Replace(temp, path, null);
            else File.Move(temp, path);
        }
    }
}
