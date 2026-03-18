"""Settly Unified Agent — Voice (Vapi) + SMS (Claude) in one service."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

import database
import vapi_client
from config import settings
from services.sms_service import send_sms_background

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    logger.info("Settly unified agent starting up")
    yield
    logger.info("Settly unified agent shutting down")


app = FastAPI(title="Settly Unified Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Import routers ---
from routers import health, sms_webhooks, vapi_webhooks, simulate
from routers.chat import router as chat_router

app.include_router(health.router)
app.include_router(sms_webhooks.router)
app.include_router(vapi_webhooks.router)
app.include_router(simulate.router)
app.include_router(chat_router)


# ---------------------------------------------------------------------------
# Chat simulator UI
# ---------------------------------------------------------------------------

CHAT_HTML = Path(__file__).parent / "chat-simulator" / "index.html"


@app.get("/", response_class=HTMLResponse)
async def serve_chat_ui():
    return CHAT_HTML.read_text()


# ---------------------------------------------------------------------------
# Unified reach-out: Call + Text
# ---------------------------------------------------------------------------

@app.post("/reach-out")
async def reach_out(request: Request):
    """Call AND text someone at the same time."""
    body = await request.json()
    customer_number = body["customer_number"]
    contact_name = body.get("contact_name", "there")
    event_description = body.get("event_description", "a Discovery call")
    event_time_local = body.get("event_time_local", "your upcoming appointment")
    rsvp_status = body.get("rsvp_status", "needs_action")
    call_reason = body.get("call_reason", "just_booked")
    assistant_id = body.get("assistant_id")
    from_number = body.get("from_number")
    agent_name = body.get("agent_name", "Dan")
    company_name = body.get("company_name", "Martell Growth Solutions")

    # Send SMS first
    sms_lines = [
        f"hey {contact_name}, it's {agent_name} from {company_name}",
        f"i saw u booked in {event_description} for {event_time_local}",
        "could u accept the calendar invite so i know ur good to make it",
    ]
    send_sms_background(customer_number, sms_lines, from_number=from_number)

    # Then make the call
    call_data = vapi_client.make_call(
        customer_number=customer_number,
        contact_name=contact_name,
        call_purpose=event_description,
        event_time_local=event_time_local,
        rsvp_status=rsvp_status,
        assistant_id=assistant_id,
        agent_name=agent_name,
        company_name=company_name,
    )

    return {
        "call": call_data,
        "sms": "sent",
        "message": f"Called and texted {contact_name} at {customer_number}",
    }


# ---------------------------------------------------------------------------
# Voice management endpoints
# ---------------------------------------------------------------------------

@app.post("/call")
async def make_call(request: Request):
    body = await request.json()
    data = vapi_client.make_call(
        customer_number=body["customer_number"],
        contact_name=body.get("contact_name", "there"),
        event_time_local=body.get("event_time_local", "your upcoming appointment"),
        rsvp_status=body.get("rsvp_status", "needs_action"),
        contact_email=body.get("contact_email", ""),
        company_name=body.get("company_name", "Martell Growth Solutions"),
        agent_name=body.get("agent_name", "Dan"),
        call_purpose=body.get("call_purpose") or body.get("event_description", ""),
        phone_number_id=body.get("phone_number_id"),
        assistant_id=body.get("assistant_id"),
    )
    return data


@app.post("/text")
async def send_text(request: Request):
    """Send a text to someone."""
    body = await request.json()
    customer_number = body["customer_number"]
    contact_name = body.get("contact_name", "there")
    event_time_local = body.get("event_time_local", "your upcoming appointment")
    event_description = body.get("event_description", "a Discovery call")
    agent_name = body.get("agent_name", "Dan")
    company_name = body.get("company_name", "Martell Growth Solutions")

    from_number = body.get("from_number")
    lines = [
        f"hey {contact_name}, it's {agent_name} from {company_name}",
        f"i saw u booked in {event_description} for {event_time_local}",
        "could u accept the calendar invite so i know ur good to make it",
    ]
    send_sms_background(customer_number, lines, from_number=from_number)
    return {"status": "sent", "to": customer_number, "lines": lines}


@app.post("/assistant/create")
async def create_assistant(request: Request):
    body = await request.json() if await request.body() else {}
    name = body.get("name", "Confirmation Agent")
    server_url = body.get("server_url")
    voice_id = body.get("voice_id")
    first_message = body.get("first_message")
    data = vapi_client.create_assistant(
        name=name, server_url=server_url,
        voice_id=voice_id, first_message=first_message,
    )
    return data


@app.get("/assistant/list")
async def list_assistants():
    return vapi_client.list_assistants()


@app.patch("/assistant/{assistant_id}/update")
async def update_assistant_endpoint(assistant_id: str, request: Request):
    body = await request.json() if await request.body() else {}
    return vapi_client.update_assistant(assistant_id, body)


@app.get("/phone-numbers")
async def list_phone_numbers():
    return vapi_client.list_phone_numbers()


@app.post("/phone-number/import")
async def import_phone_number(request: Request):
    body = await request.json() if await request.body() else {}
    assistant_id = body.get("assistant_id")
    phone_number = body.get("phone_number", settings.twilio_phone_number)
    data = vapi_client.import_twilio_number(
        twilio_sid=settings.twilio_account_sid,
        twilio_token=settings.twilio_auth_token,
        phone_number=phone_number,
        assistant_id=assistant_id,
    )
    return data


@app.get("/call/{call_id}")
async def get_call(call_id: str):
    return vapi_client.get_call(call_id)


@app.get("/calls")
async def list_calls():
    return vapi_client.list_calls()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
