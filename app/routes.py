from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import AccountCreate, AccountView, DepositCreate, DepositView
from app.services import accounts, deposits

router = APIRouter()
DatabaseSession = Annotated[Session, Depends(get_session)]
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


@router.post("/accounts", status_code=201)
def create_account(body: AccountCreate, session: DatabaseSession) -> AccountView:
    return accounts.create_account(session, body)


@router.get("/accounts/{id}")
def get_account(id: UUID, session: DatabaseSession) -> AccountView:
    return AccountView.model_validate(accounts.get_account(session, id))


@router.post("/deposits", status_code=201)
def deposit(body: DepositCreate, session: DatabaseSession, key: IdempotencyHeader) -> DepositView:
    return deposits.deposit(session, body)
