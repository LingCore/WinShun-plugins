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

## 作者提交时的宿主验证说明（2026-10-24）

已下载并校验 Win顺 `v0.13.2` 官方便携版（SHA-256：`a8635855fcd13dfd204005d80bee463031e450f537780fe0407b2aab3e4da3da`），并使用独立 `--profile` 目录尝试启动。当前隔离环境中宿主窗口未稳定完成插件搜索交互，因此没有勾选“在 Win顺 里试过了”。提交内容保留了可直接放入 `%LOCALAPPDATA%\\WinShun\\plugins\\` 的开发目录和协议测试，供维护者在实际 Win顺环境中复核。

以上为作者提交时的历史记录；后续维护者验证如下。

## 维护者补测（2026-10-26）

- 原始 PowerShell 入口的 50 次协议查询通过；在声明的 512 MB Job 限额下，66 项核心测试和 46 项 UI 测试通过。
- 使用 Win顺项目现有 `wsbench --plugin ... --query "br " --runs 3`，原始 PowerShell 插件通过真实宿主启动和查询：冷启动约 2.4 秒，常驻往返约 0.1 毫秒；进程为普通中完整性令牌，并处于 Job 中。
- 按钮操作验收使用临时 WinForms 测试宿主：直接编译本插件原样 `src/*.cs`，只增加入口包装，复用 `runtime.config`，由真实 `WinShunPluginHost` 启动，并以 `initialize.dataDir` 指定独立临时数据目录。该可执行文件仅用于维护者测试，不随插件分发。
- 在上述同源码 GUI 中添加序号规则，预览并确认重命名一个包含两份测试文件的目录，然后确认撤销；核对原名称及内部文件内容恢复。
- 在独立目标目录中按模板和组合规则创建两份空文件；核对文件名、数量和大小。创建后再次预览能显示已有目标冲突。结束时无未完成事务。
- 打包使用干净 Git 快照，检查 `.wsplugin` 的 manifest、文件路径、禁止文件类型和 SHA256 与目录索引一致。

PowerShell 入口、宿主查询与同源码 GUI 操作分别验证。尚未对用户生产配置下的启动器键盘交互、所有文件选择方式及网络盘做完整验收。

