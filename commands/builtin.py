"""快捷指令处理。"""

import logging

logger = logging.getLogger(__name__)

# 指令 → 处理函数映射
COMMANDS: dict[str, callable] = {}


def register(cmd: str):
    """装饰器：注册快捷指令。"""

    def decorator(fn):
        COMMANDS[cmd] = fn
        return fn

    return decorator


def dispatch(text: str, session_mgr, rate_limiter, profile_store, user_id: str, group_id: str | None) -> str | None:
    """尝试匹配指令。匹配成功返回回复文本，不匹配返回 None。"""
    text = text.strip()

    # 消息可能以 @机器人名 开头（企微会把 @mention 留在 content 里），
    # 找到第一个 "/" 指令的起始位置
    slash_pos = text.find("/")
    if slash_pos > 0:
        text = text[slash_pos:]

    # 指令格式：/xxx 或 /xxx arg
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    handler = COMMANDS.get(cmd)
    if handler is None:
        return None

    logger.info("快捷指令：%s (user=%s)", cmd, user_id)
    return handler(
        arg=arg,
        session_mgr=session_mgr,
        rate_limiter=rate_limiter,
        profile_store=profile_store,
        user_id=user_id,
        group_id=group_id,
    )


# ---------- 内置指令 ----------

@register("/help")
def _help(**ctx) -> str:
    return (
        "可用指令：\n"
        "/help      — 显示此帮助\n"
        "/reset     — 清除当前对话上下文\n"
        "/status    — 查看会话状态\n"
        "/setpubg   — 设置你的 PUBG 游戏ID，如 /setpubg LaoLiu_2023\n"
        "/pubg      — 查看自己的 PUBG 战绩\n"
        "/pubglist  — 查看本群所有人的 PUBG 档案"
    )


@register("/reset")
def _reset(arg, session_mgr, user_id, group_id, **ctx) -> str:
    session_mgr.clear(user_id, group_id)
    return "对话上下文已清除"


@register("/status")
def _status(arg, session_mgr, rate_limiter, user_id, group_id, **ctx) -> str:
    sess = session_mgr.get_status(user_id, group_id)
    rl = rate_limiter.get_status(user_id)
    return (
        f"会话状态：\n"
        f"  历史消息数：{sess['messages']}\n"
        f"  对话轮次：{sess['rounds']}\n"
        f"  空闲秒数：{sess['idle_seconds']}\n"
        f"  限流窗口内消息：{rl['recent_count']}/{rl['limit']}"
    )


VALID_SHARDS = {"steam", "kakao", "console", "psn", "xbox", "stadia", "tournament"}


@register("/setpubg")
def _setpubg(arg, profile_store, user_id, group_id, **ctx) -> str | None:
    parts = arg.strip().split(maxsplit=1)
    if not parts or not parts[0]:
        return "格式：/setpubg <游戏ID> [区服]\n例如：/setpubg LaoLiu_2023\n支持区服：steam（默认）、kakao、console、psn、xbox"
    game_id = parts[0]
    shard = "steam"
    if len(parts) > 1 and parts[1].strip().lower() in VALID_SHARDS:
        shard = parts[1].strip().lower()
    profile_store.set_profile(user_id, f"{game_id}|{shard}", group_id)
    # 多余文本不是合法区服 → 返回 None，让消息落入 AI 流程处理（如"同时查一下战绩"）
    if len(parts) > 1 and parts[1].strip().lower() not in VALID_SHARDS:
        return None
    return f"PUBG 档案已更新：{game_id}（区服：{shard}）"


@register("/pubg")
def _pubg(arg, profile_store, user_id, group_id, **ctx) -> str | None:
    profile = profile_store.get_profile(user_id, group_id)
    if profile is None:
        return "你还没有设置 PUBG 档案，用 /setpubg <游戏ID> 来设置吧"
    # 有档案时返回 None，让消息落入 AI 流程，由 AI 结合实时战绩数据回复
    return None


@register("/pubglist")
def _pubglist(arg, profile_store, group_id, **ctx) -> str:
    if not group_id:
        return "这个指令只在群聊里可用"
    profiles = profile_store.list_profiles(group_id)
    if not profiles:
        return "本群还没有人设置 PUBG 档案"
    lines = ["本群 PUBG 档案："]
    for uid, profile in profiles.items():
        summary = profile.split("\n")[0] if "\n" in profile else profile
        if len(summary) > 60:
            summary = summary[:57] + "..."
        lines.append(f"  <@{uid}> — {summary}")
    return "\n".join(lines)
