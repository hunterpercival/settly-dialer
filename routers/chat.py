"""Chat simulator endpoint — test SMS AI in-browser without Twilio."""
import json
import logging
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

import anthropic
from config import settings
from prompts import SMS_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []
    system_prompt: Optional[str] = None
    rsvp_status: str = "needsAction"
    attempt_number: int = 1
    time_until_event_hours: float = 48.0
    contact_name: str = "Sarah"
    event_time_local: str = "Friday at 2:00 PM"
    current_state: str = "FIRST_OUTREACH_SENT"


class ChatResponse(BaseModel):
    message_to_user: str
    action: str
    reason: str
    raw_response: Optional[str] = None


def _fix_message_roles(messages: List[dict]) -> List[dict]:
    if not messages:
        return messages
    fixed = []
    for msg in messages:
        if fixed and fixed[-1]["role"] == msg["role"]:
            fixed[-1]["content"] += "\n" + msg["content"]
        else:
            fixed.append(dict(msg))
    if fixed and fixed[0]["role"] != "user":
        fixed.insert(0, {"role": "user", "content": "[conversation start]"})
    return fixed


@router.post("/send")
async def chat_send(req: ChatRequest) -> ChatResponse:
    """Send a message through the AI engine and get a response."""
    system_prompt = req.system_prompt or SMS_SYSTEM_PROMPT

    messages = []
    for msg in req.history:
        messages.append({"role": msg.role, "content": msg.content})

    context_parts = [
        "[SYSTEM CONTEXT]",
        f"Contact: {req.contact_name}",
        f"Event time: {req.event_time_local}",
        f"RSVP status: {req.rsvp_status}",
        f"Attempt: {req.attempt_number}",
        f"Hours until event: {req.time_until_event_hours:.1f}",
        f"Current state: {req.current_state}",
    ]

    if req.message:
        context_parts.append(f"Their latest message: {req.message}")
    else:
        context_parts.append("No reply yet — generate first outreach or follow-up.")

    context_parts.append(
        '\nRespond with JSON only: {"message_to_user": "...", "action": "...", "reason": "..."}'
    )

    messages.append({"role": "user", "content": "\n".join(context_parts)})
    messages = _fix_message_roles(messages)

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=300,
            system=system_prompt,
            messages=messages,
        )
        raw = response.content[0].text.strip()

        cleaned = raw
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        parsed = json.loads(cleaned)
        return ChatResponse(
            message_to_user=parsed.get("message_to_user", ""),
            action=parsed.get("action", "request_calendar_acceptance"),
            reason=parsed.get("reason", ""),
            raw_response=raw,
        )
    except anthropic.AuthenticationError:
        return ChatResponse(
            message_to_user="[API KEY ERROR] Set a valid ANTHROPIC_API_KEY in your .env file.",
            action="error",
            reason="Invalid or missing API key",
            raw_response=None,
        )
    except Exception as e:
        logger.exception("Chat send failed")
        return ChatResponse(
            message_to_user="[ERROR] Failed to get response from Claude.",
            action="error",
            reason=str(e),
            raw_response=None,
        )


@router.get("/default-prompt")
async def get_default_prompt():
    """Return the default system prompt so the UI can display it."""
    return {"prompt": SMS_SYSTEM_PROMPT}


@router.post("/first-outreach")
async def chat_first_outreach(req: ChatRequest) -> ChatResponse:
    """Generate the first outreach message (no user message needed)."""
    req.message = ""
    req.attempt_number = 1
    req.current_state = "NEW"
    req.history = []
    return await chat_send(req)
