"""ParrotGo CLI conversation runner."""

import argparse
import sys
import uuid
from typing import Any, Optional
from rich.console import Console

# Ensure UTF-8 encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    getattr(sys.stderr, "reconfigure")(encoding="utf-8")
if hasattr(sys.stdin, "reconfigure"):
    getattr(sys.stdin, "reconfigure")(encoding="utf-8")

from src.config import settings
from src.core.graph import build_parrotgo_graph
from src.core.state import create_initial_state
from src.core.time_utils import now_iso
from src.db.in_memory_cache import geo_cache
from pathlib import Path
from src.db.sqlite_manager import (
    PersistenceError,
    SQLiteManager,
)

console_err = Console(stderr=True)


class SessionRunner:
    def __init__(
        self,
        phone: str,
        name: str,
        city: Optional[str] = None,
        debug: bool = False,
        db_path: Optional[str] = None,
    ):
        self.phone = phone
        self.name = name
        nationwide = bool(city and city.strip().lower() in {"none", "null", "toan quoc", "toàn quốc"})
        self.city = None if nationwide else (city or settings.DEFAULT_SESSION_CITY)
        self.debug = debug or settings.DEBUG
        self.db = SQLiteManager(db_path=db_path or settings.PERSISTENT_DB_PATH)
        snapshot = Path(settings.GEO_DATA_PATH)
        if snapshot.exists():
            geo_cache.hydrate_snapshot(snapshot)
        if not geo_cache.export_dataset()["places"]:
            seed = Path(__file__).resolve().parents[2] / "data" / "seed_data" / "places.json"
            if seed.exists():
                import json
                geo_cache.upsert_dataset(json.loads(seed.read_text(encoding="utf-8")))
                geo_cache.persist_snapshot(snapshot)
        self.graph = build_parrotgo_graph(db_manager=self.db)
        self.session_id: Optional[str] = None
        self.is_first_turn = True

    def start_new_session(self) -> str:
        """Initialize session in database and prepare conversation graph."""
        self.session_id = str(uuid.uuid4())
        started_at = now_iso(settings.SESSION_TIMEZONE)
        self.db.start_session(
            session_id=self.session_id,
            phone=self.phone,
            name=self.name,
            session_city=self.city,
            timezone=settings.SESSION_TIMEZONE,
            started_at=started_at,
        )
        self.is_first_turn = True
        if self.debug:
            console_err.print(
                f"[bold cyan][DEBUG][/bold cyan] Started session {self.session_id} for {self.name} ({self.phone})"
            )
        return self.session_id

    def handle_turn(self, utterance: str) -> Optional[str]:
        """Invoke graph for single user turn."""
        if not self.session_id:
            self.start_new_session()

        received_at = now_iso(settings.SESSION_TIMEZONE)
        session_id = self.session_id or self.start_new_session()
        thread_id = session_id
        config: Any = {"configurable": {"thread_id": thread_id}}

        if self.is_first_turn:
            init_state = create_initial_state(
                session_id=session_id,
                customer_phone=self.phone,
                customer_name=self.name,
                turn_received_at=received_at,
                session_city=self.city,
                timezone=settings.SESSION_TIMEZONE,
            )
            init_state["user_current_input"] = utterance
            input_payload: Any = init_state
            self.is_first_turn = False
        else:
            input_payload: Any = {
                "user_current_input": utterance,
                "turn_received_at": received_at,
            }

        try:
            result = self.graph.invoke(input_payload, config=config)
            bot_text = result.get("final_response_text", "")

            if self.debug:
                console_err.print(
                    f"[bold green][STATE][/bold green] status={result.get('booking_status')} "
                    f"ready={result.get('ready_to_book')} revision={result.get('booking_revision')}"
                )

            return bot_text
        except PersistenceError as pe:
            console_err.print(f"[bold red][PERSISTENCE ERROR][/bold red] {pe}")
            return "Dạ hiện tại em chưa thể xác nhận việc lưu yêu cầu, mình thử lại sau giúp em ạ."
        except Exception as e:
            if self.debug:
                console_err.print(f"[bold red][GRAPH ERROR][/bold red] {e}")
            raise

    def is_session_terminal(self) -> bool:
        """Check if current session has reached terminal status."""
        if not self.session_id:
            return False
        config: Any = {"configurable": {"thread_id": self.session_id}}
        current = self.graph.get_state(config)
        if current and current.values:
            return bool(current.values.get("is_terminal", False))
        return False


