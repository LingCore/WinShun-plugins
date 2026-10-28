## 这个 PR 做什么

（新收录 / 更新哪个插件，一两句话；插件仓库的链接）

## 自查

- [ ] 插件在我自己的公开仓库里，正式发布的 Release 上有 `<id>-<版本>.wsplugin`（用 [template/release.yml](https://github.com/LingCore/WinShun-plugins/blob/main/template/release.yml) 发最省事）
- [ ] `plugins/<id>.json` 是 `python tools/entry.py <包的网址>` 生成的，或者从发布工作流的运行摘要里复制的，生成的字段没有手改
- [ ] 这个 PR 只改了 `plugins/<id>.json`（老插件：只改了 `legacy/<id>/` 里的文件，并且升了 `version`）
- [ ] 插件仓库里有 `README.md`：它做什么、要哪些权限、为什么要
- [ ] 只申请用得到的权限；`network`、`processes`、`files:write` 等我在 README 里解释了
- [ ] 我在 Win顺 里试过了（或用 `wsbench --plugin <文件夹> --query "..."`），能出结果、Enter 能用
- [ ] `plugin.json` 里写了 `author` 和 `license`，代码我有权按这个许可证放出来

## 权限

（和 plugin.json 里的 `permissions` 一致；没有就写"无"）
