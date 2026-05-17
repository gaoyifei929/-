"""
企业微信 AI 助手 — 入口

用法：
    python main.py

前置：
    1. 在企业微信客户端 → 工作台 → 智能机器人 → API 模式创建
    2. 将获取的 BotID 和 Secret 填入 .env
    3. pip install -r requirements.txt
"""

VERSION = "0.7.3"

import asyncio
import logging
import sys
from pathlib import Path

from utils.config import load_config
from modules.logger import setup_logging
from modules.session import SessionManager
from modules.rate_limiter import RateLimiter
from modules.profile_store import ProfileStore
from modules.pubg_api import PubgApiClient
from modules.pubg_cache import PubgCache
from modules.ai_engine import AIEngine, AIEngineError
from modules.reply import ReplyHandler
from modules.wecom_adapter import WeComAdapter
from commands.builtin import dispatch as dispatch_command

logger = logging.getLogger(__name__)


async def main():
    config_path = Path(__file__).parent / "config.yaml"
    config = load_config(str(config_path))
    setup_logging(config)

    logger.info("===== 企业微信 AI 助手 v%s 启动 =====", VERSION)

    wecom_config = config.get("wecom", {})
    rl_config = config.get("rate_limit", {})
    session_config = config.get("session", {})
    persona_config = config.get("bot_persona", {})

    system_prompt_text = persona_config.get(
        "system_prompt",
        "你是一个友好的企业微信 AI 助手。请用中文回复，回答简洁准确。",
    )

    ai_engine = AIEngine(config)
    rate_limiter = RateLimiter(
        window_seconds=rl_config.get("window_seconds", 60),
        max_messages=rl_config.get("max_messages_per_window", 10),
        global_qps=rl_config.get("global_qps", 5),
    )
    session_mgr = SessionManager(
        max_rounds=session_config.get("max_history_rounds", 10),
        timeout_minutes=session_config.get("timeout_minutes", 30),
    )
    profile_store = ProfileStore(
        str(Path(__file__).parent / "data" / "profiles.json")
    )
    pubg_config = config.get("pubg", {})
    pubg_api = PubgApiClient(
        api_key=pubg_config.get("api_key", ""),
        shard=pubg_config.get("default_shard", "steam"),
    )
    pubg_cache = PubgCache(
        ttl_seconds=pubg_config.get("cache_ttl_seconds", 300),
    )
    adapter = WeComAdapter(
        bot_id=wecom_config["bot_id"],
        secret=wecom_config["secret"],
    )
    reply_handler = ReplyHandler(adapter)

    from wecom_aibot_sdk import generate_req_id as _gen_sid

    # 触发 PUBG API 查询的关键词（小写）
    _PUBG_STATS_KEYWORDS = [
        "战绩", "kd", "k/d", "吃鸡", "数据", "击杀", "排名",
        "伤害", "场次", "top10", "赛季", "生涯", "比赛",
        "多少杀", "几杀", "打了几场", "帮我查", "查一下",
        "/pubg",
    ]

    def _wants_pubg_stats(text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in _PUBG_STATS_KEYWORDS)

    async def handle_message(msg_obj: dict):
        try:
            user_id = msg_obj["from_user"]
            group_id = msg_obj.get("group_id")
            content = msg_obj.get("content", "").strip()

            # 进入会话事件忽略
            if msg_obj.get("event_type") == "enter_chat":
                return

            # 频率控制
            if not rate_limiter.is_allowed(user_id):
                logger.info("用户 %s 被限流", user_id)
                await reply_handler.reply_text(msg_obj, "消息太频繁，请稍后再试")
                return

            # 快捷指令
            cmd_reply = dispatch_command(content, session_mgr, rate_limiter, profile_store, user_id, group_id)
            if cmd_reply is not None:
                await reply_handler.reply_text(msg_obj, cmd_reply)
                return

            # 空消息跳过
            if not content:
                return

            # 加载会话历史（群聊按用户隔离）
            history = session_mgr.get_history(user_id, group_id)
            messages = [
                {"role": "system", "content": system_prompt_text},
            ]
            # 仅当用户明确想查战绩时才请求 PUBG API
            if _wants_pubg_stats(content):
                logger.info("PUBG 关键词命中：user=%s, content=%.60s", user_id, content)
                profile = profile_store.get_profile(user_id, group_id)
                if profile:
                    parts = profile.split("|", maxsplit=1)
                    game_id = parts[0]
                    shard = parts[1] if len(parts) > 1 else "steam"
                    logger.info("PUBG 查询开始：game_id=%s, shard=%s", game_id, shard)
                    cache_key = f"{shard}:{game_id}"
                    stats_text = pubg_cache.get(cache_key)
                    if stats_text is None:
                        logger.info("PUBG 缓存未命中，请求 API...")
                        orig_shard = pubg_api.shard
                        pubg_api.shard = shard
                        stats = await pubg_api.get_player_stats(game_id)
                        pubg_api.shard = orig_shard
                        if stats is not None:
                            stats_text = stats.format()
                            pubg_cache.set(cache_key, stats_text)
                            logger.info("PUBG API 返回成功：kd=%.2f, kills=%d", stats.kd, stats.kills)
                        else:
                            logger.warning("PUBG API 返回 None：game_id=%s", game_id)
                    else:
                        logger.info("PUBG 缓存命中：len=%d", len(stats_text))
                    if stats_text:
                        content_preview = stats_text[:100].replace("\n", " ")
                        logger.info("PUBG 数据注入 system prompt：%s...", content_preview)
                        messages.append({
                            "role": "system",
                            "content": f"当前说话用户的 PUBG 战绩（官方数据）：\n{stats_text}",
                        })
                    else:
                        logger.warning("PUBG 无数据注入：game_id=%s", game_id)
                        messages.append({
                            "role": "system",
                            "content": f"用户查询了自己的 PUBG 战绩（游戏ID: {game_id}），但 API 未返回数据——该 ID 可能不存在或没有比赛记录。请如实告知用户查不到数据，建议确认游戏 ID 是否正确（用 /setpubg 修改）。",
                        })
                else:
                    logger.info("PUBG 查询：用户 %s 未绑定 ID", user_id)
                    messages.append({
                        "role": "system",
                        "content": "用户想查 PUBG 战绩，但还没有绑定游戏 ID。请引导用户使用 /setpubg <游戏ID> 绑定。",
                    })
            messages.extend(history)
            messages.append({"role": "user", "content": content})

            # 流式调用 AI
            full_reply = ""
            stream_id = _gen_sid("stream")
            at_list = [user_id] if msg_obj.get("is_group") else None
            last_sent = 0

            for chunk in ai_engine.chat_stream(messages):
                full_reply += chunk
                # 每累积 50 字发一次更新，最后一次由最终 finish 发送
                if len(full_reply) - last_sent >= 50:
                    await adapter.send_stream_update(
                        msg_obj, full_reply, stream_id, finish=False, at_list=at_list,
                    )
                    last_sent = len(full_reply)

            # 最终更新（finish=True）
            await adapter.send_stream_update(
                msg_obj, full_reply, stream_id, finish=True, at_list=at_list,
            )

            # 保存会话
            session_mgr.add_message(user_id, "user", content, group_id)
            session_mgr.add_message(user_id, "assistant", full_reply, group_id)

        except AIEngineError:
            await reply_handler.reply_error(msg_obj)
        except Exception:
            logger.exception("消息处理异常")
            await reply_handler.reply_error(msg_obj)

    try:
        await adapter.start(handle_message)
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception:
        logger.exception("启动失败")
        sys.exit(1)
    finally:
        await adapter.stop()
        await pubg_api.close()


if __name__ == "__main__":
    asyncio.run(main())
