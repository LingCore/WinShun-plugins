## 这个 PR 做什么

（新增 / 更新哪个插件，一两句话）

## 自查

- [ ] 我在 Win顺 里试过了（或用 `wsbench --plugin <文件夹> --query "..."`），能出结果、Enter 能用
- [ ] `python tools/check.py` 通过
- [ ] 文件夹名和 `plugin.json` 的 `id` 一样，写成 `作者.名字`
- [ ] 文件夹里有 `README.md`：说明它做什么、要哪些权限、为什么要
- [ ] 只申请用得到的权限；`network`、`processes`、`files:write` 等我在 README 里解释了
- [ ] 没有二进制文件（exe、dll、bat 等），也没有大于 1 MB 的文件
- [ ] `plugin.json` 里写了 `author` 和 `license`，代码我有权按这个许可证放出来
- [ ] 是更新的话，`version` 已经升高
- [ ] PowerShell 脚本存成了带 BOM 的 UTF-8

## 权限

（和 plugin.json 里的 `permissions` 一致；没有就写"无"）
