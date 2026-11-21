from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt
from uuid import UUID

from app.config import CURRENCIES, MAX_AMOUNT

Currency = Annotated[str, Field(pattern="^(" + "|".join(CURRENCIES) + ")$")]
Amount = Annotated[StrictInt, Field(gt=0, le=MAX_AMOUNT)]


class AccountCreate(BaseModel):
    owner: Annotated[str, Field(min_length=1, max_length=100)]
    currency: Currency


class AccountView(AccountCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    balance_cents: int


class DepositCreate(BaseModel):
    account_id: UUID
    amount_cents: Amount


class DepositView(BaseModel):
    transaction_id: UUID
    type: Literal["DEPOSIT"]
    account_id: UUID
    amount_cents: int
    currency: Currency
    created_at: datetime
