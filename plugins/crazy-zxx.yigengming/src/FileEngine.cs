using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using System.Threading;

namespace WinShun.BatchRenamer
{
    public static class Fs
    {
        public static readonly StringComparer Comparer = StringComparer.OrdinalIgnoreCase;
        [StructLayout(LayoutKind.Sequential)]
        struct FileInformation
        {
            public uint Attributes;
            public System.Runtime.InteropServices.ComTypes.FILETIME Creation, Access, Write;
            public uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
        }
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern SafeFileHandle CreateFile(string name, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool GetFileInformationByHandle(SafeFileHandle handle, out FileInformation info);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern bool CreateDirectory(string name, IntPtr security);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool SetFileInformationByHandle(SafeFileHandle handle, int informationClass, ref int information, uint size);
        static string FileId(FileInformation info) { return info.Volume.ToString("X8") + ":" + info.IndexHigh.ToString("X8") + info.IndexLow.ToString("X8"); }
        public static string Identity(string path)
        {
            using (SafeFileHandle h = CreateFile(path, 0, 7, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero))
            {
                if (h.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error(), "无法读取文件标识：" + path);
                FileInformation info;
                if (!GetFileInformationByHandle(h, out info)) throw new Win32Exception(Marshal.GetLastWin32Error());
                // NTFS name tunneling can change creation times during name swaps. The volume/file ID remains stable.
                return FileId(info);
            }
        }
        public static string Normalize(string path)
        {
            string p = Path.GetFullPath(Environment.ExpandEnvironmentVariables(path.Trim().Trim('"')));
            return p.Length > Path.GetPathRoot(p).Length ? p.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) : p;
        }
        public static bool Exists(string path) { return File.Exists(path) || Directory.Exists(path); }
        public static bool Under(string path, string parent) { return path.StartsWith(parent.TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase); }
        public static int Depth(string path) { return path.Count(c => c == '\\'); }
        public static void Guard(string path)
        {
            for (string p = path; !String.IsNullOrEmpty(p); p = Path.GetDirectoryName(p))
            {
                if (Exists(p) && (File.GetAttributes(p) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("暂不处理符号链接、联接点或其内部路径：" + p);
            }
        }
        public static void ValidateName(string name)
        {
            if (String.IsNullOrWhiteSpace(name) || name == "." || name == "..") throw new ArgumentException("名称不能为空或为 . / ..。");
            if (name.Length > 255) throw new ArgumentException("名称超过 255 个 UTF-16 字符。");
            if (name.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0) throw new ArgumentException("名称含 Windows 不允许的字符（如 \\ / : * ? \" < > |）。");
            if (name.EndsWith(" ") || name.EndsWith(".")) throw new ArgumentException("名称不能以空格或句点结尾。");
            string stem = name.Split('.')[0].TrimEnd(' ', '.').ToUpperInvariant();
            if (new[] { "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$" }.Contains(stem) ||
                System.Text.RegularExpressions.Regex.IsMatch(stem, @"^(COM|LPT)[1-9¹²³]$"))
                throw new ArgumentException("名称属于 Windows 保留设备名。");
        }
        public static void ValidateLength(string path, bool directory)
        {
            if (path.Length > (directory ? 247 : 259)) throw new PathTooLongException("完整路径过长，请缩短名称或选择更浅的目录。");
        }
        public static void Move(string from, string to, bool directory)
        {
            if (Exists(to)) throw new IOException("目标已存在，未覆盖：" + to);
            if (directory) Directory.Move(from, to); else File.Move(from, to);
        }
        public static void CreateNew(string path, bool directory)
        {
            if (directory)
            {
                // CreateDirectoryW fails atomically when an item already exists; Directory.CreateDirectory does not.
                if (!CreateDirectory(path, IntPtr.Zero)) throw new Win32Exception(Marshal.GetLastWin32Error(), "无法创建目录：" + path);
            }
            else using (FileStream stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None)) { stream.Flush(true); }
        }
        public static void DeleteEmptyFile(string path, string expectedIdentity)
        {
            // Hold an exclusive DELETE-capable handle through the empty/identity checks and deletion.
            // This prevents a writer from adding content between the check and the delete.
            using (SafeFileHandle handle = CreateFile(path, 0x80010000, 0, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero))
            {
                if (handle.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error(), "无法独占访问创建项：" + path);
                FileInformation info;
                if (!GetFileInformationByHandle(handle, out info)) throw new Win32Exception(Marshal.GetLastWin32Error());
                if (FileId(info) != expectedIdentity || info.SizeHigh != 0 || info.SizeLow != 0 || (info.Attributes & 0x410) != 0)
                    throw new IOException("创建项已改变，不能删除：" + path);
                int delete = 1;
                if (!SetFileInformationByHandle(handle, 4, ref delete, 4)) throw new Win32Exception(Marshal.GetLastWin32Error(), "无法删除空文件：" + path);
            }
        }
    }

