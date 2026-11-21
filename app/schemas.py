from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID

from app.config import CURRENCIES

Currency = Annotated[str, Field(pattern="^(" + "|".join(CURRENCIES) + ")$")]


class AccountCreate(BaseModel):
    owner: Annotated[str, Field(min_length=1, max_length=100)]
    currency: Currency


class AccountView(AccountCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    balance_cents: int
