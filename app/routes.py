from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import AccountCreate, AccountView
from app.services import accounts

router = APIRouter()
DatabaseSession = Annotated[Session, Depends(get_session)]


@router.post("/accounts", status_code=201)
def create_account(body: AccountCreate, session: DatabaseSession) -> AccountView:
    return accounts.create_account(session, body)


@router.get("/accounts/{id}")
def get_account(id: UUID, session: DatabaseSession) -> AccountView:
    return AccountView.model_validate(accounts.get_account(session, id))
