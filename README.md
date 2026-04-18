# 📬 JLC Auto Sign

支持通过 `X-JLC-AccessToken` 执行嘉立创积分/金豆签到，并通过 [Server 酱](https://sct.ftqq.com/) 推送汇总消息。

---

## ✨ 功能

- 支持多账号签到
- 支持积分/金豆签到
- 默认直接使用 `TOKEN_LIST`
- 内置 Token 状态检测，可提示 token 是否失效
- 保留账号密码驱动模式代码，但默认不启用
- 按 `SEND_KEY_LIST` 分组推送 Server 酱通知

---

## 🔧 推荐配置

推荐直接使用 token 模式：

| 变量名 | 说明 |
| --- | --- |
| `TOKEN_LIST` | 嘉立创 `X-JLC-AccessToken`，多个 token 用英文逗号分隔 |
| `SEND_KEY_LIST` | Server 酱 SendKey，多个值用英文逗号分隔，按账号索引匹配 |

脚本会对每个账号执行以下流程：

1. 检测 token 是否有效
2. 如果 token 有效，执行积分/金豆签到
3. 查询当前金豆数量
4. 把 token 状态和签到结果一起推送到 Server 酱

---

## 🧩 可选保留配置

账号密码驱动模式代码仍然保留，但当前默认不启用：

| 变量名 | 说明 |
| --- | --- |
| `JLC_USERNAME` | 嘉立创登录账号，多个账号用英文逗号分隔 |
| `JLC_PASSWORD` | 嘉立创登录密码，多个密码用英文逗号分隔，顺序要和账号一致 |
| `ENABLE_BROWSER_LOGIN` | 设为 `true` 时才启用账号密码驱动模式 |

如果同时提供了账号密码和 `TOKEN_LIST`，而 `ENABLE_BROWSER_LOGIN` 没有设为 `true`，脚本会忽略账号密码，直接使用 `TOKEN_LIST`。

---

## ⚙️ GitHub Actions Secrets

进入你自己的仓库：

`Settings -> Secrets and variables -> Actions`

推荐至少配置下面两个 Secret：

| 名称 | 示例 |
| --- | --- |
| `TOKEN_LIST` | `token1,token2` |
| `SEND_KEY_LIST` | `SCTxxxx,SCTyyyy` |

可选保留 Secret：

| 名称 | 说明 |
| --- | --- |
| `JLC_USERNAME` | 账号密码登录模式使用 |
| `JLC_PASSWORD` | 账号密码登录模式使用 |
| `ENABLE_BROWSER_LOGIN` | 设为 `true` 才启用账号密码模式 |

注意：

- 多个账号之间都使用英文逗号 `,` 分隔。
- `TOKEN_LIST` 与 `SEND_KEY_LIST` 最好按同样顺序一一对应。
- 如果某个账号没有对应的 `SendKey`，脚本仍会执行签到，但不会推送它的通知。

---

## 💻 本地运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

默认 token 模式：

```bash
TOKEN_LIST=token1,token2
SEND_KEY_LIST=SCTxxxx,SCTyyyy
python main.py
```

如果你以后想重新启用账号密码驱动模式：

```bash
JLC_USERNAME=user1@example.com,user2@example.com
JLC_PASSWORD=password1,password2
ENABLE_BROWSER_LOGIN=true
SEND_KEY_LIST=SCTxxxx,SCTyyyy
python main.py
```

---

## 🤖 GitHub Actions

仓库已经自带 workflow，会自动：

1. 安装 Python 3.12
2. 安装 `requests` 和 `selenium`
3. 读取仓库 Secrets
4. 执行 `python main.py`

默认定时为每天执行 1 次，时间是北京时间 07:00。你也可以按自己的需要修改 [.github/workflows/python-publish.yml](/D:/Code/PycharmProjects/AutoSign/LC-AutoSign/.github/workflows/python-publish.yml)。

---

## 📬 通知说明

每个账号的通知会包含：

- Token 状态检测结果
- 积分/金豆签到结果
- 是否完成签到、获得多少金豆、当前有多少金豆

如果多个账号使用同一个 `SendKey`，脚本会自动合并成一条汇总消息。
