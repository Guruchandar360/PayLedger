import argparse
import json
from uuid import uuid4

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PayLedger demo")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=10, trust_env=False) as client:
        sender, receiver = [
            client.post("/accounts", json={"owner": owner, "currency": "INR"}).raise_for_status().json()
            for owner in ("Demo student", "Demo university")
        ]
        deposit = client.post(
            "/deposits",
            json={"account_id": sender["id"], "amount_cents": 100_000},
            headers={"Idempotency-Key": uuid4().hex},
        ).raise_for_status()

        body = {"sender_id": sender["id"], "receiver_id": receiver["id"], "amount_cents": 80_000}
        headers = {"Idempotency-Key": uuid4().hex}
        transfer = client.post("/transfers", json=body, headers=headers).raise_for_status()
        replay = client.post("/transfers", json=body, headers=headers).raise_for_status()
        if replay.content != transfer.content or replay.headers.get("Idempotent-Replay") != "true":
            raise RuntimeError("Transfer replay did not return the original response")

        sender_id = sender["id"]
        receiver_id = receiver["id"]
        sender_balance = client.get(f"/accounts/{sender_id}").raise_for_status().json()["balance_cents"]
        receiver_balance = client.get(f"/accounts/{receiver_id}").raise_for_status().json()["balance_cents"]
        history = client.get(f"/accounts/{sender_id}/transactions").raise_for_status().json()["items"]
        if (sender_balance, receiver_balance) != (20_000, 80_000):
            raise RuntimeError("Unexpected balances after replay")
        if [item["type"] for item in history] != ["TRANSFER", "DEPOSIT"]:
            raise RuntimeError("Expected exactly one transfer and one deposit in the student's history")

        print(json.dumps({
            "deposit": deposit.json(),
            "transfer": transfer.json(),
            "replayed": True,
            "student_balance_cents": sender_balance,
            "university_balance_cents": receiver_balance,
            "student_history": history,
        }, indent=2))


if __name__ == "__main__":
    main()
