import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import IdempotencyKey
from app.schemas import DepositView, TransferView


@dataclass(frozen=True)
class PaymentResult:
    status: int
    body: dict
    replay: bool = False


def canonical_json(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def run(
    session: Session,
    key: str,
    endpoint: str,
    body: BaseModel,
    work: Callable[[], DepositView | TransferView],
) -> PaymentResult:
    request_hash = hashlib.sha256(
        canonical_json({"endpoint": endpoint, "body": body.model_dump(mode="json")})
    ).hexdigest()

    with session.begin():
        claim = (
            insert(IdempotencyKey)
            .values(key=key, request_hash=request_hash)
            .on_conflict_do_nothing(index_elements=[IdempotencyKey.key])
            .returning(IdempotencyKey.key)
        )
        claimed = session.scalar(claim)
        stored = session.get(IdempotencyKey, key)
        if claimed is None:
            if stored.request_hash != request_hash:
                raise DomainError("IDEMPOTENCY_CONFLICT", 409, "Key was used for a different request")
            return PaymentResult(stored.status_code, stored.response_body, replay=True)

        try:
            payment = work()
        except DomainError as error:
            # Business rules reject before posting any ledger entries.
            result = PaymentResult(error.status, error.body)
        else:
            result = PaymentResult(201, payment.model_dump(mode="json"))
            stored.txn_id = payment.transaction_id

        stored.status_code = result.status
        stored.response_body = result.body
        return result
