import logging
from openai import OpenAI

logger = logging.getLogger(__name__)


class AIEngine:
    """AI 调用统一入口。普通文本对话 + 多模态路由（图片生成/语音/TTS 留接口）。"""

    def __init__(self, config: dict):
        ai_config = config.get("ai", {})
        self.client = OpenAI(
            api_key=ai_config["api_key"],
            base_url=ai_config.get("base_url", "https://api.openai.com/v1"),
        )
        self.model = ai_config.get("model", "gpt-4o")
        self.max_tokens = ai_config.get("max_tokens", 2000)
        self.temperature = ai_config.get("temperature", 0.7)
        self.timeout = ai_config.get("timeout", 60)

    def chat(self, messages: list[dict]) -> str:
        """发送消息列表到 LLM，返回生成的文本（非流式）。"""
        logger.info("AI 调用：model=%s, 消息数=%d", self.model, len(messages))
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                timeout=self.timeout,
            )
            content = response.choices[0].message.content or ""
            logger.info("AI 回复：%d 字符", len(content))
            return content
        except Exception as e:
            logger.exception("AI 调用异常")
            raise AIEngineError(f"AI 调用失败: {e}") from e

    def chat_stream(self, messages: list[dict]):
        """流式调用 LLM，逐块 yield 文本增量。"""
        logger.info("AI 流式调用：model=%s, 消息数=%d", self.model, len(messages))
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                timeout=self.timeout,
                stream=True,
            )
            total = 0
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    total += len(delta.content)
                    yield delta.content
            logger.info("AI 流式回复：%d 字符", total)
        except Exception as e:
            logger.exception("AI 流式调用异常")
            raise AIEngineError(f"AI 调用失败: {e}") from e

    def generate_image(self, prompt: str) -> str | None:
        """
        图片生成（需要模型支持，如 DALL·E）。
        返回图片 URL 或 None。
        """
        logger.info("图片生成请求：%s", prompt[:80])
        try:
            response = self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                n=1,
                size="1024x1024",
            )
            url = response.data[0].url
            logger.info("图片生成完成：%s", url)
            return url
        except Exception as e:
            logger.exception("图片生成异常")
            return None

    def transcribe_audio(self, audio_path: str) -> str | None:
        """语音转文本（Whisper）。"""
        logger.info("语音识别：%s", audio_path)
        try:
            with open(audio_path, "rb") as f:
                result = self.client.audio.transcriptions.create(
                    model="whisper-1", file=f
                )
            text = result.text
            logger.info("语音识别结果：%s", text[:80])
            return text
        except Exception as e:
            logger.exception("语音识别异常")
            return None

    def text_to_speech(self, text: str, output_path: str) -> bool:
        """TTS 文本转语音，写入 output_path。"""
        logger.info("TTS 请求：%d 字符 → %s", len(text), output_path)
        try:
            response = self.client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text,
            )
            response.stream_to_file(output_path)
            logger.info("TTS 完成：%s", output_path)
            return True
        except Exception as e:
            logger.exception("TTS 异常")
            return False


class AIEngineError(Exception):
    """AI 调用异常。"""
    pass
