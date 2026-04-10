"""
Analytics view for portfolio deep-dive.
Shows drawdown chart, return histogram, and monthly heatmap.
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from core.portfolio import Portfolio
from core.metrics import (
    compute_all_metrics, compute_drawdown_series, compute_daily_returns,
    compute_monthly_returns,
)
from core.benchmark import get_normalized_benchmark
from data.fetch import fetch_benchmark_prices


DARK_BG = "#0b0d14"
CARD_BG = "#12151f"
BORDER = "#1e2130"
ACCENT = "#00d4aa"
TEXT = "#c8c8c8"
DIM = "#505878"


class AnalyticsWorker(QThread):
    """Background worker to compute all analytics data."""
    ready = Signal(dict)

    def __init__(self, portfolio: Portfolio):
        super().__init__()
        self.portfolio = portfolio

    def run(self):
        try:
            value_series = self.portfolio.get_value_series()
            bench_series = pd.Series(dtype=float)
            if value_series is not None and not value_series.empty:
                start = value_series.index[0].strftime("%Y-%m-%d") if hasattr(value_series.index[0], "strftime") else str(value_series.index[0])[:10]
                bench_series = fetch_benchmark_prices(self.portfolio.benchmark, start=start)

            metrics = compute_all_metrics(value_series, bench_series if not bench_series.empty else None)
            drawdown = compute_drawdown_series(value_series)
            returns = compute_daily_returns(value_series) * 100
            monthly = compute_monthly_returns(value_series)

            self.ready.emit({
                "metrics": metrics,
                "drawdown": drawdown,
                "returns": returns,
                "monthly": monthly,
                "value_series": value_series,
            })
        except Exception as e:
            self.ready.emit({"error": str(e)})


class MetricCard(QFrame):
    """Single metric display card."""
    def __init__(self, title: str, value: str, color: str = TEXT, parent=None):
        super().__init__(parent)
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        lbl = QLabel(title)
        lbl.setObjectName("metricTitle")
        val = QLabel(value)
        val.setObjectName("metricValue")
        val.setStyleSheet(f"color: {color};")

        layout.addWidget(lbl)
        layout.addWidget(val)


class AnalyticsView(QWidget):
    """
    Full analytics view with metrics cards and matplotlib charts.
    """

    back_clicked = Signal()

    def __init__(self, portfolio: Portfolio, parent=None):
        super().__init__(parent)
        self.portfolio = portfolio
        self._worker = None
        self._build_ui()
        self._apply_styles()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        back_btn = QPushButton("< Back to Dashboard")
        back_btn.setObjectName("backBtn")
        back_btn.clicked.connect(self.back_clicked.emit)
        title = QLabel(f"ANALYTICS  |  {self.portfolio.name.upper()}")
        title.setObjectName("viewTitle")
        header.addWidget(back_btn)
        header.addStretch()
        header.addWidget(title)
        layout.addLayout(header)

        # Loading label
        self.status_label = QLabel("Computing analytics...")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("analyticsScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(20)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self.content_widget)
        layout.addWidget(scroll)

    def _load_data(self):
        self._worker = AnalyticsWorker(self.portfolio)
        self._worker.ready.connect(self._on_data_ready)
        self._worker.start()

    def _on_data_ready(self, data: dict):
        self.status_label.hide()

        if "error" in data:
            self.status_label.setText(f"Error: {data['error']}")
            self.status_label.show()
            return

        self._render_metrics(data["metrics"])
        self._render_drawdown(data["drawdown"])
        self._render_histogram(data["returns"])
        self._render_heatmap(data["monthly"])

    def _render_metrics(self, metrics: dict):
        row = QHBoxLayout()
        row.setSpacing(12)

        def fmt_pct(v): return f"{v*100:.2f}%"
        def fmt_ratio(v): return f"{v:.2f}"

        cards_data = [
            ("CAGR", fmt_pct(metrics.get("cagr", 0)), ACCENT),
            ("Volatility", fmt_pct(metrics.get("volatility", 0)), "#f0a030"),
            ("Sharpe Ratio", fmt_ratio(metrics.get("sharpe_ratio", 0)), "#80c8ff"),
            ("Max Drawdown", fmt_pct(metrics.get("max_drawdown", 0)), "#ff6060"),
            ("Beta", fmt_ratio(metrics.get("beta", 1.0)), "#c0c0ff"),
        ]

        for title, value, color in cards_data:
            card = MetricCard(title, value, color)
            row.addWidget(card)

        container = QWidget()
        container.setLayout(row)
        self.content_layout.addWidget(container)

    def _make_figure(self, figsize=(10, 3)) -> tuple:
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor("#0b0d14")
        ax.set_facecolor("#12151f")
        ax.tick_params(colors="#6070a0", labelsize=9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        for spine in ["bottom", "left"]:
            ax.spines[spine].set_color("#1e2130")
        ax.xaxis.label.set_color("#6070a0")
        ax.yaxis.label.set_color("#6070a0")
        return fig, ax

    def _embed_fig(self, fig, title_text: str):
        frame = QFrame()
        frame.setObjectName("chartFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel(title_text)
        title.setObjectName("chartTitle")
        layout.addWidget(title)

        canvas = FigureCanvas(fig)
        canvas.setMinimumHeight(240)
        layout.addWidget(canvas)
        self.content_layout.addWidget(frame)

    def _render_drawdown(self, drawdown: pd.Series):
        if drawdown.empty:
            return
        fig, ax = self._make_figure(figsize=(10, 2.5))
        ax.fill_between(drawdown.index, drawdown.values * 100, 0,
                        color="#ff6060", alpha=0.4, linewidth=0)
        ax.plot(drawdown.index, drawdown.values * 100, color="#ff6060", linewidth=1)
        ax.set_ylabel("Drawdown (%)")
        ax.axhline(0, color="#2a2d3a", linewidth=0.5)
        plt.tight_layout(pad=0.5)
        self._embed_fig(fig, "DRAWDOWN")

    def _render_histogram(self, returns: pd.Series):
        if returns.empty:
            return
        fig, ax = self._make_figure(figsize=(10, 2.5))
        n, bins, patches = ax.hist(returns.dropna(), bins=40, edgecolor="none")
        for patch, left in zip(patches, bins[:-1]):
            patch.set_facecolor("#00d4aa" if left >= 0 else "#ff6060")
            patch.set_alpha(0.75)
        ax.axvline(0, color="#ffffff", linewidth=0.5, linestyle="--", alpha=0.4)
        ax.set_xlabel("Daily Return (%)")
        ax.set_ylabel("Frequency")
        plt.tight_layout(pad=0.5)
        self._embed_fig(fig, "DAILY RETURN DISTRIBUTION")

    def _render_heatmap(self, monthly: pd.DataFrame):
        if monthly.empty:
            return
        fig, ax = self._make_figure(figsize=(10, max(2.5, len(monthly) * 0.5)))
        vmax = max(abs(monthly.values[~np.isnan(monthly.values)]).max(), 0.01) if monthly.size > 0 else 5

        cmap = mcolors.LinearSegmentedColormap.from_list(
            "rdgn", ["#ff4040", "#0b0d14", "#00d4aa"]
        )
        im = ax.imshow(monthly.values, cmap=cmap, vmin=-vmax, vmax=vmax, aspect="auto")
        ax.set_xticks(range(len(monthly.columns)))
        ax.set_xticklabels(monthly.columns, fontsize=9, color="#8090b0")
        ax.set_yticks(range(len(monthly.index)))
        ax.set_yticklabels(monthly.index, fontsize=9, color="#8090b0")

        for r in range(len(monthly.index)):
            for c in range(len(monthly.columns)):
                val = monthly.values[r, c]
                if not np.isnan(val):
                    ax.text(c, r, f"{val:.1f}%", ha="center", va="center",
                            fontsize=8, color="#e8e8e8" if abs(val) < vmax * 0.6 else "#ffffff")

        fig.colorbar(im, ax=ax, label="Return %", shrink=0.6)
        plt.tight_layout(pad=0.5)
        self._embed_fig(fig, "MONTHLY RETURNS HEATMAP")

    def _apply_styles(self):
        self.setStyleSheet("""
            AnalyticsView {
                background: #0b0d14;
            }
            QLabel#viewTitle {
                font-family: 'Courier New', monospace;
                font-size: 14px;
                color: #506070;
                letter-spacing: 2px;
            }
            QLabel#statusLabel {
                color: #506070;
                font-size: 13px;
            }
            QPushButton#backBtn {
                background: transparent;
                color: #00d4aa;
                border: none;
                font-size: 13px;
                padding: 4px 0;
            }
            QPushButton#backBtn:hover {
                color: #80f0d8;
            }
            QFrame#chartFrame {
                background: #12151f;
                border: 1px solid #1e2130;
                border-radius: 10px;
            }
            QLabel#chartTitle {
                font-family: 'Courier New', monospace;
                font-size: 11px;
                color: #506070;
                letter-spacing: 3px;
            }
            QFrame#metricCard {
                background: #12151f;
                border: 1px solid #1e2130;
                border-radius: 8px;
            }
            QLabel#metricTitle {
                font-family: 'Courier New', monospace;
                font-size: 10px;
                color: #506070;
                letter-spacing: 2px;
            }
            QLabel#metricValue {
                font-family: 'Courier New', monospace;
                font-size: 22px;
                font-weight: 700;
            }
            QScrollArea#analyticsScroll {
                background: transparent;
                border: none;
            }
            QScrollArea#analyticsScroll > QWidget > QWidget {
                background: transparent;
            }
        """)