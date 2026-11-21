import threading
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from uuid import uuid4

import httpx
from sqlalchemy import select

from app.models import Account, LedgerEntry, Transaction


def account(client, owner="Student", currency="INR"):
    response = client.post("/accounts", json={"owner": owner, "currency": currency})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def deposit(client, account_id, amount, key=None):
    return client.post(
        "/deposits",
        json={"account_id": account_id, "amount_cents": amount},
        headers={"Idempotency-Key": key or uuid4().hex},
    )


def balance(client, account_id):
    response = client.get(f"/accounts/{account_id}")
    assert response.status_code == 200, response.text
    return response.json()["balance_cents"]


def transfer_body(sender, receiver, amount):
    return {"sender_id": sender, "receiver_id": receiver, "amount_cents": amount}


def transfer(client, sender, receiver, amount, key=None):
    return client.post(
        "/transfers",
        json=transfer_body(sender, receiver, amount),
        headers={"Idempotency-Key": key or uuid4().hex},
    )


def assert_ledger_consistent(session):
    accounts = {row.id: row for row in session.scalars(select(Account))}
    transactions = list(session.scalars(select(Transaction)))
    by_transaction = defaultdict(list)
    by_account = defaultdict(int)
    by_currency = defaultdict(int)
    for entry in session.scalars(select(LedgerEntry)):
        by_transaction[entry.txn_id].append(entry)
        signed = entry.amount_cents if entry.direction == "CREDIT" else -entry.amount_cents
        by_account[entry.account_id] += signed
        by_currency[accounts[entry.account_id].currency] += signed

    for transaction in transactions:
        entries = by_transaction[transaction.id]
        assert len(entries) == 2
        assert {entry.direction for entry in entries} == {"DEBIT", "CREDIT"}
        assert all(entry.amount_cents == transaction.amount_cents for entry in entries)
        assert all(accounts[entry.account_id].currency == transaction.currency for entry in entries)
        assert transaction.status == "POSTED"

    assert all(total == 0 for total in by_currency.values())
    for account in accounts.values():
        assert account.balance_cents == by_account[account.id]
        assert account.is_internal or account.balance_cents >= 0

def concurrently(url, requests):
    barrier = threading.Barrier(len(requests), timeout=15)

    def send(request):
        path, body, key = request
        with httpx.Client(base_url=url, timeout=25, trust_env=False) as client:
            barrier.wait()
            return client.post(path, json=body, headers={"Idempotency-Key": key})

    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        return list(executor.map(send, requests, timeout=30))