    public static class Planner
    {
        public const int MaxItems = 10000;
        public static OperationPlan Rename(IList<SourceItem> sources, IList<Rule> rules, string seed, DateTime date, CancellationToken cancellation = default(CancellationToken))
        {
            OperationPlan plan = new OperationPlan();
            if (sources.Count > MaxItems) { plan.Error = "每批最多 10000 项。"; return plan; }
            HashSet<string> seen = new HashSet<string>(Fs.Comparer);
            foreach (SourceItem source in sources)
            {
                cancellation.ThrowIfCancellationRequested();
                PlanEntry e = new PlanEntry { Source = source.Path, IsDirectory = source.IsDirectory, Error = "" };
                plan.Entries.Add(e);
                try
                {
                    e.Source = Fs.Normalize(source.Path);
                    if (!seen.Add(e.Source)) throw new ArgumentException("源路径重复。");
                    if (!Fs.Exists(e.Source)) throw new FileNotFoundException("源项目已不存在。");
                    if (e.Source == Path.GetPathRoot(e.Source)) throw new ArgumentException("不能重命名磁盘根目录。");
                    Fs.Guard(e.Source);
                    e.IsDirectory = Directory.Exists(e.Source);
                    e.Identity = Fs.Identity(e.Source);
                    e.Name = RuleEngine.Apply(Path.GetFileName(e.Source), rules, new NameContext {
                        OriginalName = Path.GetFileName(e.Source), Parent = Path.GetFileName(Path.GetDirectoryName(e.Source)),
                        Key = e.Source, Index = plan.Entries.Count - 1, IsDirectory = e.IsDirectory, Date = date, Seed = seed, Cancellation = cancellation
                    });
                    Fs.ValidateName(e.Name);
                }
                catch (OperationCanceledException) { throw; }
                catch (Exception ex) { e.Error = ex.Message; e.Name = Path.GetFileName(e.Source); }
            }
            Dictionary<string, PlanEntry> directories = new Dictionary<string, PlanEntry>(Fs.Comparer);
            foreach (PlanEntry e in plan.Entries.Where(x => x.IsDirectory)) if (!directories.ContainsKey(e.Source)) directories.Add(e.Source, e);
            foreach (PlanEntry e in plan.Entries)
            {
                try
                {
                    e.Destination = Path.Combine(FinalParent(Path.GetDirectoryName(e.Source), directories), e.Name ?? "");
                    Fs.ValidateLength(e.Destination, e.IsDirectory);
                }
                catch (Exception ex) { e.Error = ex.Message; e.Destination = e.Source; }
            }
            Validate(plan, true, cancellation);
            return plan;
        }
        static string FinalParent(string parent, Dictionary<string, PlanEntry> dirs)
        {
            if (String.IsNullOrEmpty(parent)) return parent;
            PlanEntry e;
            if (dirs.TryGetValue(parent, out e)) return Path.Combine(FinalParent(Path.GetDirectoryName(parent), dirs), e.Name);
            string next = Path.GetDirectoryName(parent);
            if (String.IsNullOrEmpty(next)) return parent;
            return Path.Combine(FinalParent(next, dirs), Path.GetFileName(parent));
        }
        public static OperationPlan Create(string folder, IList<string> names, bool directory, IList<Rule> rules, string seed, DateTime date, CancellationToken cancellation = default(CancellationToken))
        {
            OperationPlan plan = new OperationPlan { Create = true };
            try
            {
                folder = Fs.Normalize(folder);
                if (!Directory.Exists(folder)) throw new DirectoryNotFoundException("请选择已存在的目标目录。");
                Fs.Guard(folder);
                if (names.Count > MaxItems) throw new ArgumentException("每批最多创建 10000 项。");
            }
            catch (Exception ex) { plan.Error = ex.Message; return plan; }
            for (int i = 0; i < names.Count; i++)
            {
                cancellation.ThrowIfCancellationRequested();
                PlanEntry e = new PlanEntry { Source = "", IsDirectory = directory, Error = "" };
                plan.Entries.Add(e);
                try
                {
                    string baseName = RuleEngine.Expand(names[i], names[i], new NameContext { OriginalName = names[i], Parent = Path.GetFileName(folder), Index = i, IsDirectory = directory, Date = date });
                    e.Name = RuleEngine.Apply(baseName, rules, new NameContext { OriginalName = baseName, Parent = Path.GetFileName(folder), Key = i + ":" + names[i], Index = i, IsDirectory = directory, Date = date, Seed = seed, Cancellation = cancellation });
                    Fs.ValidateName(e.Name);
                    e.Destination = Path.Combine(folder, e.Name);
                    Fs.ValidateLength(e.Destination, directory);
                }
                catch (OperationCanceledException) { throw; }
                catch (Exception ex) { e.Error = ex.Message; e.Destination = folder; e.Name = names[i]; }
            }
            Validate(plan, true, cancellation);
            return plan;
        }
        public static void Validate(OperationPlan plan, bool retainErrors, CancellationToken cancellation = default(CancellationToken))
        {
            if (!retainErrors) foreach (PlanEntry e in plan.Entries) e.Error = "";
            Dictionary<string, PlanEntry> source = new Dictionary<string, PlanEntry>(Fs.Comparer);
            foreach (PlanEntry e in plan.Entries) if (!String.IsNullOrEmpty(e.Source) && !source.ContainsKey(e.Source)) source.Add(e.Source, e);
            foreach (var group in plan.Entries.Where(x => !String.IsNullOrEmpty(x.Destination)).GroupBy(x => x.Destination, Fs.Comparer).Where(x => x.Count() > 1))
                foreach (PlanEntry e in group) e.Error = "本批次中有多个项目使用同一目标名称。";
            foreach (PlanEntry e in plan.Entries)
            {
                cancellation.ThrowIfCancellationRequested();
                if (!String.IsNullOrEmpty(e.Error)) continue;
                try
                {
                    if (!plan.Create)
                    {
                        Fs.Guard(e.Source);
                        if (!Fs.Exists(e.Source) || Fs.Identity(e.Source) != e.Identity) throw new IOException("源项目已删除或被替换，请刷新预览。");
                    }
                    string physicalTarget = plan.Create ? e.Destination : Path.Combine(Path.GetDirectoryName(e.Source), e.Name);
                    Fs.Guard(Path.GetDirectoryName(physicalTarget));
                    PlanEntry occupant;
                    if (Fs.Exists(physicalTarget) && !(source.TryGetValue(physicalTarget, out occupant) &&
                        (occupant.Changed || Fs.Comparer.Equals(occupant.Source, e.Source))))
                        throw new IOException("目标名称已被现有项目占用。");
                }
                catch (Exception ex) { e.Error = ex.Message; }
            }
        }
    }

