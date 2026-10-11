"""
Request bodies, validated in one place (Pydantic). Invalid input -> 400 with a clear message.
Responses are plain JSON built in the route modules.
"""
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.core import config


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

    @field_validator("message")
    @classmethod
    def check_message(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Message is empty.")
        if len(v) > config.MAX_QUESTION_CHARS:
            raise ValueError(f"Please keep your message under {config.MAX_QUESTION_CHARS} characters.")
        return v


class FeedbackRequest(BaseModel):
    value: Optional[Literal["up", "down"]] = None


EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class HandoffRequest(BaseModel):
    """The "talk to a person" ticket form."""
    conversation_id: Optional[str] = None
    name: str = Field("", validate_default=True)       # missing fields get the same clear messages
    email: str = Field("", validate_default=True)
    issue: str = Field("", validate_default=True)

    @field_validator("name")
    @classmethod
    def check_name(cls, v):
        v = " ".join(v.split())
        if not v:
            raise ValueError("Please enter your name.")
        if len(v) > 80:
            raise ValueError("Please keep your name under 80 characters.")
        return v

    @field_validator("email")
    @classmethod
    def check_email(cls, v):
        v = v.strip()
        if not EMAIL.match(v) or len(v) > 200:
            raise ValueError("Please enter a valid email address.")
        return v

    @field_validator("issue")
    @classmethod
    def check_issue(cls, v):
        v = v.strip()
        if len(v) < 5:
            raise ValueError("Please describe the issue in a few words.")
        if len(v) > 2000:
            raise ValueError("Please keep the issue under 2000 characters.")
        return v


class TicketMessageRequest(BaseModel):
    """A message from the customer or an agent while a ticket is open."""
    message: str
    agent: Optional[str] = None

    @field_validator("message")
    @classmethod
    def check_message(cls, v):
        return ChatRequest.check_message(v)


class AgentRequest(BaseModel):
    agent: str

    @field_validator("agent")
    @classmethod
    def check_agent(cls, v):
        v = v.strip()
        if not v or len(v) > 40:
            raise ValueError("Enter your name (up to 40 characters).")
        return v


def parse(model, data):
    """Returns (object, None) or (None, error message)."""
    try:
        return model.model_validate(data or {}), None
    except ValidationError as e:
        err = e.errors()[0]
        msg = err.get("msg", "Invalid request.").removeprefix("Value error, ")
        if err.get("loc") == ("value",):
            msg = "value must be 'up', 'down' or null."
        elif err.get("loc") == ("message",) and err.get("type") != "value_error":
            msg = "Message is empty."
        return None, msg
