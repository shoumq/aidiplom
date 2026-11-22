import argparse
import sqlite3
import time

from backend import yookassa
from backend.app import ALLOW_MOCK_PAY, _auth_connection, _credit_balance, _normalise_email


def main():
    parser = argparse.ArgumentParser(description="Add account credit using a unique grant reference.")
    parser.add_argument("email")
    parser.add_argument("amount_rub", type=int)
    parser.add_argument("reference", help="Unique reference for this grant. Use it again to retry safely.")
    args = parser.parse_args()
    if not 1 <= args.amount_rub <= 1_000_000:
        parser.error("amount_rub must be between 1 and 1000000")
    if not 1 <= len(args.reference) <= 80:
        parser.error("reference must contain 1 to 80 characters")

    email = _normalise_email(args.email)
    reason = "test-admin-grant" if ALLOW_MOCK_PAY and not yookassa.configured() else "admin-grant"
    grant_id = f"{reason}:{args.reference}"
    with _auth_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        user = connection.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if user is None:
            parser.error("account not found")
        try:
            connection.execute(
                "INSERT INTO account_credits(id,user_id,amount_rub,reason,created_at) VALUES(?,?,?,?,?)",
                (grant_id, user["id"], args.amount_rub, reason, int(time.time())),
            )
        except sqlite3.IntegrityError:
            previous = connection.execute(
                "SELECT user_id,amount_rub FROM account_credits WHERE id=?", (grant_id,),
            ).fetchone()
            if previous is None or tuple(previous) != (user["id"], args.amount_rub):
                parser.error("grant reference is already in use")
        print(f"Account credit: {_credit_balance(connection, user['id'])} RUB")


if __name__ == "__main__":
    main()
