using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace WinShun.BatchRenamer
{
    static class Program
    {
        sealed class LaunchRequest { public string Command; public string Text; }
        static readonly ConcurrentQueue<LaunchRequest> queue = new ConcurrentQueue<LaunchRequest>();
        static Thread uiThread;
        static MainForm window;
        static volatile bool stopping;
        static string dataDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WinShun", "plugins", "crazy-zxx.yigengming.data");
        [STAThread]
        internal static int Main(string[] args)
        {
            CommunityHost.UseNativeDpi();
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
            Application.ThreadException += delegate(object sender, ThreadExceptionEventArgs e)
            { Console.Error.WriteLine(e.Exception); MessageBox.Show(e.Exception.Message, "易更名", MessageBoxButtons.OK, MessageBoxIcon.Warning); };
            try
            {
                if (args.Contains("--serve")) return Serve();
                if (args.Length >= 2 && args[0] == "--render-demo")
                {
                    dataDir = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(args[1])), "demo-data");
                    using (MainForm form = new MainForm(dataDir))
                    {
                        ThemePreference demoTheme;
                        if (args.Length >= 3 && Enum.TryParse(args[2], true, out demoTheme) && Enum.IsDefined(typeof(ThemePreference), demoTheme)) form.SetThemeMode(demoTheme);
                        form.ShowInTaskbar = false; form.Opacity = 0;
                        form.Shown += async delegate { try { await form.RenderDemo(Path.GetFullPath(args[1])); } finally { form.Close(); } };
                        Application.Run(form);
                    }
                    return 0;
                }
                using (MainForm form = new MainForm(dataDir))
                {
                    if (args.Length > 0 && args[0] != "--ui") form.Shown += delegate { form.OpenRequest("rename", args[0]); };
                    Application.Run(form);
                }
                return 0;
            }
            catch (Exception ex) { Console.Error.WriteLine(ex); if (!args.Contains("--serve")) MessageBox.Show(ex.Message, "易更名"); return 1; }
        }
        static Dictionary<string, object> Obj(object value) { return value as Dictionary<string, object> ?? new Dictionary<string, object>(); }
        static object Get(Dictionary<string, object> value, string key) { object result; return value.TryGetValue(key, out result) ? result : null; }
        static string Str(Dictionary<string, object> value, string key) { return Convert.ToString(Get(value, key)) ?? ""; }
        static void Reply(StreamWriter writer, object id, object result)
        { writer.WriteLine(Json.Encode(new { jsonrpc = "2.0", id = id, result = result })); writer.Flush(); }
        static void RpcError(StreamWriter writer, object id, int code, string message)
        { writer.WriteLine(Json.Encode(new { jsonrpc = "2.0", id = id, error = new { code = code, message = message } })); writer.Flush(); }
        static int Serve()
        {
            Console.SetError(new StreamWriter(Console.OpenStandardError(), new UTF8Encoding(false)) { AutoFlush = true });
            using (StreamReader reader = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false), true))
            using (StreamWriter writer = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush = true })
            {
                string line;
                while ((line = reader.ReadLine()) != null)
                {
                    if (line.Length == 0) continue;
                    object id = null; bool hasId = false;
                    try
                    {
                        Dictionary<string, object> request = Json.Decode<Dictionary<string, object>>(line);
                        if (request == null) { RpcError(writer, null, -32600, "请求必须为 JSON 对象。"); continue; }
                        hasId = request.ContainsKey("id"); id = Get(request, "id");
                        Dictionary<string, object> p = Obj(Get(request, "params"));
                        string method = Str(request, "method");
                        switch (method)
                        {
                            case "initialize":
                                string dir = Str(p, "dataDir");
                                if (!String.IsNullOrEmpty(dir)) dataDir = Path.GetFullPath(dir);
                                if (hasId) Reply(writer, id, new { protocolVersion = "1", name = "易更名" }); break;
                            case "query":
                                string command = Str(p, "command") == "create" ? "create" : "rename";
                                string query = Str(p, "text");
                                object item = new {
                                    id = "open-" + command, title = command == "create" ? "易更名 · 批量创建" : "易更名 · 批量重命名",
                                    subtitle = query.Length > 0 ? "载入路径：" + query : "文件 / 文件夹 · 组合规则 · 实时预览 · 撤销",
                                    icon = "icon.png", score = 90, valid = true, data = new { command = command, text = query }
                                };
                                if (hasId) Reply(writer, id, new { items = new[] { item }, cache = 0, rerun = 0 }); break;
                            case "action":
                                Dictionary<string, object> data = Obj(Get(Obj(Get(p, "item")), "data"));
                                string cmd = Str(data, "command"); if (cmd.Length == 0) cmd = Str(p, "command");
                                string text = Str(data, "text"); if (text.Length == 0) text = Str(p, "text");
                                Launch(cmd == "create" ? "create" : "rename", text);
                                if (hasId) Reply(writer, id, new { effects = new[] { new { type = "hide" } } }); break;
                            case "shutdown": if (hasId) Reply(writer, id, new { }); stopping = true; return 0;
                            case "cancel": case "settingsChanged": if (hasId) Reply(writer, id, new { }); break;
                            default: if (hasId) RpcError(writer, id, -32601, "未知方法：" + method); break;
                        }
                    }
                    catch (Exception ex)
                    {
                        Console.Error.WriteLine(ex);
                        RpcError(writer, id, hasId ? -32603 : -32700, hasId ? "请求处理失败：" + ex.Message : "JSON 格式无效。");
                    }
                }
            }
            stopping = true; return 0;
        }
        static void Launch(string command, string text)
        {
            queue.Enqueue(new LaunchRequest { Command = command, Text = text });
            if (uiThread != null && uiThread.IsAlive) return;
            uiThread = new Thread(delegate()
            {
                CommunityHost.UseNativeDpi();
                using (System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer { Interval = 40 })
                {
                    timer.Tick += delegate
                    {
                        if (stopping) { Application.ExitThread(); return; }
                        if (window != null && !window.IsDisposed && window.IsBusy) return;
                        LaunchRequest request;
                        while (queue.TryDequeue(out request))
                        {
                            if (window == null || window.IsDisposed) window = new MainForm(dataDir);
                            window.OpenRequest(request.Command, request.Text);
                        }
                    };
                    timer.Start(); Application.Run();
                }
            });
            uiThread.IsBackground = true; uiThread.SetApartmentState(ApartmentState.STA); uiThread.Start();
        }
    }
}
