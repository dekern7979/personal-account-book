from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "account_book.db"

EXPENSE_CATEGORIES = ["餐饮美食", "交通出行", "购物消费", "居家生活", "休闲娱乐", "医疗健康", "教育学习", "其他支出"]
INCOME_CATEGORIES = ["工资薪水", "奖金补贴", "理财收益", "兼职外快", "其他收入"]


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL DEFAULT 'cash',
                opening_balance_cents INTEGER NOT NULL DEFAULT 0,
                icon TEXT NOT NULL DEFAULT '💰',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                type INTEGER NOT NULL CHECK(type IN (1, 2)),
                amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                category TEXT NOT NULL,
                note TEXT DEFAULT '',
                transaction_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_account_id INTEGER NOT NULL REFERENCES accounts(id),
                to_account_id INTEGER NOT NULL REFERENCES accounts(id),
                amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                fee_cents INTEGER NOT NULL DEFAULT 0,
                note TEXT DEFAULT '',
                transfer_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        if conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
            now = datetime.now().isoformat(timespec="seconds")
            conn.executemany(
                "INSERT INTO accounts(name, type, icon, created_at) VALUES (?, ?, ?, ?)",
                [("现金", "cash", "💵", now), ("银行卡", "bank", "💳", now), ("微信", "wechat", "💬", now), ("支付宝", "alipay", "🅰️", now)],
            )


def accounts() -> list[sqlite3.Row]:
    with connect() as conn:
        # Streamlit widgets serialize their options between reruns. sqlite3.Row
        # is not pickleable, so expose plain dictionaries to the UI layer.
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
        for tr in transfers:
            if tr["from_account_id"] == row["id"]:
                balance -= tr["amount_cents"] + tr["fee_cents"]
            if tr["to_account_id"] == row["id"]:
                balance += tr["amount_cents"]
        result.append({**dict(row), "balance_cents": balance})
    return result


def add_account(name: str, kind: str, opening_balance_cents: int, icon: str) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO accounts(name, type, opening_balance_cents, icon, created_at) VALUES (?, ?, ?, ?, ?)", (name, kind, opening_balance_cents, icon, datetime.now().isoformat(timespec="seconds")))


def delete_account(account_id: int) -> None:
    with connect() as conn:
        if conn.execute("SELECT COUNT(*) FROM transactions WHERE account_id=?", (account_id,)).fetchone()[0] or conn.execute("SELECT COUNT(*) FROM transfers WHERE from_account_id=? OR to_account_id=?", (account_id, account_id)).fetchone()[0]:
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
    with connect() as conn:
        before = conn.total_changes
        conn.executemany("INSERT INTO transactions(account_id,type,amount_cents,category,note,transaction_date,created_at) SELECT ?,?,?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM transactions WHERE account_id=? AND type=? AND amount_cents=? AND note=? AND transaction_date=?)", rows)
        return conn.total_changes - before
