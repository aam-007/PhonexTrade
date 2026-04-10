"""
Export utilities for trades and holdings.
Supports CSV and Excel output.
"""

import os
import pandas as pd
from typing import Optional


def export_trades_to_csv(trades: list[dict], filepath: str) -> None:
    """Export trade records to a CSV file."""
    df = pd.DataFrame(trades)
    if df.empty:
        df = pd.DataFrame(columns=["id", "portfolio_id", "symbol", "quantity", "price", "type", "timestamp"])
    df.to_csv(filepath, index=False)


def export_holdings_to_csv(holdings: list[dict], filepath: str) -> None:
    """Export holdings to a CSV file."""
    df = pd.DataFrame(holdings)
    if df.empty:
        df = pd.DataFrame(columns=["symbol", "quantity", "avg_price", "current_price",
                                   "invested_value", "current_value", "pnl_abs", "pnl_pct", "allocation_pct"])
    df.to_csv(filepath, index=False)


def export_to_excel(trades: list[dict], holdings: list[dict], filepath: str) -> None:
    """Export both trades and holdings to separate sheets in an Excel file."""
    trades_df = pd.DataFrame(trades)
    holdings_df = pd.DataFrame(holdings)

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        if not trades_df.empty:
            trades_df.to_excel(writer, sheet_name="Trades", index=False)
        else:
            pd.DataFrame(columns=["id", "portfolio_id", "symbol", "quantity",
                                   "price", "type", "timestamp"]).to_excel(
                writer, sheet_name="Trades", index=False
            )

        if not holdings_df.empty:
            holdings_df.to_excel(writer, sheet_name="Holdings", index=False)
        else:
            pd.DataFrame(columns=["symbol", "quantity", "avg_price", "current_price",
                                   "invested_value", "current_value",
                                   "pnl_abs", "pnl_pct", "allocation_pct"]).to_excel(
                writer, sheet_name="Holdings", index=False
            )


def suggest_filepath(base_name: str, extension: str, directory: Optional[str] = None) -> str:
    """Return a suggested filepath for export."""
    if directory is None:
        directory = os.path.expanduser("~")
    filename = f"{base_name}.{extension}"
    return os.path.join(directory, filename)