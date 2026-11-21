from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MAX_BALANCE
from app.errors import DomainError
from app.models import Account
from app.schemas import DepositCreate, DepositView
from app.services import posting
from app.services.accounts import get_account, lock_accounts


def deposit(session: Session, body: DepositCreate) -> DepositView:
    with session.begin():
        return make_deposit(session, body)


def make_deposit(session: Session, body: DepositCreate) -> DepositView:
    customer = get_account(session, body.account_id)
    funding_id = session.execute(
        select(Account.id).where(Account.currency == customer.currency, Account.is_internal)
    ).scalar_one()
    locked = lock_accounts(session, [funding_id, customer.id])
    customer, funding = locked[customer.id], locked[funding_id]
    if customer.balance_cents + body.amount_cents > MAX_BALANCE:
        raise DomainError("BALANCE_LIMIT", 422, "Customer balance limit exceeded")

    transaction = posting.post_entries(
        session, "DEPOSIT", customer.currency, body.amount_cents, funding, customer
    )
    return DepositView(
        transaction_id=transaction.id,
        type="DEPOSIT",
        account_id=customer.id,
        amount_cents=transaction.amount_cents,
        currency=transaction.currency,
        created_at=transaction.created_at,
    )
