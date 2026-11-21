import base64
import binascii
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import LedgerEntry, Transaction
from app.schemas import HistoryItem, HistoryPage
from app.services.accounts import get_account


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        encoded = base64.b64decode(cursor, altchars=b"-_", validate=True)
        timestamp, transaction_id = encoded.decode("ascii").split("|")
        created_at = datetime.fromisoformat(timestamp)
        if created_at.tzinfo is None:
            raise ValueError("Cursor timestamp must include a time zone")
        return created_at, UUID(transaction_id)
    except (ValueError, binascii.Error) as error:
        raise DomainError("INVALID_CURSOR", 422, "Invalid history cursor") from error


def history(session: Session, account_id: UUID, limit: int, cursor: str | None) -> HistoryPage:
    get_account(session, account_id)
    query = (
        select(
            Transaction.id.label("transaction_id"),
            Transaction.type,
            Transaction.status,
            LedgerEntry.direction,
            LedgerEntry.amount_cents,
            Transaction.created_at,
        )
        .join(LedgerEntry, LedgerEntry.txn_id == Transaction.id)
        .where(LedgerEntry.account_id == account_id)
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        query = query.where(tuple_(Transaction.created_at, Transaction.id) < decode_cursor(cursor))

    rows = session.execute(query).mappings().all()
    items = [HistoryItem.model_validate(row) for row in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        value = f"{last.created_at.isoformat()}|{last.transaction_id}"
        next_cursor = base64.urlsafe_b64encode(value.encode("ascii")).decode("ascii")
    return HistoryPage(items=items, next_cursor=next_cursor)
