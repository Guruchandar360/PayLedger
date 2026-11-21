from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update

from app.config import MAX_AMOUNT, MAX_BALANCE
from app.models import Account, IdempotencyKey, Transaction
from app.services.accounts import lock_accounts
from app.services.posting import post_entries
from helpers import account, assert_ledger_consistent, balance, deposit, transfer, transfer_body


def test_accounts_persist_and_internal_accounts_are_hidden(app, client):
    account_id = account(client)
    assert balance(client, account_id) == 0
    assert client.post("/accounts", json={"owner": "Student", "currency": "JPY"}).status_code == 422
    assert client.post("/accounts", json={"owner": "", "currency": "INR"}).status_code == 422

    with app.state.sessions() as session:
        funding = session.scalars(select(Account).where(Account.is_internal)).all()
        assert {row.currency for row in funding} == {"INR", "USD", "GBP"}
        assert len(funding) == 3
        internal_id = str(funding[0].id)

    for path in (f"/accounts/{internal_id}", f"/accounts/{internal_id}/transactions"):
        assert client.get(path).status_code == 404
    assert deposit(client, internal_id, 100).status_code == 404
    assert transfer(client, account_id, internal_id, 100).status_code == 404
    assert transfer(client, internal_id, account_id, 100).status_code == 404


@pytest.mark.parametrize("amount", [0, -1, 10.5, "100", True, MAX_AMOUNT + 1])
def test_invalid_amounts_are_rejected_before_claim(app, client, amount):
    sender, receiver = str(uuid4()), str(uuid4())
    key = "invalid-amount"
    assert deposit(client, sender, amount, key).status_code == 422
    assert transfer(client, sender, receiver, amount, key).status_code == 422
    with app.state.sessions() as session:
        assert session.get(IdempotencyKey, key) is None


def test_header_and_self_transfer_are_validated_before_claim(app, client):
    sender, receiver = str(uuid4()), str(uuid4())
    for path, body in (
        ("/deposits", {"account_id": sender, "amount_cents": 100}),
        ("/transfers", transfer_body(sender, receiver, 100)),
    ):
        assert client.post(path, json=body).status_code == 422
        assert client.post(path, json=body, headers={"Idempotency-Key": "short"}).status_code == 422
        assert client.post(path, json=body, headers={"Idempotency-Key": "x" * 129}).status_code == 422

    key = "self-transfer"
    response = transfer(client, sender, sender, 100, key)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SELF_TRANSFER"
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(IdempotencyKey)) == 0


def test_unknown_accounts_and_currency_mismatch(client):
    sender = account(client)
    missing_id, receiver = str(uuid4()), account(client, currency="USD")
    for response in (
        client.get(f"/accounts/{missing_id}"),
        client.get(f"/accounts/{missing_id}/transactions"),
        deposit(client, missing_id, 100),
        transfer(client, sender, missing_id, 100),
    ):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"

    response = transfer(client, sender, receiver, 100)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CURRENCY_MISMATCH"


def test_rejected_payment_replays_even_after_adding_funds(client):
    sender, receiver = account(client), account(client)
    key = "rejected-payment"
    first = transfer(client, sender, receiver, 1_000, key)
    assert first.status_code == 422
    assert first.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
    assert deposit(client, sender, 1_000).status_code == 201

    replay = transfer(client, sender, receiver, 1_000, key)
    assert replay.status_code == 422 and replay.content == first.content
    assert replay.headers["Idempotent-Replay"] == "true"
    assert transfer(client, sender, receiver, 1_000).status_code == 201


def test_deposit_replay_and_cross_endpoint_key_conflict(app, client):
    sender, receiver = account(client), account(client)
    key = "global-key-01"
    first = deposit(client, sender, MAX_AMOUNT, key)
    assert first.status_code == 201
    replay = client.post(
        "/deposits",
        content='{"amount_cents":1000000000000, "account_id":"' + sender.upper() + '"}',
        headers={"Content-Type": "application/json", "Idempotency-Key": key},
    )
    assert replay.status_code == 201 and replay.content == first.content
    assert replay.headers["Idempotent-Replay"] == "true"
    assert deposit(client, sender, MAX_AMOUNT - 1, key).status_code == 409
    assert transfer(client, sender, receiver, 1, key).status_code == 409
    assert balance(client, sender) == MAX_AMOUNT
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Transaction)) == 1
        assert_ledger_consistent(session)


def test_customer_balance_limit_applies_to_both_credit_paths(app, client):
    sender, receiver = account(client), account(client)
    assert deposit(client, sender, 1).status_code == 201

    # Seed the exact boundary with a balanced posting, skipping 1,000 API calls.
    receiver_id = UUID(receiver)
    with app.state.sessions.begin() as session:
        funding_id = session.scalar(select(Account.id).where(Account.is_internal, Account.currency == "INR"))
        rows = lock_accounts(session, [receiver_id, funding_id])
        post_entries(session, "DEPOSIT", "INR", MAX_BALANCE, rows[funding_id], rows[receiver_id])

    for response in (deposit(client, receiver, 1), transfer(client, sender, receiver, 1)):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "BALANCE_LIMIT"
    assert balance(client, receiver) == MAX_BALANCE
    assert balance(client, sender) == 1
    with app.state.sessions() as session:
        assert_ledger_consistent(session)


def test_history_paginates_on_timestamp_and_transaction_id(app, client):
    sender, receiver = account(client), account(client)
    for _ in range(44):
        assert deposit(client, sender, 100).status_code == 201
    paid = transfer(client, sender, receiver, 100)
    assert paid.status_code == 201

    # Exercise the UUID tie-breaker even if all postings share a timestamp.
    with app.state.sessions.begin() as session:
        session.execute(update(Transaction).values(created_at=func.now()))
        expected = [str(row) for row in session.scalars(select(Transaction.id).order_by(Transaction.id.desc()))]

    path = f"/accounts/{sender}/transactions"
    first = client.get(path).json()
    second = client.get(path, params={"cursor": first["next_cursor"]}).json()
    third = client.get(path, params={"cursor": second["next_cursor"]}).json()
    pages = [first, second, third]
    assert [len(page["items"]) for page in pages] == [20, 20, 5]
    assert third["next_cursor"] is None
    items = [item for page in pages for item in page["items"]]
    assert [item["transaction_id"] for item in items] == expected
    outgoing = next(item for item in items if item["type"] == "TRANSFER")
    incoming = client.get(f"/accounts/{receiver}/transactions").json()["items"][0]
    assert outgoing["direction"] == "DEBIT"
    assert incoming["direction"] == "CREDIT"
    assert incoming["transaction_id"] == outgoing["transaction_id"]
    assert client.get(path, params={"cursor": "not a cursor"}).status_code == 422
    assert client.get(path, params={"limit": 101}).status_code == 422
    assert client.get(path, params={"limit": 0}).status_code == 422
