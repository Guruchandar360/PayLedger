from sqlalchemy.orm import Session

from app.config import MAX_BALANCE
from app.errors import DomainError
from app.schemas import TransferCreate, TransferView
from app.services import idempotency, posting
from app.services.accounts import lock_accounts


def transfer(session: Session, key: str, body: TransferCreate) -> idempotency.PaymentResult:
    if body.sender_id == body.receiver_id:
        raise DomainError("SELF_TRANSFER", 422, "Sender and receiver must be different")
    return idempotency.run(session, key, "transfer", body, lambda: make_transfer(session, body))


def make_transfer(session: Session, body: TransferCreate) -> TransferView:
    locked = lock_accounts(session, [body.sender_id, body.receiver_id])
    sender, receiver = locked[body.sender_id], locked[body.receiver_id]
    if sender.is_internal or receiver.is_internal:
        raise DomainError("ACCOUNT_NOT_FOUND", 404, "Account not found")
    if sender.currency != receiver.currency:
        raise DomainError("CURRENCY_MISMATCH", 422, "Accounts must have the same currency")
    if sender.balance_cents < body.amount_cents:
        raise DomainError("INSUFFICIENT_FUNDS", 422, "Sender has insufficient funds")
    if receiver.balance_cents + body.amount_cents > MAX_BALANCE:
        raise DomainError("BALANCE_LIMIT", 422, "Customer balance limit exceeded")

    transaction = posting.post_entries(
        session, "TRANSFER", sender.currency, body.amount_cents, sender, receiver
    )
    return TransferView(
        transaction_id=transaction.id,
        type="TRANSFER",
        sender_id=sender.id,
        receiver_id=receiver.id,
        amount_cents=transaction.amount_cents,
        currency=transaction.currency,
        created_at=transaction.created_at,
    )
