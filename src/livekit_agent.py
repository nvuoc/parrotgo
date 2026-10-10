"""
ParrotGo LiveKit Voice Agent
Tích hợp STT & TTS của Azure Speech vào hệ thống lõi ParrotGo (LiveKit Agents 1.x).
"""

import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load biến môi trường từ .env
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

from livekit.agents import (
    APIConnectOptions,
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    llm,
)
from livekit.plugins import azure, silero

from src.cli.runner import SessionRunner

logger = logging.getLogger("livekit.agent")


# --- CUSTOM LLM CHO PARROTGO ---
class ParrotGoLLM(llm.LLM):
    """
    Adapter wrap ParrotGo Runner thành một LLM Interface để AgentSession gọi.
    Core Logic của ParrotGo chạy độc lập và trả về final_response_text.
    """
    def __init__(self, runner: SessionRunner):
        super().__init__()
        self.runner = runner

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: Optional[list[llm.Tool]] = None,
        conn_options: Optional[APIConnectOptions] = None,
        **kwargs,
    ) -> "ParrotGoLLMStream":
        user_message = ""
        # Lấy tin nhắn cuối cùng (mới nhất) của khách hàng từ pipeline
        for msg in reversed(chat_ctx.messages):
            if msg.role == "user":
                if isinstance(msg.content, str):
                    user_message = msg.content
                    break
                elif isinstance(msg.content, list):
                    texts = [c if isinstance(c, str) else getattr(c, "text", str(c)) for c in msg.content]
                    user_message = " ".join(texts)
                    break

        conn_opts = conn_options or APIConnectOptions()
        return ParrotGoLLMStream(
            self,
            runner=self.runner,
            user_message=user_message,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_opts,
        )


class ParrotGoLLMStream(llm.LLMStream):
    def __init__(
        self,
        llm_instance: llm.LLM,
        runner: SessionRunner,
        user_message: str,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        conn_options: APIConnectOptions,
    ):
        super().__init__(llm_instance, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self.runner = runner
        self.user_message = user_message

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            # Chạy handle_turn trong ThreadPool để graph synchronous không block async event loop
            bot_text = await loop.run_in_executor(None, self.runner.handle_turn, self.user_message)
            logger.info(f"[Khách] {self.user_message}")
            logger.info(f"[Bot] {bot_text}")
        except Exception as e:
            logger.error(f"Lỗi xử lý ParrotGo: {e}", exc_info=True)
            bot_text = "Dạ hệ thống đang bận một chút, quý khách vui lòng thử lại nhé."

        self._event_ch.send_nowait(
            llm.ChatChunk(
                id=str(uuid.uuid4()),
                delta=llm.ChoiceDelta(role="assistant", content=bot_text or "Dạ em nghe rõ ạ."),
            )
        )


# --- ENTRYPOINT CỦA VOICE AGENT ---
async def entrypoint(ctx: JobContext):
    # Khởi tạo thông tin khách hàng từ metadata của phòng LiveKit (nếu có)
    # Ví dụ khi tổng đài tạo phòng, truyền metadata: '{"phone": "09...", "name": "..."}'
    try:
        metadata = json.loads(ctx.room.metadata) if ctx.room.metadata else {}
    except Exception:
        metadata = {}

    phone = metadata.get("phone", "0988888888")
    name = metadata.get("name", "Quý khách")
    city = metadata.get("city", None)

    logger.info(f"Đang khởi tạo ParrotGo Agent cho: {name} - SĐT: {phone}")

    # Khởi tạo phiên của ParrotGo (dùng chung src.cli.runner.SessionRunner)
    runner = SessionRunner(phone=phone, name=name, city=city, debug=False)

    # Kết nối phòng và lắng nghe Audio từ người gọi
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    agent = Agent(
        instructions="Trợ lý đặt xe ParrotGo thông minh qua giọng nói.",
    )

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=azure.STT(language="vi-VN"),             # Azure STT tiếng Việt
        llm=ParrotGoLLM(runner),                     # Adapter gọi lõi LangGraph
        tts=azure.TTS(voice="vi-VN-HoaiMyNeural"),   # Giọng nữ Azure
    )

    await session.start(agent, room=ctx.room)

    # Đợi 1 chút cho kết nối Audio ổn định, rồi bot chủ động chào đón trước
    await asyncio.sleep(1.0)
    await session.say(f"Dạ ParrotGo xin chào {name}. Em có thể giúp gì cho mình ạ?", allow_interruptions=True)


if __name__ == "__main__":
    # Đảm bảo utf-8 cho console log trên Windows
    if hasattr(sys.stdout, "reconfigure"):
        getattr(sys.stdout, "reconfigure")(encoding="utf-8")

    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))

