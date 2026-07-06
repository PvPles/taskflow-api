"""Cursor-based pagination for task lists.

A cursor is the (created_at, id) of the last item on the previous page,
base64-encoded. Unlike offset pagination it stays correct when rows are
inserted or deleted between page fetches, and the DB can seek straight to
the position via the (project_id, created_at, id) index instead of counting
skipped rows.
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