    public sealed class MoveRecord
    {
        public string From { get; set; }
        public string To { get; set; }
        public bool IsDirectory { get; set; }
        public string Identity { get; set; }
        public bool Done { get; set; }
        public bool Reversed { get; set; }
    }
    public sealed class Transaction
    {
        public string Id { get; set; }
        public string Kind { get; set; }
        public string State { get; set; }
        public string CreatedAt { get; set; }
        public string UndoOf { get; set; }
        public int EventCount { get; set; }
        public List<PlanEntry> Entries { get; set; }
        public List<MoveRecord> Moves { get; set; }
        public Transaction() { Entries = new List<PlanEntry>(); Moves = new List<MoveRecord>(); }
    }
    public sealed class JournalEvent
    {
        public int Sequence { get; set; }
        public string Type { get; set; }
        public int Index { get; set; }
        public string Value { get; set; }
        public MoveRecord Move { get; set; }
    }
    public sealed class FileEngine
    {
        readonly string dataDir;
        public Action<int, int> Progress;
        public Action<string, string> BeforeMove; // deterministic fault injection for filesystem tests
        public FileEngine(string data) { dataDir = data; }
        string Journal(Transaction t) { return Path.Combine(dataDir, "transactions", t.Id + ".json"); }
        void Save(Transaction t) { Json.AtomicWrite(Journal(t), t); }
        void Append(Transaction tx, JournalEvent entry)
        {
            entry.Sequence = tx.EventCount + 1;
            byte[] bytes = new System.Text.UTF8Encoding(false).GetBytes(Json.Encode(entry) + "\n");
            using (FileStream stream = new FileStream(Journal(tx) + "l", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.Read))
            {
                // Discard only a torn final record left by a process/power interruption.
                long end = stream.Length;
                while (end > 0) { stream.Position = end - 1; if (stream.ReadByte() == 10) break; end--; }
                if (end != stream.Length) stream.SetLength(end);
                stream.Position = end; stream.Write(bytes, 0, bytes.Length); stream.Flush(true);
            }
            tx.EventCount = entry.Sequence;
        }
        static void Replay(Transaction tx, string file)
        {
            if (!File.Exists(file)) return;
            string content = File.ReadAllText(file);
            string[] lines = content.Split('\n');
            for (int i = 0; i < lines.Length - 1; i++)
            {
                if (lines[i].Length == 0) continue;
                JournalEvent entry = Json.Decode<JournalEvent>(lines[i]);
                if (entry.Sequence <= tx.EventCount) continue;
                if (entry.Sequence != tx.EventCount + 1) throw new IOException("恢复日志序号不连续：" + file);
                switch (entry.Type)
                {
                    case "Move": tx.Moves.Add(entry.Move); break;
                    case "Reverse": tx.Moves[entry.Index].Reversed = true; break;
                    case "PrepareCreate": tx.Entries[entry.Index].Source = entry.Value; break;
                    case "Created": tx.Entries[entry.Index].Identity = entry.Value; break;
                    default: throw new IOException("无法识别恢复日志事件：" + entry.Type);
                }
                tx.EventCount = entry.Sequence;
            }
        }
        public List<Transaction> History()
        {
            string folder = Path.Combine(dataDir, "transactions");
            List<Transaction> result = new List<Transaction>();
            if (!Directory.Exists(folder)) return result;
            foreach (string file in Directory.GetFiles(folder, "*.json"))
            {
                // Do not silently discard an unreadable recovery journal.
                Transaction tx = Json.Decode<Transaction>(File.ReadAllText(file));
                Replay(tx, file + "l"); result.Add(tx);
            }
            return result.OrderByDescending(x => x.CreatedAt, StringComparer.Ordinal).ToList();
        }
        public List<Transaction> Pending() { return History().Where(x => x.State == "Running" || x.State == "RecoveryNeeded" || x.State == "UndoRunning" || x.State == "DeletePending").ToList(); }
        public Transaction LastUndoable()
        {
            List<Transaction> history = History();
            HashSet<string> undone = new HashSet<string>(history.Where(x => x.State == "Completed" && !String.IsNullOrEmpty(x.UndoOf)).Select(x => x.UndoOf));
            return history.FirstOrDefault(x => x.State == "Completed" && String.IsNullOrEmpty(x.UndoOf) && !undone.Contains(x.Id));
        }
        FileStream AcquireLock()
        {
            Directory.CreateDirectory(dataDir);
            try { return new FileStream(Path.Combine(dataDir, "operations.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None); }
            catch (IOException ex) { throw new IOException("另一个窗口正在执行文件操作，请等待完成。", ex); }
        }
        Transaction New(OperationPlan plan, string undoOf)
        {
            return new Transaction { Id = DateTime.UtcNow.ToString("yyyyMMddHHmmssfff") + "-" + Guid.NewGuid().ToString("N").Substring(0, 8), Kind = plan.Create ? "Create" : "Rename", State = "Running", CreatedAt = DateTime.UtcNow.ToString("o"), UndoOf = undoOf, Entries = plan.Entries.Where(x => plan.Create || x.Changed).ToList() };
        }
        public Transaction Execute(OperationPlan plan) { using (AcquireLock()) return Execute(plan, null, false); }
        Transaction Execute(OperationPlan plan, string undoOf, bool undoCreate)
        {
            string protectedDir = Fs.Normalize(dataDir);
            foreach (PlanEntry e in plan.Entries)
                foreach (string path in new[] { e.Source, e.Destination }.Where(x => !String.IsNullOrEmpty(x)))
                    if (Fs.Comparer.Equals(path, protectedDir) || Fs.Under(path, protectedDir) || Fs.Under(protectedDir, path))
                        throw new IOException("不能操作插件自身的日志目录或其父目录：" + path);
            if (Pending().Count > 0) throw new IOException("存在未完成操作，请先点击“恢复中断操作”。");
            Planner.Validate(plan, true);
            if (!plan.Valid) throw new IOException("预览存在错误或文件系统已变化，请重新预览。" + Environment.NewLine + plan.Error + Environment.NewLine + String.Join(Environment.NewLine, plan.Entries.Where(x => !String.IsNullOrEmpty(x.Error)).Take(5).Select(x => x.Error)));
            if (plan.ChangedCount == 0) throw new IOException("当前没有需要执行的变更。");
            Transaction tx = New(plan, undoOf);
            if (undoCreate) tx.Kind = "UndoCreateStage";
            Save(tx); // A journal is durable before the first filesystem mutation.
            try
            {
                if (plan.Create) Create(tx); else Rename(tx);
                tx.State = undoCreate ? "DeletePending" : "Completed"; Save(tx); return tx;
            }
            catch (Exception ex)
            {
                try { Recover(tx); }
                catch (Exception rollback)
                {
                    tx.State = "RecoveryNeeded"; Save(tx);
                    throw new IOException("操作失败，回滚未能全部完成。保留了恢复日志，请先恢复中断操作。\r\n" + ex.Message + "\r\n" + rollback.Message, ex);
                }
                throw new IOException("操作失败，已回滚本次变更。\r\n" + ex.Message, ex);
            }
        }
        void Create(Transaction tx)
        {
            int done = 0;
            foreach (PlanEntry e in tx.Entries)
            {
                // Create into a private staging name first. A crash can be recovered using the move journal.
                string temp = Temporary(Path.GetDirectoryName(e.Destination));
                e.Source = temp; Append(tx, new JournalEvent { Type = "PrepareCreate", Index = done, Value = temp });
                Fs.Guard(Path.GetDirectoryName(temp));
                Fs.CreateNew(temp, e.IsDirectory);
                e.Identity = Fs.Identity(temp); Append(tx, new JournalEvent { Type = "Created", Index = done, Value = e.Identity });
                RecordMove(tx, temp, e.Destination, e.IsDirectory, e.Identity);
                if (Progress != null) Progress(++done, tx.Entries.Count);
            }
        }
        static string Temporary(string parent)
        {
            string temp;
            do { temp = Path.Combine(parent, ".wbr-" + Guid.NewGuid().ToString("N").Substring(0, 12)); } while (Fs.Exists(temp));
            Fs.ValidateLength(temp, true); return temp;
        }
        void Rename(Transaction tx)
        {
            Dictionary<PlanEntry, string> current = tx.Entries.ToDictionary(x => x, x => x.Source);
            int done = 0, total = tx.Entries.Count * 2;
            foreach (PlanEntry e in tx.Entries.OrderByDescending(x => Fs.Depth(x.Source)))
            {
                string from = current[e], to = Temporary(Path.GetDirectoryName(from));
                RecordMove(tx, from, to, e.IsDirectory, e.Identity);
                Update(current, from, to);
                if (Progress != null) Progress(++done, total);
            }
            foreach (PlanEntry e in tx.Entries.OrderBy(x => Fs.Depth(x.Destination)))
            {
                string from = current[e];
                RecordMove(tx, from, e.Destination, e.IsDirectory, e.Identity);
                Update(current, from, e.Destination);
                if (Progress != null) Progress(++done, total);
            }
        }
        static void Update(Dictionary<PlanEntry, string> paths, string from, string to)
        {
            foreach (PlanEntry e in paths.Keys.ToList())
            {
                if (Fs.Comparer.Equals(paths[e], from)) paths[e] = to;
                else if (Fs.Under(paths[e], from)) paths[e] = to + paths[e].Substring(from.Length);
            }
        }
        void RecordMove(Transaction tx, string from, string to, bool directory, string identity)
        {
            Fs.Guard(from); Fs.Guard(Path.GetDirectoryName(to));
            if (Fs.Identity(from) != identity) throw new IOException("执行期间源文件被替换，已停止。");
            MoveRecord move = new MoveRecord { From = from, To = to, IsDirectory = directory, Identity = identity };
            Append(tx, new JournalEvent { Type = "Move", Move = move }); tx.Moves.Add(move);
            if (BeforeMove != null) BeforeMove(from, to);
            Fs.Move(from, to, directory);
            move.Done = true;
        }
        public void Recover(Transaction tx)
        {
            foreach (MoveRecord move in tx.Moves.AsEnumerable().Reverse())
            {
                if (move.Reversed) continue;
                Fs.Guard(Path.GetDirectoryName(move.From)); Fs.Guard(Path.GetDirectoryName(move.To));
                bool atFrom = Fs.Exists(move.From) && Fs.Identity(move.From) == move.Identity;
                bool atTo = Fs.Exists(move.To) && Fs.Identity(move.To) == move.Identity;
                if (atTo && !Fs.Exists(move.From)) Fs.Move(move.To, move.From, move.IsDirectory);
                else if (!atFrom) throw new IOException("恢复路径被占用或文件标识不一致，请查看日志：" + move.From + " ← " + move.To);
                move.Reversed = true; Append(tx, new JournalEvent { Type = "Reverse", Index = tx.Moves.IndexOf(move) });
            }
            if (tx.Kind == "Create")
            {
                foreach (PlanEntry e in tx.Entries)
                {
                    if (String.IsNullOrEmpty(e.Source) || !Fs.Exists(e.Source)) continue;
                    if (String.IsNullOrEmpty(e.Identity)) throw new IOException("创建暂存项时发生中断，请人工核对后移走：" + e.Source);
                    DeleteCreated(e, e.Source);
                }
            }
            tx.State = "RolledBack"; Save(tx);
        }
        static void CheckEmpty(PlanEntry e, string path)
        {
            Fs.Guard(path);
            if (!Fs.Exists(path) || Fs.Identity(path) != e.Identity) throw new IOException("创建项已被删除或替换，不能自动撤销：" + path);
            if (e.IsDirectory ? Directory.EnumerateFileSystemEntries(path).Any() : new FileInfo(path).Length != 0)
                throw new IOException("创建项中已有内容，不能自动删除：" + path);
        }
        static void DeleteCreated(PlanEntry e, string path)
        {
            CheckEmpty(e, path);
            if (e.IsDirectory) Directory.Delete(path, false); else Fs.DeleteEmptyFile(path, e.Identity);
        }
        public Transaction UndoLast()
        { using (AcquireLock()) return UndoLastLocked(); }
        Transaction UndoLastLocked()
        {
            if (Pending().Count > 0) throw new IOException("请先恢复中断操作。");
            Transaction tx = LastUndoable();
            if (tx == null) throw new IOException("没有可撤销的操作。");
            if (tx.Kind == "Create")
            {
                foreach (PlanEntry e in tx.Entries) CheckEmpty(e, e.Destination);
                // Move the entire batch aside before deleting empty objects. This leaves a durable recovery path.
                OperationPlan staging = new OperationPlan();
                foreach (PlanEntry e in tx.Entries)
                {
                    string to = Temporary(Path.GetDirectoryName(e.Destination));
                    staging.Entries.Add(new PlanEntry { Source = e.Destination, Destination = to, Name = Path.GetFileName(to), IsDirectory = e.IsDirectory, Identity = e.Identity, Error = "" });
                }
                Transaction undo = Execute(staging, tx.Id, true);
                // Recheck emptiness at the staged paths, so outside writers never cause recursive deletion.
                try
                {
                    foreach (PlanEntry e in undo.Entries) CheckEmpty(e, e.Destination);
                }
                catch { Recover(undo); throw; }
                undo.Kind = "DeleteEmpty"; undo.State = "UndoRunning"; Save(undo);
                foreach (PlanEntry e in undo.Entries) DeleteCreated(e, e.Destination);
                undo.State = "Completed"; Save(undo);
                tx.State = "Undone"; Save(tx); return tx;
            }
            OperationPlan reverse = new OperationPlan();
            foreach (PlanEntry e in tx.Entries)
                reverse.Entries.Add(new PlanEntry { Source = e.Destination, Destination = e.Source, Name = Path.GetFileName(e.Source), IsDirectory = e.IsDirectory, Identity = e.Identity, Error = "" });
            // For hierarchical undo, destinations are absolute original paths. Collision checks still use the current parent.
            Execute(reverse, tx.Id, false);
            tx.State = "Undone"; Save(tx); return tx;
        }
        public void RecoverPending()
        { using (AcquireLock()) RecoverPendingLocked(); }
        void RecoverPendingLocked()
        {
            foreach (Transaction tx in Pending())
            {
                if (tx.Kind == "DeleteEmpty" || (tx.Kind == "UndoCreateStage" && tx.State == "DeletePending"))
                {
                    tx.Kind = "DeleteEmpty"; tx.State = "UndoRunning"; Save(tx);
                    foreach (PlanEntry e in tx.Entries) if (Fs.Exists(e.Destination)) DeleteCreated(e, e.Destination);
                    tx.State = "Completed"; Save(tx);
                    Transaction original = History().FirstOrDefault(x => x.Id == tx.UndoOf);
                    if (original != null) { original.State = "Undone"; Save(original); }
                }
                else Recover(tx);
            }
            // Complete the bookkeeping if a previous successful undo was interrupted just before marking its original.
            List<Transaction> history = History();
            foreach (Transaction undo in history.Where(x => x.State == "Completed" && !String.IsNullOrEmpty(x.UndoOf)))
            {
                Transaction original = history.FirstOrDefault(x => x.Id == undo.UndoOf);
                if (original != null && original.State == "Completed") { original.State = "Undone"; Save(original); }
            }
        }
    }
}
