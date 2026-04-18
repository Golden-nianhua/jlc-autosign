# 📬 JLC Auto Sign

支持嘉立创金豆签到和立创开源平台签到，并通过 [Server 酱](https://sct.ftqq.com/) 推送汇总消息。

---

## ✨ 功能

- 支持多账号签到
- 支持立创开源平台签到
- 支持金豆签到
- 支持账号密码驱动模式，无需手动抓 `AccessToken`
- 保留 `TOKEN_LIST` 兼容模式，可作为金豆签到回退方案
- 按 `SEND_KEY_LIST` 分组推送 Server 酱通知

---

## 🔧 推荐配置

推荐直接使用账号密码驱动模式：

| 变量名 | 说明 |
| --- | --- |
| `JLC_USERNAME` | 嘉立创登录账号，多个账号用英文逗号分隔 |
| `JLC_PASSWORD` | 嘉立创登录密码，多个密码用英文逗号分隔，顺序要和账号一致 |
| `SEND_KEY_LIST` | Server 酱 SendKey，多个值用英文逗号分隔，按账号索引匹配 |

脚本会对每个账号执行以下流程：

1. 登录立创账号
2. 执行立创开源平台签到
3. 复用同一登录态进入 `m.jlc.com`
4. 自动提取登录态里的 `AccessToken`
5. 执行金豆签到
6. 把开源平台和金豆签到结果一起推送到 Server 酱

---

## 🧩 兼容配置

如果你暂时只想跑金豆签到，也可以继续使用旧版配置：

| 变量名 | 说明 |
| --- | --- |
| `TOKEN_LIST` | 金豆签到使用的 `X-JLC-AccessToken`，多个 token 用英文逗号分隔 |
| `SEND_KEY_LIST` | Server 酱 SendKey，多个值用英文逗号分隔 |

当同时提供账号密码和 `TOKEN_LIST` 时，脚本会优先尝试账号密码驱动模式；如果某个账号的网页登录失败，或者浏览器登录态里提取不到金豆所需的 `AccessToken`，脚本会自动回退到该账号对应位置的 `TOKEN_LIST`，并把回退原因写进通知消息。

---

## ⚙️ GitHub Actions Secrets

进入你自己的仓库：

`Settings -> Secrets and variables -> Actions`

推荐至少配置下面三个 Secret：

| 名称 | 示例 |
| --- | --- |
| `JLC_USERNAME` | `user1@example.com,user2@example.com` |
| `JLC_PASSWORD` | `password1,password2` |
| `SEND_KEY_LIST` | `SCTxxxx,SCTyyyy` |

可选兼容 Secret：

| 名称 | 说明 |
| --- | --- |
| `TOKEN_LIST` | 金豆签到回退用 token 列表 |

注意：

- 多个账号之间都使用英文逗号 `,` 分隔。
- `JLC_USERNAME`、`JLC_PASSWORD`、`SEND_KEY_LIST` 最好按同样顺序一一对应。
- 如果某个账号没有对应的 `SendKey`，脚本仍会执行签到，但不会推送它的通知。

---

## 💻 本地运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

账号密码驱动模式：

```bash
JLC_USERNAME=user1@example.com,user2@example.com
JLC_PASSWORD=password1,password2
SEND_KEY_LIST=SCTxxxx,SCTyyyy
python main.py
```

仅金豆兼容模式：

```bash
TOKEN_LIST=token1,token2
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

每个账号的通知会同时包含：

- 立创开源平台签到结果
- 金豆签到结果

如果多个账号使用同一个 `SendKey`，脚本会自动合并成一条汇总消息。
