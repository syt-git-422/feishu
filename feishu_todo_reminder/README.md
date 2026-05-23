# 飞书待办提醒云端部署说明

这套 Worker 适合部署到 Railway、VPS 等长期在线环境。它会循环读取飞书多维表格待办清单，并执行补发逻辑：

- `提醒开关 = 开启`
- `完成情况 != 已完成`
- `下次提醒时间 <= 当前时间`
- `最后跟进日期` 不是今天

满足以上条件时，Worker 会发送飞书提醒，并把 `最后跟进日期` 写成今天。这样即使服务重启、短暂离线，恢复后也会补发已过期但今天未提醒过的任务。

## 一、飞书表格要求

当前脚本按飞书多维表格 API 读取。表格字段默认使用这些列名：

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

如果你的列名不一样，可以在 Railway 环境变量里覆盖，例如：

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

并确认应用拥有多维表格读取/写入权限。常用权限包括读取和更新多维表格记录，实际名称以飞书后台显示为准。

### 2. 多维表格 app_token 和 table_id

打开待办清单所在的多维表格，浏览器地址通常包含类似：

```text
https://xxx.feishu.cn/base/<app_token>?table=<table_id>
```

取出：

```text
TODO_BITABLE_APP_TOKEN=<app_token>
TODO_BITABLE_TABLE_ID=<table_id>
```

如果你的链接不是这个格式，把链接发给 Codex，我可以帮你判断 token 在哪里。

### 3. 飞书群机器人 webhook

在接收提醒的飞书群里添加自定义机器人，复制 webhook：

```text
TODO_FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

如果群机器人开启了签名校验，再准备：

```text
TODO_FEISHU_WEBHOOK_SECRET=xxx
```

## 三、Railway 部署步骤

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
TODO_BITABLE_APP_TOKEN=xxx
TODO_BITABLE_TABLE_ID=xxx
TODO_FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
TODO_FEISHU_WEBHOOK_SECRET=xxx
TODO_TIMEZONE=Asia/Shanghai
TODO_POLL_INTERVAL_SECONDS=300
```

如果群机器人没有开启签名校验，可以不填 `TODO_FEISHU_WEBHOOK_SECRET`。

7. 点击 Deploy 或等待 Railway 自动部署。
8. 打开 Railway Logs，看到类似内容说明 Worker 已经运行：

```text
checked 6 records, sent 0 reminders
```

## 四、建议的字段行为

`下次提醒时间` 可以设置成过去时间。只要当天还没有写入 `最后跟进日期`，Worker 会补发。

`最后跟进日期` 用来防止一天内重复提醒。如果你希望同一任务一天提醒多次，需要把表格加一个“最后提醒时间”字段，再调整判断逻辑。

`AI处理状态` 默认会在提醒后写成 `已提醒`。如果不想改这个字段，在环境变量里加：

```text
TODO_UPDATE_AI_STATUS=0
```

## 五、本地测试

本地临时设置环境变量后，可以运行一次检查：

```bash
python3 feishu_todo_reminder/scripts/feishu_todo_reminder.py --once
```

如果只想看云端效果，直接在 Railway Logs 里观察即可。
