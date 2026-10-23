# 结束进程 · Kill process

随 Win顺 安装的 PowerShell 常驻插件（`main.ps1` + SDK `WinShun.psm1`）。输入 `kill 名字`（或 `jc 名字`）列出名字里含这几个字的进程：名字、PID、内存、窗口标题，行首是程序自己的图标；`kill 1234` 按 PID 找；`kill ` 留空列出占内存最多的。Enter 结束它，Ctrl+Enter 连同子进程一起结束（`taskkill /T`），右键菜单里也有。

- 需要 **processes** 权限（起子进程：`taskkill`）。打开开关时会先看到这一条。
- 插件以你的普通权限运行：**不能结束系统进程和别的用户的进程**（Win顺 自己是管理员，但插件不是）。结束不了时底栏会说明。
- 设置项：**也列出系统进程**（留空列表时是否含 svchost 这类）、**最多列出**。
- 常驻：第一次用时 PowerShell 要几百毫秒启动，之后每次几毫秒；10 分钟不用自动退出。
- 中文进程名没问题：脚本和 SDK 都带 BOM，两端按 UTF-8 走。

**给 AI 用**：打开"AI 可以使用插件"后，`plugin_winshun_kill_kill` 列进程；结束进程这个动作要另外打开"允许 AI 执行插件动作"才会出现（`plugin_winshun_kill_kill_run`）。

---

A resident PowerShell plugin on the `WinShun.psm1` SDK: `kill name` lists matching processes (name, PID, memory, window title, the program's icon); Enter ends one, Ctrl+Enter ends it with its children. It needs the **processes** permission and runs with your normal rights, so system processes and other users' are beyond it. Settings: include system processes, rows at most. Exposed to AI as a query; the kill action only when "Allow AI to run plugin actions" is on.
