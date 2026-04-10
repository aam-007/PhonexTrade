"""
Quantitative metrics for portfolio analysis.
Implements CAGR, Volatility, Sharpe Ratio, Max Drawdown, and Beta.
"""

import numpy as np
import pandas as pd
from typing import Optional


def compute_daily_returns(series: pd.Series) -> pd.Series:
    """Compute percentage daily returns from a price/value series."""
    return series.pct_change().dropna()


def compute_cagr(series: pd.Series) -> float:
    """
    Compound Annual Growth Rate.
    Returns a decimal (0.12 = 12%).
    """
    if series.empty or len(series) < 2:
        return 0.0
    start_val = float(series.iloc[0])
    end_val = float(series.iloc[-1])
    if start_val <= 0:
        return 0.0

    start_date = series.index[0]
    end_date = series.index[-1]
    if hasattr(start_date, "to_pydatetime"):
        start_date = start_date.to_pydatetime()
    if hasattr(end_date, "to_pydatetime"):
        end_date = end_date.to_pydatetime()

    years = (end_date - start_date).days / 365.25
    if years <= 0:
        return 0.0

    return (end_val / start_val) ** (1.0 / years) - 1.0


def compute_volatility(series: pd.Series, annualized: bool = True) -> float:
    """
    Annualized volatility (standard deviation of returns).
    Returns a decimal (0.18 = 18%).
    """
    returns = compute_daily_returns(series)
    if returns.empty:
        return 0.0
    vol = float(returns.std())
    if annualized:
        vol *= np.sqrt(252)
    return vol


def compute_sharpe_ratio(series: pd.Series, risk_free_rate: float = 0.065) -> float:
    """
    Sharpe Ratio using daily returns, annualized.
    Assumes a default risk-free rate of 6.5% (approximate India 10Y).
    """
    returns = compute_daily_returns(series)
    if returns.empty or returns.std() == 0:
        return 0.0

    daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1
    excess = returns - daily_rf
    return float(excess.mean() / excess.std() * np.sqrt(252))


def compute_max_drawdown(series: pd.Series) -> float:
    """
    Maximum Drawdown.
    Returns a negative decimal (-0.25 = -25% drawdown).
    """
    if series.empty:
        return 0.0
    rolling_max = series.cummax()
    drawdown = (series - rolling_max) / rolling_max
    return float(drawdown.min())


def compute_drawdown_series(series: pd.Series) -> pd.Series:
    """
    Return the full drawdown series (for charting).
    """
    if series.empty:
        return pd.Series(dtype=float)
    rolling_max = series.cummax()
    return (series - rolling_max) / rolling_max


def compute_beta(portfolio_series: pd.Series, benchmark_series: pd.Series) -> float:
    """
    Beta of portfolio relative to benchmark.
    Measures sensitivity to market movements.
    """
    port_returns = compute_daily_returns(portfolio_series)
    bench_returns = compute_daily_returns(benchmark_series)

    aligned = pd.concat([port_returns, bench_returns], axis=1).dropna()
    if aligned.empty or len(aligned) < 5:
        return 1.0

    aligned.columns = ["portfolio", "benchmark"]
    cov = aligned["portfolio"].cov(aligned["benchmark"])
    var = aligned["benchmark"].var()

    if var == 0:
        return 1.0
    return float(cov / var)


def compute_monthly_returns(series: pd.Series) -> pd.DataFrame:
    """
    Return a pivot table of monthly returns (year x month).
    Values are percentage returns (5.2 = 5.2%).
    """
    if series.empty:
        return pd.DataFrame()

    monthly = series.resample("ME").last()
    returns = monthly.pct_change().dropna() * 100

    df = pd.DataFrame({
        "year": returns.index.year,
        "month": returns.index.month,
        "return": returns.values,
    })

    if df.empty:
        return pd.DataFrame()

    pivot = df.pivot_table(index="year", columns="month", values="return")
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    pivot.columns = [month_names[m - 1] for m in pivot.columns]
    return pivot


def compute_all_metrics(
    portfolio_series: pd.Series,
    benchmark_series: Optional[pd.Series] = None,
) -> dict:
    """
    Compute all metrics and return as a dict.
    """
    metrics = {
        "cagr": compute_cagr(portfolio_series),
        "volatility": compute_volatility(portfolio_series),
        "sharpe_ratio": compute_sharpe_ratio(portfolio_series),
        "max_drawdown": compute_max_drawdown(portfolio_series),
        "beta": 1.0,
    }

    if benchmark_series is not None and not benchmark_series.empty:
        metrics["beta"] = compute_beta(portfolio_series, benchmark_series)

    return metrics