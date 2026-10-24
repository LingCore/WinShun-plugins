# 易更名验证记录

验证日期：2026-10-24

## 已完成

- `powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\main.ps1 -Validate -Screenshot .\docs\create-preview.png`
  - 66 项核心规则、文件操作、撤销、恢复和持久化测试通过。
  - 46 项 WinForms 界面测试通过。
  - 覆盖 PerMonitorV2 DPI、144 DPI 字体、浅色/深色/跟随系统主题、主题切换、按钮圆角、窗口缩窄时工具栏左移、规则组合、创建文件夹和冲突检查。
- `python tests/protocol_test.py`
  - Windows PowerShell 5.1 入口、UTF-8 JSON-RPC、`initialize`、`query`、`cancel`、`settingsChanged`、未知方法错误和 `shutdown` 通过。
  - 50 次查询通过；测试启动耗时约 0.6–0.8 秒，低于 manifest 的 10 秒限制。
  - 使用 512 MB Windows Job 限额，并按 manifest 允许本地编译器子进程。
- `python tests/windows_job.py --allow-processes powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\main.ps1 -Validate`
  - 在 512 MB Job 限额下，66 项核心测试和 46 项 UI 测试通过。
- `python tools/check.py --changed crazy-zxx.yigengming --base origin/main`
  - 0 个错误、0 条警告。

## 宿主验证说明

已下载并校验 Win顺 `v0.13.2` 官方便携版（SHA-256：`a8635855fcd13dfd204005d80bee463031e450f537780fe0407b2aab3e4da3da`），并使用独立 `--profile` 目录尝试启动。当前隔离环境中宿主窗口未稳定完成插件搜索交互，因此没有勾选“在 Win顺 里试过了”。提交内容保留了可直接放入 `%LOCALAPPDATA%\\WinShun\\plugins\\` 的开发目录和协议测试，供维护者在实际 Win顺环境中复核。

