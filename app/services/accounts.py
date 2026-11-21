from uuid import UUID

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
