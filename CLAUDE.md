# CLAUDE.md

## 项目

企业微信 AI 助手「老六」—— PUBG 退役选手人格的群聊机器人。

- 技术栈：Python 3.12 + wecom-aibot-sdk-python + DeepSeek v4-pro
- 入口：`python main.py`
- 设计文档：`设计流程.md`
- 迭代历史：`版本迭代.md`

## 关键架构点

- 企业微信 WebSocket 长连接，无需公网 IP/域名
- @触发由企微平台层保证，代码无需处理触发逻辑
- 消息 cmd 为 `aibot_msg_callback`，需 msg_id 去重
- 群聊上下文 key = `group_id:user_id`
- PUBG 战绩按需查询（关键词触发），非每次对话都调 API
- 默认区服 steam

## 注意

- `.env` 在 .gitignore，不进仓库
- data/、logs/、temp/ 是运行时生成目录
- `test_v073.py` 是集成测试，.gitignore 排除
- `开发协作总结.md` 是本地方案，不进 git
