# skill-codex

后续 Claude Code 技能统一放在用户级 Claude 配置目录：

```text
/Users/bukeyitoukano/.claude/skills
```

已维护技能：

- `/Users/bukeyitoukano/.claude/skills/仓租采购审批邮件生成`：根据仓租/临租采购表格截图、OCR 文本、粘贴表格、合同内容或需求整理新增行生成中文审批邮件正文。
- `/Users/bukeyitoukano/.claude/skills/仓租采购需求整理`：根据新增仓库租赁信息或合同内容自动填充桌面《仓库临租需求.xlsx》，支持合同必要字段抽取、F 列历史检索、G/M 互算、N/O/P/Q 公式带出，并联动生成审批邮件。

## 飞书待办提醒云端 Worker

已新增：

```text
feishu_todo_reminder/scripts/feishu_todo_reminder.py
```

用途：

- 定期读取飞书多维表格待办清单。
- 对 `提醒开关=开启`、`完成情况!=已完成`、`下次提醒时间<=当前时间` 的任务发送提醒。
- 发送后写回 `最后跟进日期`，避免同一天重复提醒。
- 适合部署到 Railway 或其他云服务器，电脑关机后仍可运行。

部署步骤见：

```text
feishu_todo_reminder/README.md
```

## 飞书入站触发

已提供入站服务脚本：

```text
仓租采购需求整理/scripts/feishu_inbound_service.py
```

用途：

- 接收飞书自建应用机器人事件订阅消息。
- 支持 URL verification challenge。
- 接收 `im.message.receive_v1` 后下载消息附件。
- 调用 Codex CLI 执行“仓租采购需求整理”工作流。
- 将处理结果回复到飞书原消息。

必需环境变量：

```bash
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"
```

可选环境变量：

```bash
export FEISHU_VERIFICATION_TOKEN="xxx"
export FEISHU_INBOUND_PORT="8787"
export FEISHU_WORKFLOW_TIMEOUT_SECONDS="1800"
export FEISHU_WORKFLOW_COMMAND="自定义命令，使用 {output_file} 占位最终输出文件"
```

启动：

```bash
python3 仓租采购需求整理/scripts/feishu_inbound_service.py --port 8787
```

将服务地址通过公网域名或内网穿透暴露后，在飞书开放平台事件订阅中填写：

```text
https://你的域名/feishu/events
```

当前脚本对任意路径的 POST 都会处理，因此 `/feishu/events`、`/` 均可。
