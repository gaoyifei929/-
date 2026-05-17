import logging

logger = logging.getLogger(__name__)

# 企业微信流式消息内容长度上限（字符数，近似值）
_MAX_TEXT_CHARS = 4000


class ReplyHandler:
    """消息回复模块：文本分段发送 + 兜底错误回复。"""

    def __init__(self, adapter):
        self._adapter = adapter

    async def reply_text(self, msg_obj: dict, text: str):
        if not text:
            return

        # 长文本分段
        segments = self._split_long_text(text)
        at_list = [msg_obj["from_user"]] if msg_obj.get("is_group") else None

        for seg in segments:
            await self._adapter.send_text(msg_obj, seg, at_list)

    async def reply_error(self, msg_obj: dict, custom_message: str | None = None):
        """异常兜底回复。"""
        msg = custom_message or "我没听懂你说的"
        await self._adapter.send_error(msg_obj, msg)

    @staticmethod
    def _split_long_text(text: str) -> list[str]:
        """按字符长度拆分超长文本。"""
        if len(text) <= _MAX_TEXT_CHARS:
            return [text]

        segments = []
        for i in range(0, len(text), _MAX_TEXT_CHARS):
            segments.append(text[i:i + _MAX_TEXT_CHARS])
        return segments
