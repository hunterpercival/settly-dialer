"""Vapi server-url webhook — receives call events, sends SMS follow-ups."""
from __future__ import annotations

import logging
import re
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from services.sms_service import send_sms_background

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    """Handle Vapi server-url events. Sends SMS follow-up after call ends."""
    body = await request.json()
    message_type = body.get("message", {}).get("type", "unknown")
    logger.info("Vapi webhook received: %s", message_type)

    if message_type == "status-update":
        status = body["message"].get("status")
        call_id = body["message"].get("call", {}).get("id")
        logger.info("Call %s status: %s", call_id, status)
        return JSONResponse({"ok": True})

    if message_type == "end-of-call-report":
        call_id = body["message"].get("call", {}).get("id")
        transcript = body["message"].get("transcript", "")
        summary = body["message"].get("summary", "")
        ended_reason = body["message"].get("endedReason", "")
        duration = body["message"].get("call", {}).get("duration")
        customer_number = body["message"].get("call", {}).get("customer", {}).get("number", "")

        logger.info(
            "Call %s ended (%s) — duration: %ss\nSummary: %s",
            call_id, ended_reason, duration, summary,
        )
        logger.info("Transcript:\n%s", transcript)

        # Extract contact name from the call's first message or summary
        first_message = body["message"].get("call", {}).get("assistantOverrides", {}).get("firstMessage", "")
        contact_name = _extract_name(first_message, summary)

        # Send SMS follow-up after call ends
        if customer_number:
            if _is_confirmed(summary):
                # Confirmed — send value guide after 10 second delay
                _send_delayed_confirmation_sms(customer_number, contact_name, delay=10)
            else:
                sms_lines = _build_follow_up_sms(summary, ended_reason)
                if sms_lines:
                    send_sms_background(customer_number, sms_lines)

        return JSONResponse({"ok": True})

    if message_type in ("hang", "speech-update"):
        return JSONResponse({"ok": True})

    if message_type == "transcript":
        role = body["message"].get("role", "")
        text = body["message"].get("transcript", "")
        logger.info("Transcript [%s]: %s", role, text)
        return JSONResponse({"ok": True})

    logger.info("Unhandled webhook type: %s — body: %s", message_type, body)
    return JSONResponse({"ok": True})


VALUE_GUIDE_URL = "https://settly.up.railway.app/settly-value-guide.pdf"


def _is_confirmed(summary: str) -> bool:
    """Check if the call summary indicates the prospect confirmed."""
    s = (summary or "").lower()
    return ("accepted" in s and "invite" in s) or "confirmed" in s


def _extract_name(first_message: str, summary: str) -> str:
    """Try to extract contact name from the first message or summary."""
    # First message is usually "Hey, is this {name}?"
    match = re.search(r"is this (.+?)[\?\.]", first_message, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Fallback: look for a capitalized name near the start of the summary
    match = re.search(r"(?:called|spoke with|contacted)\s+([A-Z][a-z]+)", summary or "")
    if match:
        return match.group(1)
    return "there"


def _send_delayed_confirmation_sms(customer_number: str, contact_name: str, delay: int = 20):
    """Send the 3-part confirmation + value guide SMS after a delay."""
    def _send():
        import time
        time.sleep(delay)
        lines = [
            f"thanks for confirming {contact_name}!",
            "let me know if you have any questions before the call",
        ]
        send_sms_background(customer_number, lines)

    t = threading.Thread(target=_send, daemon=True)
    t.start()
    logger.info("Scheduled confirmation SMS to %s in %ds", customer_number, delay)


def _build_follow_up_sms(summary: str, ended_reason: str) -> list:
    """Build SMS follow-up lines based on how the call went."""
    summary_lower = (summary or "").lower()

    if "will accept" in summary_lower or "accept later" in summary_lower or "check" in summary_lower:
        return [
            "hey it was good chatting",
            "just a reminder to accept the calendar invite when u get a sec",
            "it just lets me know ur good to make it",
        ]

    if "reschedule" in summary_lower or "different time" in summary_lower:
        return [
            "hey thanks for chatting",
            "we'll get that rescheduled for u",
            "keep an eye out for the new calendar invite",
        ]

    if ended_reason in ("customer-did-not-answer", "customer-busy", "no-answer"):
        return [
            "hey tried giving u a call",
            "could u accept the calendar invite so i know ur good to make it",
        ]

    if ended_reason == "voicemail":
        return [
            "hey left u a voicemail",
            "just need u to accept the calendar invite so i know ur making it",
        ]

    if ended_reason not in ("assistant-error", "pipeline-error"):
        return [
            "hey just following up from the call",
            "if u haven't already, could u accept the calendar invite",
            "it just lets me know who's making it and who isn't",
        ]

    return []
