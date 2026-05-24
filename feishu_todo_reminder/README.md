# 飞书待办提醒部署说明

这套 Worker 会读取飞书待办清单，并执行补发逻辑：

- `提醒开关 = 开启`
- `完成情况 != 已完成`
- `下次提醒时间 <= 当前时间`
- `最后跟进日期` 不是今天

满足以上条件时，Worker 会发送飞书提醒，并把 `最后跟进日期` 写成今天。这样即使某次检查延迟或失败，下一次恢复后也会补发已过期但今天未提醒过的任务。

## 一、飞书表格要求

当前脚本支持两种存放方式：

- 飞书知识库里的电子表格，也就是链接里包含 `/wiki/`，页面里是表格。
- 飞书多维表格，也就是链接里包含 `/base/`。

表格字段默认使用这些列名：

```text
任务ID
完成情况
待办事项
优先级
待办类型
截止日期
最后跟进日期
下次提醒时间
提醒开关
AI处理状态
```

如果你的列名不一样，可以用环境变量覆盖，例如：

```text
TODO_FIELD_NEXT_REMINDER=下次提醒时间
TODO_FIELD_LAST_FOLLOW=最后跟进日期
```

## 二、需要准备的飞书信息

### 1. 自建应用凭证

在飞书开放平台进入你的自建应用，找到：

```text
FEISHU_APP_ID
FEISHU_APP_SECRET
```

并确认应用拥有云文档/电子表格或多维表格的读取、写入权限，以及机器人发送消息权限。实际权限名称以飞书后台显示为准。

### 2. 待办清单文档 token

如果你的链接是知识库 wiki 链接，例如：

```text
https://zcnr40mxkvh6.feishu.cn/wiki/YnzgwaDVci7bASkaf7Zc2E0rnTe
```

取出 `/wiki/` 后面的这一段：

```text
TODO_WIKI_NODE_TOKEN=YnzgwaDVci7bASkaf7Zc2E0rnTe
```

如果你的链接是多维表格链接，例如：

```text
https://xxx.feishu.cn/base/<app_token>?table=<table_id>
```

取出：

```text
TODO_BITABLE_APP_TOKEN=<app_token>
TODO_BITABLE_TABLE_ID=<table_id>
```

两种方式选一种即可。当前推荐先用 `TODO_WIKI_NODE_TOKEN`。

### 3. 应用机器人接收对象

如果使用飞书应用机器人主动提醒，需要配置接收对象：

```text
TODO_FEISHU_RECEIVE_ID_TYPE=chat_id
TODO_FEISHU_RECEIVE_ID=oc_xxx
```

发到群聊时通常使用 `chat_id`；发给个人时通常使用 `open_id`。机器人需要被加入对应群聊，或具备给对应用户发消息的权限。

### 4. 飞书群机器人 webhook 备用方案

在接收提醒的飞书群里添加自定义机器人，复制 webhook：

```text
TODO_FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

如果群机器人开启了签名校验，再准备：

```text
TODO_FEISHU_WEBHOOK_SECRET=xxx
```

## 三、GitHub Actions 免费定时运行

仓库里已经提供工作流：

```text
.github/workflows/feishu-todo-reminder.yml
```

默认每 10 分钟检查一次，也支持在 GitHub 页面手动运行。

### 1. 配置 Secrets

打开 GitHub 仓库：

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

逐个添加：

```text
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
TODO_WIKI_NODE_TOKEN=xxx
TODO_FEISHU_RECEIVE_ID_TYPE=chat_id
TODO_FEISHU_RECEIVE_ID=oc_xxx
```

如果你不用应用机器人，改用群自定义机器人 webhook，则添加：

```text
TODO_FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
TODO_FEISHU_WEBHOOK_SECRET=xxx
```

### 2. 手动测试

打开 GitHub 仓库：

```text
Actions -> Feishu Todo Reminder -> Run workflow
```

点运行后进入本次执行记录，看到类似下面内容说明检查成功：

```text
checked 6 records, sent 0 reminders
```

如果存在已到提醒时间且今天未跟进的待办，会显示：

```text
sent reminder record_id=xxx reminder_time=...
checked 6 records, sent 1 reminders
```

### 3. 延迟说明

GitHub Actions 定时任务不是严格准点，可能延迟几分钟。你的提醒逻辑按 `下次提醒时间 <= 当前时间` 判断，所以延迟不会漏提醒，只会晚一点发送。

## 四、Railway 部署步骤

如果以后你希望更稳定地常驻运行，可以再部署 Railway。

1. 把这个仓库推送到 GitHub。
2. 打开 Railway，创建 New Project。
3. 选择 Deploy from GitHub repo。
4. 选择这个仓库。
5. Railway 会读取仓库里的 `railway.json`，启动命令是：

```bash
python3 feishu_todo_reminder/scripts/feishu_todo_reminder.py
```

6. 在 Railway 项目的 Variables 里添加下面这些变量：

```text
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
TODO_WIKI_NODE_TOKEN=xxx
TODO_FEISHU_RECEIVE_ID_TYPE=chat_id
TODO_FEISHU_RECEIVE_ID=oc_xxx
TODO_TIMEZONE=Asia/Shanghai
TODO_POLL_INTERVAL_SECONDS=300
```

如果不用应用机器人，改用群自定义机器人 webhook，则配置 `TODO_FEISHU_WEBHOOK_URL` 和可选的 `TODO_FEISHU_WEBHOOK_SECRET`。

7. 点击 Deploy 或等待 Railway 自动部署。
8. 打开 Railway Logs，看到类似内容说明 Worker 已经运行：

```text
checked 6 records, sent 0 reminders
```

## 五、建议的字段行为

`下次提醒时间` 可以设置成过去时间。只要当天还没有写入 `最后跟进日期`，Worker 会补发。

`最后跟进日期` 用来防止一天内重复提醒。如果你希望同一任务一天提醒多次，需要把表格加一个“最后提醒时间”字段，再调整判断逻辑。

`AI处理状态` 默认会在提醒后写成 `已提醒`。如果不想改这个字段，在环境变量里加：

```text
TODO_UPDATE_AI_STATUS=0
```

## 六、本地测试

本地临时设置环境变量后，可以运行一次检查：

```bash
python3 feishu_todo_reminder/scripts/feishu_todo_reminder.py --once
```

如果只想看云端效果，直接在 Railway Logs 里观察即可。

## 七、回复“已完成”自动更新

已提供入站服务：

```text
feishu_todo_reminder/scripts/feishu_todo_inbound_service.py
```

部署到云服务器后，在飞书开放平台事件订阅中填写公网地址：

```text
https://你的域名/feishu/todo/events
```

需要订阅事件：

```text
im.message.receive_v1
```

收到文本消息后，服务会处理：

```text
已完成
已完成 T-20260522-005
```

如果没有写任务 ID，服务只会在“今天刚提醒且只有一条未完成任务”时自动完成；如果今天有多条候选任务，会回复让你补充任务 ID，避免误改。
