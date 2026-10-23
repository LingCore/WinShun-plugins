# 快捷跳转 · Go to

零代码插件：`run` 的四种写法各一个例子。

| 命令 | `run` | 做什么 |
|---|---|---|
| `code D:\项目` | `program` + `args: "%s"` | 用 VS Code 打开（路径按你的安装改；没装就报打不开） |
| `np 笔记.txt` | `program` | 记事本 |
| `dl `、`desk ` | `folder` | 跳到下载 / 桌面文件夹（`%USERPROFILE%` 这类变量会展开） |
| `pdf 合同`、`img 截图` | `search` | 保存的搜索：等于在搜索框输入 `ext:pdf 合同` |
| `go 文档` | `items` | 固定清单，输入的词用来筛选 |

程序永远以你的普通权限启动，不会提权。要加自己的：复制这个文件夹到 `%LOCALAPPDATA%\WinShun\plugins\`，改 `id`，照样子加命令。

---

A zero-code plugin with one example of each `run`: `program` (+ `args` with `%s`), `folder`, `search` (a saved query, as if typed into the box) and `items` (a fixed list the words filter). Programs start with your normal rights, never elevated. Edit the VS Code path to match your install.
