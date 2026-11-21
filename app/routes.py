from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import AccountCreate, AccountView, DepositCreate, DepositView, TransferCreate, TransferView
from app.services import accounts, deposits, idempotency, transfers

router = APIRouter()
DatabaseSession = Annotated[Session, Depends(get_session)]
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


@router.post("/accounts", status_code=201)
def create_account(body: AccountCreate, session: DatabaseSession) -> AccountView:
    return accounts.create_account(session, body)


@router.get("/accounts/{id}")
def get_account(id: UUID, session: DatabaseSession) -> AccountView:
    return AccountView.model_validate(accounts.get_account(session, id))


@router.post("/deposits", status_code=201, response_model=DepositView)
def deposit(body: DepositCreate, session: DatabaseSession, key: IdempotencyHeader) -> Response:
    return payment_response(deposits.deposit(session, key, body))


@router.post("/transfers", status_code=201, response_model=TransferView)
def transfer(body: TransferCreate, session: DatabaseSession, key: IdempotencyHeader) -> Response:
    return payment_response(transfers.transfer(session, key, body))


def payment_response(result: idempotency.PaymentResult) -> Response:
    headers = {"Idempotent-Replay": "true"} if result.replay else None
    return Response(
        content=idempotency.canonical_json(result.body),
        status_code=result.status,
        media_type="application/json",
        headers=headers,
    )
