"""ParrotGo Web Server (FastAPI backend for Voice & Chat testing)."""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from src.cli.runner import SessionRunner
from src.config import settings
from src.core.time_utils import now_iso

app = FastAPI(
    title="ParrotGo Assistant Web Interface",
    description="Interactive web interface for testing ParrotGo LLM booking agent with Voice and Text.",
    version="1.0.0",
)

# Enable CORS for cross-origin local access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for active sessions
sessions_db: Dict[str, Dict[str, Any]] = {}


class CreateSessionRequest(BaseModel):
    phone: str = Field(default="0988888888", description="Customer phone number (Caller ID)")
    name: str = Field(default="Quý khách", description="Customer name")
    city: Optional[str] = Field(default=None, description="Optional city or None for nationwide")


class TurnRequest(BaseModel):
    message: str = Field(..., description="Customer utterance / input message")


class TTSRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize to Vietnamese speech")
    voice: Optional[str] = Field(default="vi-VN-HoaiMyNeural", description="Azure voice name")


def extract_booking_state(runner: SessionRunner) -> Dict[str, Any]:
    """Extract and format rich state from LangGraph for frontend visualization."""
    if not runner.session_id:
        return {}

    config = {"configurable": {"thread_id": runner.session_id}}
    state_snap = runner.graph.get_state(config)
    if not state_snap or not state_snap.values:
        return {}

    vals = state_snap.values
    slots = vals.get("booking_slots", {})

    pickup = slots.get("pickup", {})
    dest = slots.get("destination", {})
    pickup_time = slots.get("pickup_time", {})
    vehicle_type = slots.get("vehicle_type", {})
    passengers = slots.get("passengers", {})

    return {
        "booking_status": vals.get("booking_status", "collecting"),
        "ready_to_book": vals.get("ready_to_book", False),
        "booking_revision": vals.get("booking_revision", 0),
        "is_terminal": vals.get("is_terminal", False),
        "booking_id": vals.get("booking_id"),
        "primary_intent": vals.get("primary_intent"),
        "current_focus": vals.get("current_focus"),
        "turn_index": vals.get("turn_index", 0),
        "slots": {
            "pickup": {
                "raw": pickup.get("raw"),
                "formatted": pickup.get("formatted"),
                "coords": pickup.get("coords"),
                "status": pickup.get("status", "empty"),
                "note": pickup.get("note"),
                "gate_id": pickup.get("gate_id"),
            },
            "destination": {
                "raw": dest.get("raw"),
                "formatted": dest.get("formatted"),
                "coords": dest.get("coords"),
                "status": dest.get("status", "empty"),
                "note": dest.get("note"),
            },
            "pickup_time": {
                "raw": pickup_time.get("raw"),
                "value": pickup_time.get("value"),
                "status": pickup_time.get("status", "empty"),
            },
            "vehicle_type": {
                "value": vehicle_type.get("value"),
                "status": vehicle_type.get("status", "empty"),
            },
            "passengers": {
                "value": passengers.get("value"),
                "status": passengers.get("status", "empty"),
            },
            "distance_km": slots.get("distance_km"),
            "duration_minutes": slots.get("duration_minutes"),
            "general_note": slots.get("general_note"),
        },
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint indicating LLM and map modes."""
    azure_key = os.getenv("AZURE_SPEECH_KEY")
    azure_region = os.getenv("AZURE_SPEECH_REGION", "southeastasia")
    return {
        "status": "online",
        "llm_mode": settings.LLM_MODE,
        "map_mode": settings.MAP_MODE,
        "rag_enabled": settings.RAG_ENABLED,
        "azure_tts_available": bool(azure_key and azure_region),
        "timestamp": now_iso(settings.SESSION_TIMEZONE),
    }


@app.post("/api/sessions")
async def create_session(payload: CreateSessionRequest):
    """Start a new caller session with custom name, phone and city."""
    phone = payload.phone.strip() if payload.phone else "0988888888"
    name = payload.name.strip() if payload.name else "Quý khách"
    city = payload.city.strip() if payload.city else None
    if city and city.lower() in {"none", "null", "toan quoc", "toàn quốc", ""}:
        city = None

    runner = SessionRunner(
        phone=phone,
        name=name,
        city=city,
        debug=settings.DEBUG,
    )
    session_id = runner.start_new_session()

    greeting = f"Dạ ParrotGo xin chào {name}! Em có thể hỗ trợ mình đặt xe đến đâu ạ?"

    # Initial history
    history = [
        {
            "role": "bot",
            "text": greeting,
            "timestamp": now_iso(settings.SESSION_TIMEZONE),
        }
    ]

    sessions_db[session_id] = {
        "runner": runner,
        "phone": phone,
        "name": name,
        "city": city,
        "history": history,
        "created_at": now_iso(settings.SESSION_TIMEZONE),
    }

    state = extract_booking_state(runner)

    return {
        "session_id": session_id,
        "phone": phone,
        "name": name,
        "city": city or "Toàn quốc",
        "greeting": greeting,
        "booking_state": state,
    }


@app.post("/api/sessions/{session_id}/turns")
async def process_turn(session_id: str, payload: TurnRequest):
    """Handle a conversational turn from the user."""
    session_data = sessions_db.get(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Phiên làm việc không tồn tại hoặc đã hết hạn.")

    runner: SessionRunner = session_data["runner"]
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Nội dung tin nhắn không được để trống.")

    # Record user message in history
    session_data["history"].append({
        "role": "user",
        "text": message,
        "timestamp": now_iso(settings.SESSION_TIMEZONE),
    })

    try:
        bot_response = runner.handle_turn(message)
    except Exception as e:
        bot_response = "Dạ hiện tại hệ thống đang bận một chút, quý khách vui lòng thử lại nhé ạ."

    # Record bot message in history
    session_data["history"].append({
        "role": "bot",
        "text": bot_response,
        "timestamp": now_iso(settings.SESSION_TIMEZONE),
    })

    is_terminal = runner.is_session_terminal()
    booking_state = extract_booking_state(runner)

    return {
        "session_id": session_id,
        "user_message": message,
        "bot_response": bot_response,
        "is_terminal": is_terminal,
        "booking_state": booking_state,
    }


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Retrieve full details and conversation history for a session."""
    session_data = sessions_db.get(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Phiên làm việc không tồn tại.")

    runner: SessionRunner = session_data["runner"]
    return {
        "session_id": session_id,
        "phone": session_data["phone"],
        "name": session_data["name"],
        "city": session_data["city"] or "Toàn quốc",
        "history": session_data["history"],
        "booking_state": extract_booking_state(runner),
    }


@app.delete("/api/sessions/{session_id}")
async def end_session(session_id: str):
    """End and clean up a conversation session."""
    if session_id in sessions_db:
        del sessions_db[session_id]
        return {"status": "success", "message": "Đã kết thúc phiên trò chuyện."}
    return {"status": "not_found"}


@app.post("/api/tts")
async def generate_speech(payload: TTSRequest):
    """Generate Vietnamese voice audio using Azure Cognitive Services Neural TTS."""
    azure_key = os.getenv("AZURE_SPEECH_KEY")
    azure_region = os.getenv("AZURE_SPEECH_REGION", "southeastasia")

    if not azure_key or not azure_region:
        raise HTTPException(status_code=503, detail="Azure Speech Key chưa được cấu hình trong .env")

    url = f"https://{azure_region}.tts.speech.microsoft.com/cognitiveservices/v1"
    voice = payload.voice or "vi-VN-HoaiMyNeural"
    clean_text = payload.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    ssml = f"""<speak version='1.0' xml:lang='vi-VN'>
        <voice name='{voice}'>
            {clean_text}
        </voice>
    </speak>"""

    headers = {
        "Ocp-Apim-Subscription-Key": azure_key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
        "User-Agent": "ParrotGo-Web",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, headers=headers, content=ssml.encode("utf-8"))
            if resp.status_code == 200:
                return Response(content=resp.content, media_type="audio/mpeg")
            else:
                raise HTTPException(status_code=resp.status_code, detail=f"Azure TTS Error: {resp.text}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi khi gọi Azure TTS: {str(exc)}")


# Serve static web frontend
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def serve_index():
    """Serve main web UI index."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "ParrotGo Web UI frontend not built yet"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.web.server:app", host="127.0.0.1", port=8000, reload=True)
