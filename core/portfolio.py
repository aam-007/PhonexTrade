"""
Portfolio core engine.
Handles trade execution, holdings computation, cash management,
and portfolio value history reconstruction.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional
from data import database as db
from data.fetch import fetch_current_price, fetch_historical_prices


class Portfolio:
    """
    Represents a single portfolio.
    Provides methods for trade execution and performance computation.
    """

    def __init__(self, portfolio_id: int):
        data = db.get_portfolio_by_id(portfolio_id)
        if data is None:
            raise ValueError(f"Portfolio with id {portfolio_id} not found.")

        self.id: int = data["id"]
        self.name: str = data["name"]
        self.initial_capital: float = data["initial_capital"]
        self.benchmark: str = data["benchmark"]
        self.created_at: str = data["created_at"]
        self._trades: list[dict] = db.get_trades_for_portfolio(portfolio_id)

    def refresh(self) -> None:
        """Reload trades from the database."""
        self._trades = db.get_trades_for_portfolio(self.id)

    # --- Cash and Holdings ---

    @property
    def cash(self) -> float:
        """Current available cash balance."""
        spent = sum(
            t["price"] * t["quantity"]
            for t in self._trades
            if t["type"] == "BUY"
        )
        received = sum(
            t["price"] * t["quantity"]
            for t in self._trades
            if t["type"] == "SELL"
        )
        return self.initial_capital - spent + received

    def get_holdings(self) -> dict[str, dict]:
        """
        Compute current holdings.
        Returns {symbol: {quantity, avg_price, invested_value}}
        """
        holdings: dict[str, dict] = {}

        for trade in self._trades:
            sym = trade["symbol"]
            qty = trade["quantity"]
            price = trade["price"]

            if sym not in holdings:
                holdings[sym] = {"quantity": 0.0, "total_cost": 0.0}

            if trade["type"] == "BUY":
                holdings[sym]["quantity"] += qty
                holdings[sym]["total_cost"] += qty * price
            elif trade["type"] == "SELL":
                if holdings[sym]["quantity"] > 0:
                    avg = holdings[sym]["total_cost"] / holdings[sym]["quantity"]
                    holdings[sym]["quantity"] -= qty
                    holdings[sym]["total_cost"] -= qty * avg

        # Remove zero-quantity positions
        holdings = {
            sym: h for sym, h in holdings.items() if h["quantity"] > 1e-9
        }

        for sym, h in holdings.items():
            h["avg_price"] = h["total_cost"] / h["quantity"] if h["quantity"] > 0 else 0.0
            h["invested_value"] = h["total_cost"]

        return holdings

    def get_holdings_with_market_data(self) -> list[dict]:
        """
        Return holdings enriched with current market price, P&L, and allocation.
        """
        holdings = self.get_holdings()
        rows = []
        total_current_value = 0.0

        enriched = {}
        for sym, h in holdings.items():
            current_price = fetch_current_price(sym)
            if current_price is None:
                current_price = h["avg_price"]
            current_value = current_price * h["quantity"]
            total_current_value += current_value
            enriched[sym] = {**h, "current_price": current_price, "current_value": current_value}

        for sym, h in enriched.items():
            pnl_abs = h["current_value"] - h["invested_value"]
            pnl_pct = (pnl_abs / h["invested_value"] * 100) if h["invested_value"] > 0 else 0.0
            allocation = (h["current_value"] / (total_current_value + self.cash) * 100) if (total_current_value + self.cash) > 0 else 0.0
            rows.append({
                "symbol": sym,
                "quantity": h["quantity"],
                "avg_price": h["avg_price"],
                "current_price": h["current_price"],
                "invested_value": h["invested_value"],
                "current_value": h["current_value"],
                "pnl_abs": pnl_abs,
                "pnl_pct": pnl_pct,
                "allocation_pct": allocation,
            })

        return rows

    def get_quantity_owned(self, symbol: str) -> float:
        """Return current quantity held for a symbol."""
        holdings = self.get_holdings()
        return holdings.get(symbol, {}).get("quantity", 0.0)

    def total_value(self) -> float:
        """Total portfolio value: cash + market value of holdings."""
        holdings = self.get_holdings()
        market_value = 0.0
        for sym, h in holdings.items():
            price = fetch_current_price(sym) or h["avg_price"]
            market_value += price * h["quantity"]
        return self.cash + market_value

    # --- Trade Execution ---

    def execute_buy(self, symbol: str, quantity: float, price: float) -> str:
        """
        Execute a buy trade.
        Returns 'ok' or an error message.
        """
        cost = quantity * price
        if cost > self.cash + 0.01:
            return f"Insufficient cash. Available: {self.cash:.2f}, Required: {cost:.2f}"
        db.insert_trade(self.id, symbol, quantity, price, "BUY")
        self.refresh()
        return "ok"

    def execute_sell(self, symbol: str, quantity: float, price: float) -> str:
        """
        Execute a sell trade.
        Returns 'ok' or an error message.
        """
        owned = self.get_quantity_owned(symbol)
        if quantity > owned + 1e-9:
            return f"Insufficient holdings. Owned: {owned:.4f}, Requested: {quantity:.4f}"
        db.insert_trade(self.id, symbol, quantity, price, "SELL")
        self.refresh()
        return "ok"

    # --- Portfolio Value History ---

    def get_value_series(self) -> pd.Series:
        """
        Reconstruct the portfolio value over time using historical prices.
        Returns a Series indexed by date.
        """
        if not self._trades:
            today = datetime.now().strftime("%Y-%m-%d")
            return pd.Series({today: self.initial_capital})

        start_date = self._trades[0]["timestamp"][:10]
        end_date = datetime.now().strftime("%Y-%m-%d")

        symbols = list({t["symbol"] for t in self._trades})
        price_data: dict[str, pd.Series] = {}
        for sym in symbols:
            series = fetch_historical_prices(sym, start=start_date, end=end_date)
            if not series.empty:
                price_data[sym] = series

        if not price_data:
            today = datetime.now().strftime("%Y-%m-%d")
            return pd.Series({today: self.initial_capital})

        all_dates = sorted(
            set().union(*[s.index for s in price_data.values()])
        )

        values = []
        for date in all_dates:
            cash = self.initial_capital
            holdings: dict[str, float] = {}

            for trade in self._trades:
                trade_date = pd.Timestamp(trade["timestamp"][:10])
                if trade_date > date:
                    break
                sym = trade["symbol"]
                qty = trade["quantity"]
                price = trade["price"]

                if trade["type"] == "BUY":
                    cash -= qty * price
                    holdings[sym] = holdings.get(sym, 0.0) + qty
                elif trade["type"] == "SELL":
                    cash += qty * price
                    holdings[sym] = holdings.get(sym, 0.0) - qty

            market_value = 0.0
            for sym, qty in holdings.items():
                if qty > 1e-9 and sym in price_data:
                    series = price_data[sym]
                    available = series[series.index <= date]
                    if not available.empty:
                        market_value += qty * float(available.iloc[-1])
                    else:
                        market_value += qty * 0.0

            values.append(cash + market_value)

        return pd.Series(values, index=all_dates)

    def get_all_trades(self) -> list[dict]:
        """Return all trades for this portfolio."""
        return self._trades