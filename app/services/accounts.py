from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import Account
from app.schemas import AccountCreate, AccountView


def create_account(session: Session, data: AccountCreate) -> AccountView:
    with session.begin():
        account = Account(owner=data.owner, currency=data.currency)
        session.add(account)
        session.flush()
        return AccountView.model_validate(account)


def get_account(session: Session, account_id: UUID) -> Account:
    account = session.get(Account, account_id)
    if account is None or account.is_internal:
        raise DomainError("ACCOUNT_NOT_FOUND", 404, "Account not found")
    return account


def lock_accounts(session: Session, ids: list[UUID]) -> dict[UUID, Account]:
    locked = {}
    for account_id in sorted(ids):
        account = session.scalar(
            select(Account)
            .where(Account.id == account_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if account is None:
            raise DomainError("ACCOUNT_NOT_FOUND", 404, "Account not found")
        locked[account_id] = account
    return locked
