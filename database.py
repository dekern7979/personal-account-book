from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "account_book.db"

EXPENSE_CATEGORIES = ["餐饮美食", "交通出行", "购物消费", "居家生活", "休闲娱乐", "医疗健康", "教育学习", "其他支出"]
INCOME_CATEGORIES = ["工资薪水", "奖金补贴", "理财收益", "兼职外快", "其他收入"]


def using_postgres() -> bool:
    return bool(os.getenv("DATABASE_URL", "").strip())


def _sql(sql: str) -> str:
    """Translate SQLite qmark placeholders for PostgreSQL drivers."""
    return sql.replace("?", "%s") if using_postgres() else sql


class Connection:
    """A tiny common interface for local SQLite and Supabase PostgreSQL."""

    def __init__(self):
        self.postgres = using_postgres()
        if self.postgres:
            import psycopg2

            self.raw = psycopg2.connect(os.environ["DATABASE_URL"])
        else:
            DATA_DIR.mkdir(exist_ok=True)
            self.raw = sqlite3.connect(DB_PATH)
            self.raw.row_factory = sqlite3.Row
            self.raw.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql: str, params: tuple | list = ()):
        if self.postgres:
            from psycopg2.extras import RealDictCursor

            cursor = self.raw.cursor(cursor_factory=RealDictCursor)
            cursor.execute(_sql(sql), params)
            return cursor
        return self.raw.execute(sql, params)

    def executemany(self, sql: str, rows: list[tuple]):
        if self.postgres:
            from psycopg2.extras import RealDictCursor

            cursor = self.raw.cursor(cursor_factory=RealDictCursor)
            cursor.executemany(_sql(sql), rows)
            return cursor
        return self.raw.executemany(sql, rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.raw.commit()
        else:
            self.raw.rollback()
        self.raw.close()


def connect() -> Connection:
    return Connection()


def init_db() -> None:
    account_id = "BIGSERIAL PRIMARY KEY" if using_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"
    foreign_id = "BIGINT" if using_postgres() else "INTEGER"
    with connect() as conn:
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS accounts (
                id {account_id}, name TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL DEFAULT 'cash',
                opening_balance_cents INTEGER NOT NULL DEFAULT 0,
                icon TEXT NOT NULL DEFAULT '💵', created_at TEXT NOT NULL
            )"""
        )
        transaction_id = "BIGSERIAL PRIMARY KEY" if using_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS transactions (
                id {transaction_id}, account_id {foreign_id} NOT NULL REFERENCES accounts(id),
                type INTEGER NOT NULL CHECK(type IN (1, 2)),
                amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                category TEXT NOT NULL, note TEXT DEFAULT '', transaction_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        transfer_id = "BIGSERIAL PRIMARY KEY" if using_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS transfers (
                id {transfer_id}, from_account_id {foreign_id} NOT NULL REFERENCES accounts(id),
                to_account_id {foreign_id} NOT NULL REFERENCES accounts(id),
                amount_cents INTEGER NOT NULL CHECK(amount_cents > 0), fee_cents INTEGER NOT NULL DEFAULT 0,
                note TEXT DEFAULT '', transfer_date TEXT NOT NULL, created_at TEXT NOT NULL
            )"""
        )
        count = conn.execute("SELECT COUNT(*) AS total FROM accounts").fetchone()["total"]
        if count == 0:
            now = datetime.now().isoformat(timespec="seconds")
            conn.executemany(
                "INSERT INTO accounts(name, type, icon, created_at) VALUES (?, ?, ?, ?)",
                [("现金", "cash", "💴", now), ("银行卡", "bank", "💳", now), ("微信", "wechat", "💚", now), ("支付宝", "alipay", "💙", now)],
            )


def accounts() -> list[dict]:
    with connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()]


def account_balances() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT a.*, COALESCE(SUM(CASE WHEN t.type=2 THEN t.amount_cents WHEN t.type=1 THEN -t.amount_cents ELSE 0 END), 0) AS movement
               FROM accounts a LEFT JOIN transactions t ON a.id=t.account_id GROUP BY a.id ORDER BY a.id"""
        ).fetchall()
        transfers = conn.execute("SELECT from_account_id, to_account_id, amount_cents, fee_cents FROM transfers").fetchall()
    result = []
    for row in rows:
        balance = row["opening_balance_cents"] + row["movement"]
        for transfer in transfers:
            if transfer["from_account_id"] == row["id"]:
                balance -= transfer["amount_cents"] + transfer["fee_cents"]
            if transfer["to_account_id"] == row["id"]:
                balance += transfer["amount_cents"]
        result.append({**dict(row), "balance_cents": balance})
    return result


def add_account(name: str, kind: str, opening_balance_cents: int, icon: str) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO accounts(name, type, opening_balance_cents, icon, created_at) VALUES (?, ?, ?, ?, ?)", (name, kind, opening_balance_cents, icon, datetime.now().isoformat(timespec="seconds")))


def delete_account(account_id: int) -> None:
    with connect() as conn:
        has_transactions = conn.execute("SELECT COUNT(*) AS total FROM transactions WHERE account_id=?", (account_id,)).fetchone()["total"]
        has_transfers = conn.execute("SELECT COUNT(*) AS total FROM transfers WHERE from_account_id=? OR to_account_id=?", (account_id, account_id)).fetchone()["total"]
        if has_transactions or has_transfers:
            raise ValueError("该账户已有记录，不能删除；请保留账户以保证历史数据完整。")
        conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))


def add_transaction(account_id: int, tx_type: int, amount_cents: int, category: str, note: str, tx_date: date) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO transactions(account_id,type,amount_cents,category,note,transaction_date,created_at) VALUES (?,?,?,?,?,?,?)", (account_id, tx_type, amount_cents, category, note, tx_date.isoformat(), datetime.now().isoformat(timespec="seconds")))


def delete_transaction(tx_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM transactions WHERE id=?", (tx_id,))


def add_transfer(from_id: int, to_id: int, amount_cents: int, fee_cents: int, note: str, tx_date: date) -> None:
    if from_id == to_id:
        raise ValueError("转出和转入账户不能相同")
    with connect() as conn:
        conn.execute("INSERT INTO transfers(from_account_id,to_account_id,amount_cents,fee_cents,note,transfer_date,created_at) VALUES (?,?,?,?,?,?,?)", (from_id, to_id, amount_cents, fee_cents, note, tx_date.isoformat(), datetime.now().isoformat(timespec="seconds")))


def query_transactions(start: str | None = None, end: str | None = None, account_id: int | None = None, category: str | None = None):
    sql = "SELECT t.*, a.name account_name FROM transactions t JOIN accounts a ON a.id=t.account_id WHERE 1=1"
    params: list = []
    if start:
        sql += " AND transaction_date >= ?"; params.append(start)
    if end:
        sql += " AND transaction_date <= ?"; params.append(end)
    if account_id:
        sql += " AND account_id = ?"; params.append(account_id)
    if category:
        sql += " AND category = ?"; params.append(category)
    sql += " ORDER BY transaction_date DESC, id DESC"
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def add_imported_transactions(rows: list[tuple]) -> int:
    sql = """INSERT INTO transactions(account_id,type,amount_cents,category,note,transaction_date,created_at)
             SELECT ?,?,?,?,?,?,? WHERE NOT EXISTS
             (SELECT 1 FROM transactions WHERE account_id=? AND type=? AND amount_cents=? AND note=? AND transaction_date=?)"""
    inserted = 0
    with connect() as conn:
        for row in rows:
            result = conn.execute(sql, row)
            inserted += max(result.rowcount, 0)
    return inserted
