using System;
using System.Reflection;
using System.Runtime.InteropServices;

namespace WinShun.BatchRenamer
{
    // The PowerShell entry loads this library in an AppDomain with our own .NET 4.8
    // configuration. No binary is shipped or downloaded, and no UI subprocess is used.
    public sealed class CommunityHost : MarshalByRefObject
    {
        internal static string PluginDirectory;
        public void Initialize(string directory) { PluginDirectory = directory; }
        [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
        internal static void UseNativeDpi()
        {
            try { SetThreadDpiAwarenessContext(new IntPtr(-4)); }
            catch (EntryPointNotFoundException) { }
        }
        public int Run(string[] arguments) { return Program.Main(arguments); }
        public int Validate(string screenshot)
        {
            UseNativeDpi();
            Assembly assembly = typeof(CommunityHost).Assembly;
            Type core = assembly.GetType("CoreTests", true), ui = assembly.GetType("UiTests", true);
            int result = (int)core.GetMethod("Main", BindingFlags.Public | BindingFlags.Static).Invoke(null, null);
            if (result != 0) return result;
            string[] args = String.IsNullOrEmpty(screenshot) ? new string[0] : new[] { screenshot };
            return (int)ui.GetMethod("Main", BindingFlags.Public | BindingFlags.Static).Invoke(null, new object[] { args });
        }
        public override object InitializeLifetimeService() { return null; }
    }
}
