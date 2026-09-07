# JLC Auto Sign

使用 `X-JLC-AccessToken` 自动完成嘉立创金豆签到。签到结果始终输出到运行日志，也可以选择通过 [Server 酱](https://sct.ftqq.com/) 推送到微信。

## 功能

- 支持多个嘉立创账号的金豆签到
- 签到前检测 Token 是否有效
- 失败后最多额外重试 3 次
- 所有账号的签到结果都会输出到运行日志
- 使用一个可选的 Server 酱 `SEND_KEY` 汇总推送
- 任一账号最终失败时，通知标题为 `jlc签到失败`

## GitHub Actions 配置

本地运行时，直接编辑根目录的 `config.py`：

| 字段 | 说明 |
| --- | --- |
| `ACCOUNTS` | 每个账号的 `token` 与 `customer_code`（客编） |
| `SEND_KEY` | 可选。一个 Server 酱 SendKey，用于接收所有账号的汇总通知；留空则不推送微信 |

示例：

```python
ACCOUNTS = [
    {"token": "token账号1", "customer_code": "客编1"},
    {"token": "token账号2", "customer_code": "客编2"},
]

# 留空时仅记录签到日志，不推送微信。
SEND_KEY = "SCTxxxxxxxx"
```

`config.py` 已被 Git 忽略，不会被提交。需要重新创建时，可复制 `config.example.py`。

## 通过 F12 获取 Token

1. 在 Chrome 登录 [m.jlc.com](https://m.jlc.com)。
2. 按 `F12` 打开开发者工具，选择 `Network`。
3. 刷新页面或进入“我的”，选中任意 `m.jlc.com` 接口请求，例如 `selectPersonalAssetsInfo` 或 `signIn`。
4. 在 `Headers -> Request Headers` 中找到 `X-JLC-AccessToken`。
5. 仅复制冒号后的值，填入对应账号的 `ACCOUNTS` 项。

Token 不在 Local Storage 时，可以在 Console 输入以下代码，再点击一次页面按钮触发请求。代码会把请求头中的 token 输出并复制到剪贴板；不要刷新页面，否则监听会失效。

```js
const original = XMLHttpRequest.prototype.setRequestHeader;
XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
  if (name.toLowerCase() === "x-jlc-accesstoken") {
    console.log(value);
    copy(value);
  }
  return original.apply(this, arguments);
};
```

## 本地运行

```powershell
uv sync --frozen
.\.venv\Scripts\python.exe main.py
```

## 三种自动运行方式

三种方式都在每天北京时间 `00:01` 开始，并随机延后不超过 59 分钟。三者互为备选，**只能启用一种**；启用新的方式前，请停用另外两种，避免重复签到。

### GitHub Actions

在线运行时，在 `Settings -> Secrets and variables -> Actions` 配置 `TOKEN_LIST`、`CUSTOMER_CODE_LIST`（均用英文逗号分隔）和可选的 `SEND_KEY`。工作流会临时生成 `config.py`，然后随机等待并执行。日志可直接在 Actions 的运行记录中查看。

### Windows 任务计划

先完成本地 `uv` 环境与 `config.py` 配置，再在 PowerShell 运行：

```powershell
.\install_windows_task.ps1
```

任务名为 `JLC Auto Sign`，运行日志写入根目录的 `autosign.log`。

卸载 Windows 任务：

```powershell
.\uninstall_windows_task.ps1
```

### Linux 服务器

将项目复制到服务器后，在项目目录创建 Linux 的 `uv` 环境和 `config.py`，再运行：

```bash
bash install_linux_timer.sh
```

安装脚本会执行 `uv sync --frozen`，根据提交的 `uv.lock` 创建或同步 `.venv`。

定时器日志通过以下命令查看：

```bash
journalctl -u jlc-autosign.service
```

卸载 Linux 定时器：

```bash
bash uninstall_linux_timer.sh
```
