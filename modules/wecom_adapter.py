"""
企业微信接入层 — 基于官方智能机器人 WebSocket 长连接。

前置条件：
    1. 在企业微信客户端 → 工作台 → 智能机器人 → 创建（API 模式）
    2. 获取 BotID 和 Secret，填入 .env
    3. pip install wecom-aibot-sdk-python

优势：
    - 无需公网 IP、域名、HTTPS 证书
    - 无需处理消息加解密
    - 官方 API，无封号风险
"""

import asyncio
import logging
from typing import Callable, Awaitable
from wecom_aibot_sdk import WSClient, WSClientOptions, generate_req_id

logger = logging.getLogger(__name__)


class WeComAdapter:
    """封装企业微信智能机器人 SDK。"""

    def __init__(self, bot_id: str, secret: str):
        self.bot_id = bot_id
        self.secret = secret
        self._client = WSClient(
            WSClientOptions(
                bot_id=bot_id,
                secret=secret,
                reconnect_interval=5000,
                max_reconnect_attempts=0,
                logger=logger,  # 接入项目日志
            )
        )
        self._callback: Callable[[dict], Awaitable[None]] | None = None
        self._connected = asyncio.Event()
        self._seen_msg_ids: set[str] = set()

    # ---------- 生命周期 ----------

    async def start(self, callback: Callable[[dict], Awaitable[None]]):
        """
        连接企业微信并开始接收消息。阻塞直到连接断开或调用 stop()。
        callback 签名：async def callback(msg_obj: dict) -> None
        """
        self._callback = callback

        # 注册消息处理
        self._client.on("*", self._dispatch)
        self._client.on("authenticated", self._on_authenticated)

        logger.info("企业微信适配器启动：bot_id=%s", self.bot_id[:8] + "***")
        await self._client.connect_async()

        # connect_async 返回后，后台任务已在运行。等待直到 stop() 被调用
        await self._connected.wait()

    async def _on_authenticated(self, frame):
        logger.info("企业微信认证成功！机器人已上线")

    async def stop(self):
        self._connected.set()
        await self._client.disconnect()
        logger.info("企业微信适配器已断开")

    # ---------- 消息接收 ----------

    async def _dispatch(self, frame):
        """将 SDK 的 WsFrame 转为标准消息对象，交给上层回调。"""
        try:
            body = frame.body or {}
            headers = frame.headers or {}
            cmd = frame.cmd or ""

            logger.debug("收到 frame: cmd=%s, body_keys=%s", cmd, list(body.keys())[:10])

            # 判断是消息还是事件
            if cmd == "aibot_msg_callback":
                msg_obj = self._parse_message(body, headers)
            elif cmd == "aibot_recv_event":
                msg_obj = self._parse_event(body, headers)
            else:
                return

            if msg_obj is None:
                logger.warning("消息解析返回 None")
                return

            # 去重：SDK 对同一条消息可能 dispatch 多次
            msg_id = msg_obj.get("msg_id", "")
            if msg_id and msg_id in self._seen_msg_ids:
                logger.debug("跳过重复消息 msg_id=%s", msg_id)
                return
            if msg_id:
                self._seen_msg_ids.add(msg_id)
                # 限制集合大小，防止内存泄漏
                if len(self._seen_msg_ids) > 10000:
                    self._seen_msg_ids.clear()

            logger.info(
                "收到消息 from=%s, type=%s, content=%.80s",
                msg_obj["from_user"],
                msg_obj["msg_type"],
                msg_obj["content"],
            )

            if self._callback:
                await self._callback(msg_obj)
        except Exception:
            logger.exception("消息分发异常")

    def _parse_message(self, body: dict, headers: dict) -> dict | None:
        """解析消息 body。"""
        try:
            msgtype = body.get("msgtype", "text")
            content = ""
            if msgtype == "text":
                content = body.get("text", {}).get("content", "")
            elif msgtype == "image":
                content = "[图片消息]"
            elif msgtype == "voice":
                content = "[语音消息]"
            elif msgtype == "file":
                content = "[文件消息]"
            elif msgtype == "mixed":
                # 混合消息取第一条文本
                items = body.get("mixed", {}).get("msg_item", [])
                text_parts = []
                for item in items:
                    if item.get("msgtype") == "text":
                        text_parts.append(item.get("text", {}).get("content", ""))
                content = " ".join(text_parts) if text_parts else "[混合消息]"

            chattype = body.get("chattype", "single")
            return {
                "msg_id": body.get("msgid", ""),
                "from_user": body.get("from", {}).get("userid", ""),
                "content": content,
                "msg_type": msgtype,
                "is_group": chattype == "group",
                "group_id": body.get("chatid") if chattype == "group" else None,
                "timestamp": body.get("create_time", 0),
                "_frame_headers": headers,  # 保留，回复时需要
            }
        except Exception:
            logger.exception("消息解析异常")
            return None

    def _parse_event(self, body: dict, headers: dict) -> dict | None:
        """解析事件 body。"""
        try:
            event_type = body.get("event", {}).get("eventtype", "")
            if event_type == "enter_chat":
                chattype = body.get("chattype", "single")
                return {
                    "msg_id": "",
                    "from_user": body.get("from", {}).get("userid", ""),
                    "content": "",
                    "msg_type": "event",
                    "is_group": chattype == "group",
                    "group_id": body.get("chatid") if chattype == "group" else None,
                    "timestamp": body.get("create_time", 0),
                    "event_type": "enter_chat",
                    "_frame_headers": headers,
                }
            return None
        except Exception:
            logger.exception("事件解析异常")
            return None

    # ---------- 消息发送 ----------

    async def send_text(self, msg_obj: dict, text: str, at_list: list[str] | None = None):
        """回复文本消息（一次性发送）。"""
        from_user = msg_obj.get("from_user", "?")
        headers = msg_obj.get("_frame_headers")
        if not headers:
            logger.warning("发送失败：缺少 frame headers, to=%s", from_user)
            return

        stream_id = generate_req_id("stream")
        full_text = self._prepend_at(text, msg_obj, at_list)

        try:
            await self._client.reply_stream(
                frame=headers,
                stream_id=stream_id,
                content=full_text,
                finish=True,
            )
            logger.info("回复成功: to=%s, len=%d", from_user, len(full_text))
        except Exception:
            logger.exception("发送失败: to=%s", from_user)

    async def send_stream_update(
        self, msg_obj: dict, text: str, stream_id: str, finish: bool = False,
        at_list: list[str] | None = None,
    ):
        """发送流式消息的增量更新。finish=True 表示最后一段。"""
        from_user = msg_obj.get("from_user", "?")
        headers = msg_obj.get("_frame_headers")
        if not headers:
            logger.warning("流式发送失败：缺少 frame headers, to=%s", from_user)
            return
        full_text = self._prepend_at(text, msg_obj, at_list)
        try:
            await self._client.reply_stream(
                frame=headers,
                stream_id=stream_id,
                content=full_text,
                finish=finish,
            )
            if finish:
                logger.info("流式回复完成: to=%s, len=%d", from_user, len(full_text))
        except Exception:
            logger.exception("流式发送失败: to=%s", from_user)

    async def send_error(self, msg_obj: dict, text: str | None = None):
        """发送错误兜底回复。"""
        await self.send_text(msg_obj, text or "我没听懂你说的")

    @staticmethod
    def _prepend_at(text: str, msg_obj: dict, at_list: list[str] | None) -> str:
        """群聊时在文本前拼 @mention。"""
        if at_list and msg_obj.get("is_group"):
            at_text = " ".join(f"<@{uid}>" for uid in at_list)
            return f"{at_text}\n{text}"
        return text
