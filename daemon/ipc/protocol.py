"""Framed newline-delimited JSON IPC protocol."""

import json
from typing import Any, Dict, Optional, Tuple


def encode_message(payload: Dict[str, Any]) -> bytes:
    """Encode a dictionary to UTF-8 newline-terminated JSON bytes."""
    return (json.dumps(payload, separators=(',', ':')) + "\n").encode("utf-8")


def decode_message(line: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Decode a single line of JSON string into a dictionary."""
    line = line.strip()
    if not line:
        return False, None, "Empty payload"
    try:
        data = json.loads(line)
        if not isinstance(data, dict):
            return False, None, "Payload must be a JSON object"
        return True, data, None
    except json.JSONDecodeError as e:
        return False, None, f"Malformed JSON: {e}"


def make_response(success: bool, data: Any = None, error: Optional[str] = None) -> bytes:
    """Construct a standard response message."""
    payload: Dict[str, Any] = {
        "success": success,
        "data": data if success else None,
        "error": error if not success else None,
    }
    return encode_message(payload)


def make_event(event_name: str, data: Any) -> bytes:
    """Construct an asynchronous event broadcast message."""
    payload = {
        "type": "event",
        "event": event_name,
        "data": data,
    }
    return encode_message(payload)
