"""Simulation endpoints for testing SMS conversations without Twilio."""
from __future__ import annotations

import logging

from fastapi import APIRouter

import database as db
from models import CreateContactRequest, SimulateRequest, InteractionInput
from services import claude_service
from state_machine import transition
from routers.sms_webhooks import _hours_until, _localize_event_time

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulate", tags=["simulate"])


@router.post("/contact")
async def create_test_contact(req: CreateContactRequest):
    """Create a test contact for simulation."""
    contact_id = await db.insert_contact(
        name=req.name,
        phone=req.phone,
        event_time_utc=req.event_time_utc,
        email=req.email,
        tz=req.timezone,
        event_description=req.event_description,
    )
    return {"contact_id": contact_id, "status": "created"}


@router.post("/sms")
async def simulate_sms(req: SimulateRequest):
    """Simulate an inbound SMS without Twilio. Returns Claude's decision."""
    contact = await db.get_contact_by_phone(req.phone)
    if not contact:
        return {"error": "Contact not found. Create one first via POST /simulate/contact"}

    await db.insert_message(contact.id, "inbound", req.message)

    rsvp = req.rsvp_status or contact.rsvp_status
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
        last_user_message=req.message,
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

    return {
        "contact_name": contact.name,
        "their_message": req.message,
        "agent_reply": decision.message_to_user,
        "action": decision.action,
        "reason": decision.reason,
        "state": f"{contact.current_state} -> {new_state}",
        "attempt": new_attempt,
        "rsvp_status": rsvp,
        "reply_length": len(decision.message_to_user),
    }


@router.post("/first-outreach")
async def simulate_first_outreach(req: SimulateRequest):
    """Simulate the first outreach message (no inbound message needed)."""
    contact = await db.get_contact_by_phone(req.phone)
    if not contact:
        return {"error": "Contact not found. Create one first via POST /simulate/contact"}

    rsvp = req.rsvp_status or contact.rsvp_status
    hours = _hours_until(contact.event_time_utc)

    interaction = InteractionInput(
        contact_name=contact.name,
        phone_number=contact.phone,
        event_time_local=_localize_event_time(contact.event_time_utc, contact.timezone),
        rsvp_status=rsvp,
        attempt_number=1,
        time_until_event_hours=hours,
        last_user_message=None,
        current_state="NEW",
    )

    decision = claude_service.decide(interaction, [])

    await db.insert_message(
        contact.id, "outbound", decision.message_to_user,
        action=decision.action, reason=decision.reason,
    )
    await db.update_contact(
        contact.id, current_state="FIRST_OUTREACH_SENT", attempt_number=1,
    )

    return {
        "contact_name": contact.name,
        "first_outreach": decision.message_to_user,
        "action": decision.action,
        "reason": decision.reason,
        "state": "NEW -> FIRST_OUTREACH_SENT",
        "reply_length": len(decision.message_to_user),
    }


@router.get("/conversation/{phone}")
async def get_conversation(phone: str):
    """View the full conversation history for a contact."""
    contact = await db.get_contact_by_phone(phone)
    if not contact:
        return {"error": "Contact not found"}

    messages = await db.get_messages(contact.id)
    return {
        "contact": {
            "name": contact.name,
            "phone": contact.phone,
            "state": contact.current_state,
            "rsvp": contact.rsvp_status,
            "attempts": contact.attempt_number,
        },
        "messages": [
            {
                "direction": m.direction,
                "body": m.body,
                "action": m.action,
                "reason": m.reason,
                "time": m.created_at,
            }
            for m in messages
        ],
    }


@router.get("/contacts")
async def list_contacts():
    """List all contacts and their current state."""
    contacts = await db.get_all_contacts()
    return [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "state": c.current_state,
            "rsvp": c.rsvp_status,
            "attempts": c.attempt_number,
            "event_time": c.event_time_utc,
        }
        for c in contacts
    ]
