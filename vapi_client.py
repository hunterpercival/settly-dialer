"""Vapi API client for managing assistants and making calls."""
from __future__ import annotations

import logging
from typing import Optional

import requests

from config import settings
from prompts import VOICE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

BASE_URL = "https://api.vapi.ai"

# Shared Vapi phone number (same across tenants)
PHONE_NUMBER_ID = "8c869ab1-dbfa-43be-b743-7a7ae5ba1496"


def _headers():
    return {
        "Authorization": f"Bearer {settings.vapi_api_key}",
        "Content-Type": "application/json",
    }


def _build_prompt(
    contact_name: str = "there",
    event_time_local: str = "your upcoming appointment",
    rsvp_status: str = "needs_action",
    contact_email: str = "",
    company_name: str = "",
    agent_name: str = "Dan",
    call_purpose: str = "",
) -> str:
    """Fill in the system prompt template with call-specific context."""
    return (
        VOICE_SYSTEM_PROMPT
        .replace("{contact_name}", contact_name)
        .replace("{event_time_local}", event_time_local)
        .replace("{rsvp_status}", rsvp_status)
        .replace("{contact_email}", contact_email)
        .replace("{company_name}", company_name)
        .replace("{agent_name}", agent_name)
        .replace("{call_purpose}", call_purpose or "a Discovery call")
    )


def _first_message(contact_name: str) -> str:
    """Short opener — just confirm who you're talking to."""
    return f"Hey, is this {contact_name}?"


def make_call(
    customer_number: str,
    contact_name: str = "there",
    event_time_local: str = "your upcoming appointment",
    rsvp_status: str = "needs_action",
    contact_email: str = "",
    company_name: str = "",
    agent_name: str = "Dan",
    call_purpose: str = "",
    phone_number_id: Optional[str] = None,
    assistant_id: Optional[str] = None,
    **kwargs,
) -> dict:
    """Make an outbound confirmation call with context-aware script."""
    if not assistant_id:
        raise ValueError("assistant_id is required — each tenant must have their own Vapi assistant")
    aid = assistant_id
    pid = phone_number_id or PHONE_NUMBER_ID

    prompt = _build_prompt(
        contact_name=contact_name,
        event_time_local=event_time_local,
        rsvp_status=rsvp_status,
        contact_email=contact_email,
        company_name=company_name,
        agent_name=agent_name,
        call_purpose=call_purpose,
    )
    first_msg = _first_message(contact_name)

    payload = {
        "assistantId": aid,
        "phoneNumberId": pid,
        "customer": {"number": customer_number},
        "assistantOverrides": {
            "firstMessage": first_msg,
            "model": {
                "provider": "openai",
                "model": "gpt-4o",
                "messages": [{"role": "system", "content": prompt}],
                "temperature": 0.7,
            },
        },
    }

    resp = requests.post(f"{BASE_URL}/call", headers=_headers(), json=payload)
    resp.raise_for_status()
    data = resp.json()
    logger.info(
        "Call initiated: %s -> %s (id: %s)",
        pid, customer_number, data.get("id"),
    )
    return data


# ---------------------------------------------------------------------------
# Assistant management
# ---------------------------------------------------------------------------

def create_assistant(
    name: str = "Settly Confirmation Agent",
    server_url: Optional[str] = None,
    voice_id: Optional[str] = None,
    first_message: Optional[str] = None,
) -> dict:
    """Create a persistent Vapi assistant."""
    vid = voice_id or "bIHbv24MWmeRgasZH58o"
    payload = {
        "name": name,
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "system", "content": VOICE_SYSTEM_PROMPT}],
            "temperature": 0.9,
        },
        "voice": {
            "provider": "11labs",
            "voiceId": vid,
            "stability": 0.25,
            "similarityBoost": 0.5,
            "style": 0.7,
            "useSpeakerBoost": True,
        },
        "firstMessage": first_message or "Hey, is this {contact_name}?",
        "endCallMessage": "Cool, talk later!",
        "maxDurationSeconds": 210,
        "silenceTimeoutSeconds": 30,
        "responseDelaySeconds": 0.2,
        "endCallPhrases": ["goodbye", "have a good one", "talk to you later", "take care", "see you later", "alright bye", "okay bye", "thanks bye"],
        "endCallFunctionEnabled": True,
        "startSpeakingPlan": {
            "waitSeconds": 0.8,
            "smartEndpointingEnabled": True,
        },
    }
    if server_url:
        payload["serverUrl"] = server_url

    resp = requests.post(f"{BASE_URL}/assistant", headers=_headers(), json=payload)
    resp.raise_for_status()
    data = resp.json()
    logger.info("Created assistant: %s (id: %s)", data.get("name"), data.get("id"))
    return data


def list_assistants() -> list:
    resp = requests.get(f"{BASE_URL}/assistant", headers=_headers())
    resp.raise_for_status()
    return resp.json()


def get_assistant(assistant_id: str) -> dict:
    resp = requests.get(f"{BASE_URL}/assistant/{assistant_id}", headers=_headers())
    resp.raise_for_status()
    return resp.json()


def update_assistant(assistant_id: str, updates: dict) -> dict:
    resp = requests.patch(
        f"{BASE_URL}/assistant/{assistant_id}", headers=_headers(), json=updates
    )
    resp.raise_for_status()
    return resp.json()


def get_call(call_id: str) -> dict:
    resp = requests.get(f"{BASE_URL}/call/{call_id}", headers=_headers())
    resp.raise_for_status()
    return resp.json()


def list_calls(limit: int = 10) -> list:
    resp = requests.get(f"{BASE_URL}/call", headers=_headers(), params={"limit": limit})
    resp.raise_for_status()
    return resp.json()


def list_phone_numbers() -> list:
    resp = requests.get(f"{BASE_URL}/phone-number", headers=_headers())
    resp.raise_for_status()
    return resp.json()


def import_twilio_number(
    twilio_sid: str,
    twilio_token: str,
    phone_number: str,
    assistant_id: Optional[str] = None,
) -> dict:
    payload = {
        "provider": "twilio",
        "number": phone_number,
        "twilioAccountSid": twilio_sid,
        "twilioAuthToken": twilio_token,
    }
    if assistant_id:
        payload["assistantId"] = assistant_id

    resp = requests.post(f"{BASE_URL}/phone-number", headers=_headers(), json=payload)
    resp.raise_for_status()
    data = resp.json()
    logger.info("Imported phone number: %s (id: %s)", phone_number, data.get("id"))
    return data
