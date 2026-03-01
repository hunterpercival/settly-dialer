"""Twilio inbound SMS webhook + SMS processing logic."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response

import database as db
from models import InteractionInput
from services import claude_service, sms_service
from state_machine import transition

logger = logging.getLogger(__name__)

router = APIRouter()


def _hours_until(event_time_utc: str) -> float:
    event_dt = datetime.fromisoformat(event_time_utc.replace("Z", "+00:00"))
    if event_dt.tzinfo is None:
        event_dt = event_dt.replace(tzinfo=timezone.utc)
    delta = event_dt - datetime.now(timezone.utc)
    return max(delta.total_seconds() / 3600, 0)


def _localize_event_time(event_time_utc: str, tz_name: str) -> str:
    try:
        from zoneinfo import ZoneInfo
        dt = datetime.fromisoformat(event_time_utc.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo(tz_name))
        return local_dt.strftime("%A, %B %d at %I:%M %p %Z")
    except Exception:
        return event_time_utc


async def process_inbound(phone: str, body: str, rsvp_override: str | None = None) -> dict:
    """Core logic for processing an inbound SMS. Returns the decision dict."""
    contact = await db.get_contact_by_phone(phone)
    if not contact:
        logger.warning("Inbound SMS from unknown number: %s", phone)
        return {"error": "unknown_contact"}

    await db.insert_message(contact.id, "inbound", body)

    rsvp = rsvp_override or contact.rsvp_status
    if rsvp != contact.rsvp_status:
        await db.update_contact(contact.id, rsvp_status=rsvp)

    new_attempt = contact.attempt_number + 1
    await db.update_contact(contact.id, attempt_number=new_attempt)

    hours = _hours_until(contact.event_time_utc)
    interaction = InteractionInput(
        contact_name=contact.name,
        phone_number=contact.phone,
        event_time_local=_localize_event_time(contact.event_time_utc, contact.timezone),
        rsvp_status=rsvp,
        attempt_number=new_attempt,
        time_until_event_hours=hours,
        last_user_message=body,
        current_state=contact.current_state,
    )

    history = await db.get_messages(contact.id)
    decision = claude_service.decide(interaction, history)

    await db.insert_message(
        contact.id, "outbound", decision.message_to_user,
        action=decision.action, reason=decision.reason,
    )

    new_state = await transition(
        contact.id, contact.current_state, decision.action, new_attempt,
    )
    logger.info(
        "Contact %s (%s): %s -> %s (action=%s)",
        contact.id, contact.name, contact.current_state, new_state, decision.action,
    )

    return {
        "message_to_user": decision.message_to_user,
        "action": decision.action,
        "reason": decision.reason,
        "new_state": new_state,
        "attempt_number": new_attempt,
    }


@router.post("/webhooks/sms")
async def handle_inbound_sms(request: Request):
    """Twilio inbound SMS webhook."""
    form = await request.form()
    from_number = form.get("From", "")
    body = form.get("Body", "").strip()

    if not from_number or not body:
        return Response(status_code=200)

    result = await process_inbound(from_number, body)

    if "error" not in result:
        contact = await db.get_contact_by_phone(from_number)
        try:
            sms_service.send_sms(contact.phone, result["message_to_user"])
        except Exception:
            logger.exception("Failed to send SMS to %s", from_number)

    return Response(status_code=200)
