"""
ParrotGo LiveKit Voice Agent
Tích hợp STT & TTS của Azure Speech vào hệ thống lõi ParrotGo.
"""

import asyncio
import logging
import sys
from typing import Optional

from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import azure, silero

from src.cli.runner import SessionRunner

logger = logging.getLogger("livekit.agent")

# --- CUSTOM LLM CHO PARROTGO ---
class ParrotGoLLM(llm.LLM):
    """
    Adapter wrap ParrotGo Runner thành một LLM Interface để VoicePipelineAgent gọi.
    Bằng cách này, Core Logic của bạn vẫn chạy hoàn toàn độc lập và trả về final_response_text
    mà không cần viết lại toàn bộ luồng.
    """
    def __init__(self, runner: SessionRunner):
        super().__init__()
        self.runner = runner

    def chat(
        self,
        chat_ctx: llm.ChatContext,
        fnc_ctx: Optional[llm.FunctionContext] = None,
        temperature: Optional[float] = None,
        n: Optional[int] = None,
        parallel_tool_calls: Optional[bool] = None,
    ) -> "ParrotGoLLMStream":
        user_message = ""
        # Lấy tin nhắn cuối cùng (mới nhất) của khách hàng từ pipeline
        for msg in reversed(chat_ctx.messages):
            if msg.role == "user" and isinstance(msg.content, str):
                user_message = msg.content
                break
                
        return ParrotGoLLMStream(self.runner, user_message)


class ParrotGoLLMStream(llm.LLMStream):
    def __init__(self, runner: SessionRunner, user_message: str):
        super().__init__(None, None)
        self.runner = runner
        self.user_message = user_message
        self._yielded = False

    async def __anext__(self) -> llm.ChatChunk:
        if self._yielded:
            raise StopAsyncIteration
            
        self._yielded = True
        
        loop = asyncio.get_event_loop()
        try:
            # Chạy handle_turn trong ThreadPool để graph synchronous không block async event loop
            bot_text = await loop.run_in_executor(None, self.runner.handle_turn, self.user_message)
            
            # Ghi log debug hội thoại
            logger.info(f"[Khách] {self.user_message}")
            logger.info(f"[Bot] {bot_text}")
            
        except Exception as e:
            logger.error(f"Lỗi xử lý ParrotGo: {e}", exc_info=True)
            bot_text = "Dạ hệ thống đang bận một chút, quý khách vui lòng thử lại nhé."
            
        return llm.ChatChunk(
            choices=[
                llm.Choice(
                    delta=llm.ChoiceDelta(role="assistant", content=bot_text)
                )
            ]
        )


# --- ENTRYPOINT CỦA VOICE AGENT ---
async def entrypoint(ctx: JobContext):
    # Khởi tạo thông tin khách hàng từ metadata của phòng LiveKit (nếu có)
    # Ví dụ khi tổng đài tạo phòng, truyền metadata: '{"phone": "09...", "name": "..."}'
    try:
        import json
        metadata = json.loads(ctx.room.metadata) if ctx.room.metadata else {}
    except:
        metadata = {}
        
    phone = metadata.get("phone", "0988888888")
    name = metadata.get("name", "Quý khách")
    city = metadata.get("city", None)

    logger.info(f"Đang khởi tạo ParrotGo Agent cho: {name} - SĐT: {phone}")

    # Khởi tạo phiên của ParrotGo (dùng chung src.cli.runner.SessionRunner)
    runner = SessionRunner(phone=phone, name=name, city=city, debug=False)
    
    agent = VoicePipelineAgent(
        vad=silero.VAD.load(),
        stt=azure.STT(languages=["vi-VN"]), # Azure STT tiếng Việt
        llm=ParrotGoLLM(runner),           # Adapter gọi lõi LangGraph
        tts=azure.TTS(voice="vi-VN-HoaiMyNeural"), # Giọng nữ Azure (hoặc "vi-VN-NamMinhNeural")
        chat_ctx=llm.ChatContext().append(
            role="system",
            text="Trợ lý đặt xe ParrotGo"
        )
    )

    # Kết nối phòng và lắng nghe Audio từ người gọi
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    agent.start(ctx.room)
    
    # Đợi 1 chút cho kết nối Audio ổn định, rồi bot chủ động chào đón trước
    await asyncio.sleep(1.5)
    await agent.say(f"Dạ ParrotGo xin chào {name}. Em có thể giúp gì cho mình ạ?", allow_interruptions=True)

if __name__ == "__main__":
    # Đảm bảo utf-8 cho console log trên Windows
    if hasattr(sys.stdout, "reconfigure"):
        getattr(sys.stdout, "reconfigure")(encoding="utf-8")
        
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
