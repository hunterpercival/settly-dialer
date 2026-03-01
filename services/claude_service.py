from __future__ import annotations

import json
import logging

import anthropic

from config import settings
from models import DecisionOutput, InteractionInput, Message
from prompts import SMS_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

FALLBACK_DECISION = DecisionOutput(
    message_to_user="Please check your email and accept the calendar invite so it locks in.",
    action="request_calendar_acceptance",
    reason="fallback: failed to parse Claude response",
)


def decide(interaction: InteractionInput, history: list[Message]) -> DecisionOutput:
    """Send conversation context to Claude and get a structured decision."""
    messages = []

    # Build conversation history
    for msg in history:
        role = "user" if msg.direction == "inbound" else "assistant"
        content = msg.body
        if role == "assistant":
            content = json.dumps({
                "message_to_user": msg.body,
                "action": msg.action or "request_calendar_acceptance",
                "reason": msg.reason or "",
            })
        messages.append({"role": role, "content": content})

    # Build current context
    context_parts = [
        f"[SYSTEM CONTEXT]",
        f"Contact: {interaction.contact_name}",
        f"Phone: {interaction.phone_number}",
        f"Event time: {interaction.event_time_local}",
        f"RSVP status: {interaction.rsvp_status}",
        f"Attempt: {interaction.attempt_number}",
        f"Hours until event: {interaction.time_until_event_hours:.1f}",
        f"Current state: {interaction.current_state}",
    ]

    if interaction.last_user_message:
        context_parts.append(f"Their latest message: {interaction.last_user_message}")
    else:
        context_parts.append("No reply yet — generate follow-up.")

    context_parts.append(
        '\nRespond with JSON only: {"message_to_user": "...", "action": "...", "reason": "..."}'
    )

    context = "\n".join(context_parts)
    messages.append({"role": "user", "content": context})

    # Ensure messages start with "user" role and alternate properly
    messages = _fix_message_roles(messages)

    try:
        response = _client.messages.create(
            model=settings.claude_model,
            max_tokens=300,
            system=SMS_SYSTEM_PROMPT,
            messages=messages,
        )
        raw = response.content[0].text.strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        return DecisionOutput.model_validate_json(raw)
    except Exception:
        logger.exception("Failed to get/parse Claude decision")
        return FALLBACK_DECISION


def _fix_message_roles(messages: list[dict]) -> list[dict]:
    """Ensure messages alternate user/assistant and start with user."""
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
