"""
Benchmark data handling for portfolio comparison.
"""

import pandas as pd
from data.fetch import fetch_benchmark_prices


def get_normalized_benchmark(benchmark_name: str, start_date: str) -> pd.Series:
    """
    Fetch benchmark data and normalize to 100 starting from start_date.
    Returns a Series indexed by date.
    """
    series = fetch_benchmark_prices(benchmark_name, start=start_date)
    if series.empty:
        return series

    # Trim to start_date
    series = series[series.index >= pd.Timestamp(start_date)]
    if series.empty:
        return series

    return normalize_series(series)


def normalize_series(series: pd.Series) -> pd.Series:
    """
    Normalize a series so the first value equals 100.
    """
    if series.empty:
        return series
    return (series / series.iloc[0]) * 100.0


def align_series(portfolio: pd.Series, benchmark: pd.Series) -> tuple[pd.Series, pd.Series]:
    """
    Align portfolio and benchmark to the same date index.
    Both are normalized to 100 at the common start date.
    """
    if portfolio.empty or benchmark.empty:
        return portfolio, benchmark

    combined = pd.concat([portfolio, benchmark], axis=1).dropna()
    if combined.empty:
        return portfolio, benchmark

    combined.columns = ["portfolio", "benchmark"]
    port_norm = normalize_series(combined["portfolio"])
    bench_norm = normalize_series(combined["benchmark"])
    return port_norm, bench_norm