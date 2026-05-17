# 企业微信 AI 助手 — 老六

企业微信群聊 AI 机器人，PUBG 退役选手人格。基于企业微信智能机器人 WebSocket 长连接 + DeepSeek v4-pro。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 创建 .env，填入凭证
cp .env.example .env

# 3. 启动
python main.py
```

## 前置条件

1. 企业微信客户端 → 工作台 → 智能机器人 → 创建（API 模式）
2. 将 BotID、Secret 填入 `.env`
3. PUBG 战绩功能需要 [developer.pubg.com](https://developer.pubg.com) 注册获取 API Key

无需公网 IP、域名、HTTPS 证书。

## 功能

| 功能 | 说明 |
|------|------|
| 快捷指令 | `/help` `/reset` `/status` |
| PUBG 战绩 | `/setpubg <游戏ID>` 绑定，`/pubg` 查实时数据 |
| 群友档案 | `/pubglist` 查看本群所有已绑定玩家 |
| 流式输出 | AI 回复实时推送，50 字符增量更新 |
| 上下文隔离 | 群聊每人独立记忆，互不串话 |
| 限流保护 | 每用户滑动窗口 + 全局 QPS |

## 消息触发

群聊中 @机器人名 即可触发，私聊始终响应。

查战绩只需说"查战绩""KD 多少""帮我查一下"等自然语言，无需记指令。

## 项目结构

```
WeChat AI/
├── main.py              # 入口
├── config.yaml          # 配置文件
├── modules/
│   ├── wecom_adapter.py # 企微接入层
│   ├── ai_engine.py     # AI 调用
│   ├── session.py       # 会话管理
│   ├── rate_limiter.py  # 限流
│   ├── reply.py         # 消息回复
│   ├── logger.py        # 日志
│   ├── profile_store.py # 档案存储
│   ├── pubg_api.py      # PUBG API
│   └── pubg_cache.py    # API 缓存
├── commands/
│   └── builtin.py       # 快捷指令
└── utils/
    └── config.py        # 配置加载
```

## 技术栈

Python 3.12 · wecom-aibot-sdk-python · DeepSeek v4-pro · httpx · PyYAML

## License

MIT
