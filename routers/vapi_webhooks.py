"""Vapi server-url webhook — receives call events, sends SMS follow-ups."""
from __future__ import annotations

import logging

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

        # Send SMS follow-up after call ends
        if customer_number:
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


def _build_follow_up_sms(summary: str, ended_reason: str) -> list:
    """Build SMS follow-up lines based on how the call went."""
    summary_lower = (summary or "").lower()

    if "accepted" in summary_lower and "invite" in summary_lower:
        return [
            "hey just following up from the call",
            "ur all set, see u soon!",
        ]

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
            "dan from settly",
            "could u accept the calendar invite so i know ur good to make it",
        ]

    if ended_reason == "voicemail":
        return [
            "hey left u a voicemail",
            "dan from settly",
            "just need u to accept the calendar invite so i know ur making it",
        ]

    if ended_reason not in ("assistant-error", "pipeline-error"):
        return [
            "hey just following up from the call",
            "if u haven't already, could u accept the calendar invite",
            "it just lets me know who's making it and who isn't",
        ]

    return []
