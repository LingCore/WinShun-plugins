using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace WinShun.BatchRenamer
{
    public static class RuleEngine
    {
        public static string[] Elements(string s)
        {
            List<string> result = new List<string>();
            TextElementEnumerator e = StringInfo.GetTextElementEnumerator(s ?? "");
            while (e.MoveNext()) result.Add((string)e.Current);
            return result.ToArray();
        }
        public static void SplitName(string full, bool directory, out string name, out string extension)
        {
            int dot = directory ? -1 : full.LastIndexOf('.');
            if (dot <= 0) { name = full; extension = ""; }
            else { name = full.Substring(0, dot); extension = full.Substring(dot + 1); }
        }
        public static string Apply(string full, IList<Rule> rules, NameContext context)
        {
            if (rules == null || rules.Count > 100) throw new ArgumentException("规则数量不能超过 100。");
            for (int i = 0; i < rules.Count; i++)
            {
                context.Cancellation.ThrowIfCancellationRequested();
                Rule r = rules[i];
                if (!r.Enabled || (context.IsDirectory && r.Target == "Extension")) continue;
                try
                {
                    string name, ext;
                    SplitName(full, context.IsDirectory, out name, out ext);
                    string input = r.Target == "FullName" ? full : r.Target == "Extension" ? ext : name;
                    string value = Transform(input, r, context, i);
                    if (value.Length > 1024) throw new ArgumentException("规则结果过长。");
                    full = r.Target == "FullName" ? value : r.Target == "Extension" ? name + (value.Length == 0 ? "" : "." + value) : value + (ext.Length == 0 ? "" : "." + ext);
                }
                catch (OperationCanceledException) { throw; }
                catch (Exception ex) { throw new ArgumentException("规则 " + (i + 1) + "（" + r.Label + "）：" + ex.Message, ex); }
            }
            return full;
        }
        static string Transform(string s, Rule r, NameContext c, int ruleIndex)
        {
            switch (r.Type)
            {
                case "Sequence":
                    if (r.Digits < 1 || r.Digits > 18) throw new ArgumentException("序号位数须在 1–18 之间。");
                    long number = checked(r.Start + checked(r.Step * c.Index));
                    return Place(s, number.ToString("D" + r.Digits, CultureInfo.InvariantCulture), r, r.Text ?? "");
                case "Case":
                    if (r.Mode == "Lower") return s.ToLowerInvariant();
                    if (r.Mode == "Title") return CultureInfo.InvariantCulture.TextInfo.ToTitleCase(s.ToLowerInvariant());
                    if (r.Mode == "Swap") return String.Concat(Elements(s).Select(x => x == x.ToUpperInvariant() ? x.ToLowerInvariant() : x.ToUpperInvariant()));
                    return s.ToUpperInvariant();
                case "Replace":
                    if (String.IsNullOrEmpty(r.Pattern)) throw new ArgumentException("查找文字不能为空。");
                    if (!r.IgnoreCase) return s.Replace(r.Pattern, r.Replacement ?? "");
                    return Regex.Replace(s, Regex.Escape(r.Pattern), m => r.Replacement ?? "", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(200));
                case "Insert": return Place(s, r.Text ?? "", r, "");
                case "Random":
                    if (r.Length < 1 || r.Length > 128) throw new ArgumentException("随机长度须在 1–128 之间。");
                    string[] chars = Elements(r.Charset).Distinct().ToArray();
                    if (chars.Length < 2 || chars.Length > 256) throw new ArgumentException("字符集须包含 2–256 个不同字符。");
                    StringBuilder random = new StringBuilder();
                    int counter = 0;
                    using (HMACSHA256 hash = new HMACSHA256(Encoding.UTF8.GetBytes(c.Seed)))
                    {
                        while (Elements(random.ToString()).Length < r.Length)
                        {
                            byte[] buffer = hash.ComputeHash(Encoding.UTF8.GetBytes(c.Key + "\0" + ruleIndex + "\0" + counter++));
                            foreach (byte b in buffer)
                            {
                                if (b >= (256 / chars.Length) * chars.Length) continue;
                                random.Append(chars[b % chars.Length]);
                                if (Elements(random.ToString()).Length == r.Length) break;
                            }
                        }
                    }
                    return Place(s, random.ToString(), r, r.Text ?? "");
                case "Slice":
                    if (r.Length < 0) throw new ArgumentException("截取长度不能为负数。");
                    string[] elements = Elements(s);
                    int start = Offset(r.Position, elements.Length);
                    int count = Math.Min(r.Length, elements.Length - start);
                    return r.Mode == "Remove" ? String.Concat(elements.Take(start).Concat(elements.Skip(start + count))) : String.Concat(elements.Skip(start).Take(count));
                case "Regex":
                    if (String.IsNullOrEmpty(r.Pattern)) throw new ArgumentException("正则表达式不能为空。");
                    Regex regex = new Regex(r.Pattern, RegexOptions.CultureInvariant | (r.IgnoreCase ? RegexOptions.IgnoreCase : RegexOptions.None), TimeSpan.FromMilliseconds(200));
                    if (r.Mode == "Extract") { Match match = regex.Match(s); return match.Success ? match.Result(r.Replacement ?? "$0") : s; }
                    return regex.Replace(s, r.Replacement ?? "");
                case "Template": return Expand(r.Text ?? "", s, c);
                case "Trim": return s.Trim();
                default: throw new ArgumentException("未知规则类型：" + r.Type);
            }
        }
        static int Offset(int p, int length) { return p < 0 ? Math.Max(0, length + p) : Math.Min(p, length); }
        static string Place(string s, string text, Rule r, string separator)
        {
            if (r.Mode == "Replace") return text;
            if (r.Mode == "Prefix") return text + separator + s;
            if (r.Mode == "Position")
            {
                string[] elements = Elements(s); int p = Offset(r.Position, elements.Length);
                return String.Concat(elements.Take(p)) + text + String.Concat(elements.Skip(p));
            }
            return s + separator + text;
        }
        public static string Expand(string template, string current, NameContext c)
        {
            string original, ext;
            SplitName(c.OriginalName, c.IsDirectory, out original, out ext);
            return Regex.Replace(template, @"\{(name|original|ext|parent|n|date)(?::([^{}]+))?\}", m =>
            {
                string format = m.Groups[2].Value;
                switch (m.Groups[1].Value)
                {
                    case "name": return current;
                    case "original": return original;
                    case "ext": return ext;
                    case "parent": return c.Parent;
                    case "n": return (c.Index + 1).ToString(format.Length > 0 ? format : "0", CultureInfo.InvariantCulture);
                    default: return c.Date.ToString(format.Length > 0 ? format : "yyyyMMdd", CultureInfo.InvariantCulture);
                }
            }, RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(200));
        }
    }
}