def run_interactive_cli():
    parser = argparse.ArgumentParser(description="ParrotGo CLI Booking Assistant")
    parser.add_argument("--phone", default=None, help="Customer phone number (Caller ID)")
    parser.add_argument("--name", default=None, help="Customer name (CRM profile)")
    parser.add_argument("--city", default=None, help="Session city (Leave empty for nationwide call center)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logs to stderr")
    parser.add_argument("--non-interactive", action="store_true", help="Skip interactive metadata prompts")

    args = parser.parse_args()

    phone = args.phone
    name = args.name
    city = args.city

    # Interactive prompt if executed from a terminal without pre-supplied CLI arguments
    if not args.non_interactive and sys.stdin.isatty():
        if not phone or not name or city is None:
            console_err.print("\n[bold cyan]╔══════════════════════════════════════════════════════════════════════════╗[/bold cyan]")
            console_err.print("[bold cyan]║               PARROTGO VOICEBOT - THIẾT LẬP CUỘC GỌI                     ║[/bold cyan]")
            console_err.print("[bold cyan]╚══════════════════════════════════════════════════════════════════════════╝[/bold cyan]")
            console_err.print("[dim]Trong hệ thống thực tế, SĐT và Tên được lấy từ tín hiệu Caller ID và CRM tổng đài.[/dim]\n")

        if not phone:
            console_err.print("[bold yellow]1. Số điện thoại người gọi[/bold yellow] [dim](Nhấn Enter dùng mặc định '0988888888'):[/dim] ", end="")
            val = sys.stdin.readline().strip()
            phone = val if val else "0988888888"

        if not name:
            console_err.print("[bold yellow]2. Tên khách hàng[/bold yellow] [dim](Nhấn Enter dùng mặc định 'Quý khách'):[/dim] ", end="")
            val = sys.stdin.readline().strip()
            name = val if val else "Quý khách"

        if city is None:
            console_err.print("[bold yellow]3. Tỉnh/Thành phố khách đang gọi[/bold yellow] [dim](Nhấn Enter = Chế độ TOÀN QUỐC):[/dim] ", end="")
            val = sys.stdin.readline().strip()
            city = val if val else None
    else:
        phone = phone or "0988888888"
        name = name or "Quý khách"

    if city and city.strip().lower() in {"none", "null", "toan quoc", "toàn quốc"}:
        city = "toàn quốc"

    runner = SessionRunner(
        phone=phone,
        name=name,
        city=city,
        debug=args.debug,
    )
    runner.start_new_session()

    city_desc = f"[cyan]{city}[/cyan]" if city else "[bold green]TOÀN QUỐC[/bold green] [dim](tổng đài tự hỏi làm rõ khi cần)[/dim]"
    console_err.print(
        f"\n[bold green]✓ ParrotGo Assistant Ready[/bold green]\n"
        f"  • Khách hàng: [cyan]{name}[/cyan] ({phone})\n"
        f"  • Khu vực phiên: {city_desc}\n"
    )
    console_err.print("[dim]Nhập phát ngôn của bạn và nhấn Enter. Nhấn Ctrl+C hoặc EOF để thoát.[/dim]\n")

    try:
        while True:
            try:
                console_err.print("[bold blue]Khách:[/bold blue] ", end="")
                try:
                    utterance = input().strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not utterance:
                    continue

                response = runner.handle_turn(utterance)
                if sys.stdout.isatty():
                    console_err.print(f"[bold magenta]Bot:[/bold magenta] {response}\n")
                else:
                    # Pure TTS stream output when piped
                    print(response, flush=True)

                if runner.is_session_terminal():
                    console_err.print("\n[yellow]Phiên đặt xe đã hoàn thành/kết thúc.[/yellow]")
                    break
            except (KeyboardInterrupt, EOFError):
                break
    finally:
        console_err.print("\n[dim]Tạm biệt quý khách![/dim]")


if __name__ == "__main__":
    run_interactive_cli()
