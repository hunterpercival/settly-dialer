from typing import Literal, Optional

from pydantic import BaseModel


# --- Pydantic schemas ---

class InteractionInput(BaseModel):
    channel: Literal["sms"] = "sms"
    contact_name: str
    phone_number: str
    event_time_local: str
    rsvp_status: Literal["needsAction", "accepted", "declined"]
    attempt_number: int
    time_until_event_hours: float
    last_user_message: Optional[str]
    current_state: str


class DecisionOutput(BaseModel):
    message_to_user: str
    action: Literal[
        "confirm_attendance",
        "request_calendar_acceptance",
        "request_reschedule",
        "mark_declined",
        "no_answer",
        "escalate_high_risk",
    ]
    reason: str


# --- API request schemas ---

class CreateContactRequest(BaseModel):
    name: str
    phone: str
    event_time_utc: str
    email: str = ""
    timezone: str = "UTC"
    event_description: str = ""
    rsvp_status: str = "needsAction"


class SimulateRequest(BaseModel):
    phone: str
    message: str
    rsvp_status: Optional[str] = None


# --- DB row classes ---

class Contact:
    def __init__(
        self,
        id: int,
        name: str,
        phone: str,
        email: str,
        timezone: str,
        event_time_utc: str,
        event_description: str,
        rsvp_status: str,
        current_state: str,
        attempt_number: int,
        created_at: str,
        updated_at: str,
    ):
        self.id = id
        self.name = name
        self.phone = phone
        self.email = email
        self.timezone = timezone
        self.event_time_utc = event_time_utc
        self.event_description = event_description
        self.rsvp_status = rsvp_status
        self.current_state = current_state
        self.attempt_number = attempt_number
        self.created_at = created_at
        self.updated_at = updated_at


class Message:
    def __init__(
        self,
        id: int,
        contact_id: int,
        direction: str,
        body: str,
        action: Optional[str],
        reason: Optional[str],
        created_at: str,
    ):
        self.id = id
        self.contact_id = contact_id
        self.direction = direction
        self.body = body
        self.action = action
        self.reason = reason
        self.created_at = created_at
