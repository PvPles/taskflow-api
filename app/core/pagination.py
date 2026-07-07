"""Keyset pagination for task lists.

The cursor encodes the (created_at, id) of the previous page's last row.
Keyset paging avoids OFFSET's drift under concurrent writes and its scan
cost, and is served directly by the (project_id, created_at, id) index.
"""

import base64
import binascii
import json
import uuid
from datetime import datetime

from app.core.errors import APIError


def encode_cursor(created_at: datetime, item_id: uuid.UUID) -> str:
    payload = json.dumps({"t": created_at.isoformat(), "id": item_id.hex})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(payload["t"]), uuid.UUID(payload["id"])
    except (binascii.Error, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise APIError(400, "invalid_cursor", "The pagination cursor is not valid") from exc
