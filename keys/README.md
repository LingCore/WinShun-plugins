# keys/：插件列表的验签公钥

`index.json.sig` 是 `index.json` 的数字签名，Win顺 用这里的公钥（`<id>.pub`，一行 128 位十六进制）检查列表有没有被人换过。验得过，才会在后台自动更新插件；验不过，只提示，不自动装。

私钥不在仓库里：只放在 GitHub 的 Environment `index-signing`（secret `INDEX_SIGNING_KEYS`，只允许 main 分支用）和一份离线加密备份里。`*.pem` 已经写进 `.gitignore`，不要提交。

## 换钥匙（计划内）

1. 生成新钥匙 B：`python tools/sign_index.py keygen <新id> --out <仓库外的文件夹>`，把 `keys/<新id>.pub` 提交。
2. 发一个同时认 A 和 B 的 Win顺 版本。
3. secret 里放 A 和 B 两个 PEM，`.sig` 里就有两个签名：旧版用 A 验，新版任一把都行。
4. 旧版基本都升级了（或半年后），从 secret 和 Win顺 里去掉 A，把 `keys/A.pub` 移到 `keys/retired/`。

## 私钥丢了

生成新钥匙，照上面的步骤走。没升级的旧版在这期间只会提示，不会出错。

## 私钥泄露了

马上从 secret 里去掉这把钥匙，发布只认新钥匙的 Win顺。还没升级的旧版仍然信任旧钥匙，但攻击者还得能控制用户的网络或镜像，而且只能：更新用户已经装的插件、只能升不能降、权限不能超过用户已同意的、受 `minWinShun` 限制。
