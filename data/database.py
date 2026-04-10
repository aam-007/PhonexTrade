"""
Database layer for PhonexTrade.
Manages SQLite operations for portfolios, trades, and price cache.
"""

import sqlite3
import os
from typing import Optional
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "phonextrade.db")


def get_connection() -> sqlite3.Connection:
    """Return a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    """Create all tables if they do not exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            initial_capital REAL NOT NULL,
            benchmark TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
        );

        CREATE TABLE IF NOT EXISTS price_cache (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            price REAL NOT NULL,
            PRIMARY KEY (symbol, date)
        );
    """)

    conn.commit()
    conn.close()


# --- Portfolio CRUD ---

def create_portfolio(name: str, initial_capital: float, benchmark: str) -> int:
    """Insert a new portfolio and return its id."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO portfolios (name, initial_capital, benchmark, created_at) VALUES (?, ?, ?, ?)",
        (name, initial_capital, benchmark, now),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def get_all_portfolios() -> list[dict]:
    """Return all portfolios as a list of dicts."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM portfolios ORDER BY created_at DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_portfolio_by_id(portfolio_id: int) -> Optional[dict]:
    """Return a single portfolio dict or None."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM portfolios WHERE id = ?", (portfolio_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_portfolio(portfolio_id: int) -> None:
    """Delete a portfolio and all its trades."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trades WHERE portfolio_id = ?", (portfolio_id,))
    cursor.execute("DELETE FROM portfolios WHERE id = ?", (portfolio_id,))
    conn.commit()
    conn.close()


# --- Trade CRUD ---

def insert_trade(portfolio_id: int, symbol: str, quantity: float, price: float, trade_type: str) -> int:
    """Insert a trade record and return its id."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO trades (portfolio_id, symbol, quantity, price, type, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (portfolio_id, symbol, quantity, price, trade_type, now),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def get_trades_for_portfolio(portfolio_id: int) -> list[dict]:
    """Return all trades for a portfolio ordered by timestamp."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM trades WHERE portfolio_id = ? ORDER BY timestamp ASC",
        (portfolio_id,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# --- Price Cache ---

def cache_prices(symbol: str, prices: dict[str, float]) -> None:
    """Store a mapping of date->price for a symbol."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executemany(
        "INSERT OR REPLACE INTO price_cache (symbol, date, price) VALUES (?, ?, ?)",
        [(symbol, date, price) for date, price in prices.items()],
    )
    conn.commit()
    conn.close()


def get_cached_prices(symbol: str) -> dict[str, float]:
    """Return cached prices as {date: price} dict."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT date, price FROM price_cache WHERE symbol = ? ORDER BY date ASC",
        (symbol,),
    )
    result = {row["date"]: row["price"] for row in cursor.fetchall()}
    conn.close()
    return result