from __future__ import annotations

import database as db

TERMINAL_STATES = {"CONFIRMED", "DECLINED", "ESCALATED"}

MAX_ATTEMPTS = 5

# Maps (current_state, action) -> next_state
TRANSITIONS: dict[tuple[str, str], str] = {
    # First outreach sent, they replied
    ("FIRST_OUTREACH_SENT", "confirm_attendance"): "CONFIRMED",
    ("FIRST_OUTREACH_SENT", "request_calendar_acceptance"): "REPLIED",
    ("FIRST_OUTREACH_SENT", "request_reschedule"): "DECLINED",
    ("FIRST_OUTREACH_SENT", "mark_declined"): "DECLINED",
    ("FIRST_OUTREACH_SENT", "escalate_high_risk"): "ESCALATED",
    # Awaiting reply
    ("AWAITING_REPLY", "confirm_attendance"): "CONFIRMED",
    ("AWAITING_REPLY", "request_calendar_acceptance"): "REPLIED",
    ("AWAITING_REPLY", "request_reschedule"): "DECLINED",
    ("AWAITING_REPLY", "mark_declined"): "DECLINED",
    ("AWAITING_REPLY", "escalate_high_risk"): "ESCALATED",
    # Replied (we sent a nudge, they responded again)
    ("REPLIED", "confirm_attendance"): "CONFIRMED",
    ("REPLIED", "request_calendar_acceptance"): "REPLIED",
    ("REPLIED", "request_reschedule"): "DECLINED",
    ("REPLIED", "mark_declined"): "DECLINED",
    ("REPLIED", "escalate_high_risk"): "ESCALATED",
}


async def transition(contact_id: int, current_state: str, action: str, attempt_number: int) -> str:
    """Apply a state transition and update the contact. Returns the new state."""
    if attempt_number >= MAX_ATTEMPTS:
        new_state = "ESCALATED"
    else:
        new_state = TRANSITIONS.get((current_state, action), current_state)

    await db.update_contact(contact_id, current_state=new_state)
    return new_state
