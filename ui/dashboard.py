"""
Main Dashboard view.
Shows portfolio summary, equity curve, and holdings table.
"""

import pyqtgraph as pg
import pandas as pd
import numpy as np
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QFrame, QSizePolicy,
    QHeaderView, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QBrush

from core.portfolio import Portfolio
from core.benchmark import align_series, get_normalized_benchmark
from data.fetch import fetch_benchmark_prices
from utils.export import export_trades_to_csv, export_holdings_to_csv, export_to_excel


DARK_BG = "#0b0d14"
CARD_BG = "#12151f"
BORDER = "#1e2130"
ACCENT = "#00d4aa"
RED = "#ff6060"
TEXT = "#c8c8c8"
DIM = "#506070"

pg.setConfigOption("background", CARD_BG)
pg.setConfigOption("foreground", "#6070a0")


class PortfolioDataWorker(QThread):
    """Background worker for expensive portfolio computations."""
    data_ready = Signal(dict)

    def __init__(self, portfolio: Portfolio):
        super().__init__()
        self.portfolio = portfolio

    def run(self):
        try:
            value_series = self.portfolio.get_value_series()
            bench_series = pd.Series(dtype=float)
            if not value_series.empty:
                start = (
                    value_series.index[0].strftime("%Y-%m-%d")
                    if hasattr(value_series.index[0], "strftime")
                    else str(value_series.index[0])[:10]
                )
                bench_series = fetch_benchmark_prices(self.portfolio.benchmark, start=start)

            holdings = self.portfolio.get_holdings_with_market_data()
            total_val = self.portfolio.total_value()
            cash = self.portfolio.cash
            initial = self.portfolio.initial_capital
            port_return = (total_val - initial) / initial * 100 if initial > 0 else 0.0

            bench_return = 0.0
            if not bench_series.empty:
                bench_return = (float(bench_series.iloc[-1]) - float(bench_series.iloc[0])) / float(bench_series.iloc[0]) * 100

            self.data_ready.emit({
                "value_series": value_series,
                "bench_series": bench_series,
                "holdings": holdings,
                "total_value": total_val,
                "cash": cash,
                "port_return": port_return,
                "bench_return": bench_return,
                "initial": initial,
            })
        except Exception as e:
            self.data_ready.emit({"error": str(e)})


class StatCard(QFrame):
    """Compact stat display card."""
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        self._title_lbl = QLabel(title.upper())
        self._title_lbl.setObjectName("statTitle")
        self._val_lbl = QLabel("--")
        self._val_lbl.setObjectName("statValue")
        layout.addWidget(self._title_lbl)
        layout.addWidget(self._val_lbl)

    def set_value(self, text: str, color: str = TEXT):
        self._val_lbl.setText(text)
        self._val_lbl.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: 700; font-family: 'Courier New', monospace;")


class Dashboard(QWidget):
    """
    Main portfolio dashboard.
    Emits show_analytics() when user navigates to analytics view.
    """

    show_analytics = Signal()
    go_back = Signal()

    def __init__(self, portfolio: Portfolio, parent=None):
        super().__init__(parent)
        self.portfolio = portfolio
        self._worker = None
        self._build_ui()
        self._apply_styles()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(52)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 0, 20, 0)

        brand = QLabel("PHONEX TRADE")
        brand.setObjectName("topBrand")

        self.portfolio_label = QLabel(self.portfolio.name.upper())
        self.portfolio_label.setObjectName("portfolioName")

        back_btn = QPushButton("All Portfolios")
        back_btn.setObjectName("topBtn")
        back_btn.clicked.connect(self.go_back.emit)

        top_layout.addWidget(back_btn)
        top_layout.addStretch()
        top_layout.addWidget(brand)
        top_layout.addStretch()
        top_layout.addWidget(self.portfolio_label)
        root.addWidget(top_bar)

        # Main body: sidebar + content
        body = QHBoxLayout()
        body.setSpacing(0)
        body.setContentsMargins(0, 0, 0, 0)
        root.addLayout(body)

        # --- Sidebar ---
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(16, 24, 16, 24)
        sb_layout.setSpacing(8)

        nav_label = QLabel("NAVIGATION")
        nav_label.setObjectName("navLabel")
        sb_layout.addWidget(nav_label)

        self.trade_btn = QPushButton("+ Add Trade")
        self.trade_btn.setObjectName("sideBtn")
        self.analytics_btn = QPushButton("Analytics")
        self.analytics_btn.setObjectName("sideBtn")
        self.analytics_btn.clicked.connect(self.show_analytics.emit)
        self.export_btn = QPushButton("Export Data")
        self.export_btn.setObjectName("sideBtn")
        self.export_btn.clicked.connect(self._on_export)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("sideBtnAccent")
        self.refresh_btn.clicked.connect(self.refresh)

        for btn in [self.trade_btn, self.analytics_btn, self.export_btn]:
            sb_layout.addWidget(btn)
        sb_layout.addSpacing(12)
        sb_layout.addWidget(self.refresh_btn)
        sb_layout.addStretch()

        body.addWidget(sidebar)

        # --- Main content ---
        content = QWidget()
        content.setObjectName("content")
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(20, 20, 20, 20)
        c_layout.setSpacing(16)

        # Stat cards row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        self.card_value = StatCard("Portfolio Value")
        self.card_return = StatCard("Total Return")
        self.card_bench = StatCard("Benchmark Return")
        self.card_cash = StatCard("Cash Available")
        for card in [self.card_value, self.card_return, self.card_bench, self.card_cash]:
            cards_row.addWidget(card)
        c_layout.addLayout(cards_row)

        # Equity curve chart
        chart_frame = QFrame()
        chart_frame.setObjectName("chartFrame")
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.setContentsMargins(16, 16, 16, 16)
        chart_layout.setSpacing(8)

        chart_header = QHBoxLayout()
        chart_title = QLabel("EQUITY CURVE")
        chart_title.setObjectName("sectionTitle")
        self.loading_label = QLabel("Loading...")
        self.loading_label.setObjectName("loadingLabel")
        chart_header.addWidget(chart_title)
        chart_header.addStretch()
        chart_header.addWidget(self.loading_label)
        chart_layout.addLayout(chart_header)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setMinimumHeight(220)
        self.plot_widget.setLabel("left", "Value (normalized)", color=DIM)
        self.plot_widget.getAxis("bottom").setStyle(tickFont=QFont("Courier New", 8))
        self.plot_widget.getAxis("left").setStyle(tickFont=QFont("Courier New", 8))
        self.plot_widget.showGrid(x=True, y=True, alpha=0.15)
        chart_layout.addWidget(self.plot_widget)

        # Legend
        legend_layout = QHBoxLayout()
        for label, color in [(f"Portfolio ({self.portfolio.name})", ACCENT), (self.portfolio.benchmark, "#f0a030")]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 14px;")
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
            legend_layout.addWidget(dot)
            legend_layout.addWidget(lbl)
            legend_layout.addSpacing(16)
        legend_layout.addStretch()
        chart_layout.addLayout(legend_layout)
        c_layout.addWidget(chart_frame)

        # Holdings table
        holdings_frame = QFrame()
        holdings_frame.setObjectName("chartFrame")
        h_layout = QVBoxLayout(holdings_frame)
        h_layout.setContentsMargins(16, 16, 16, 16)
        h_layout.setSpacing(8)

        holdings_title = QLabel("HOLDINGS")
        holdings_title.setObjectName("sectionTitle")
        h_layout.addWidget(holdings_title)

        self.holdings_table = QTableWidget()
        columns = ["Symbol", "Qty", "Avg Price", "Current Price",
                   "Invested", "Current Value", "P&L (Rs.)", "P&L (%)", "Allocation"]
        self.holdings_table.setColumnCount(len(columns))
        self.holdings_table.setHorizontalHeaderLabels(columns)
        self.holdings_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.holdings_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.holdings_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.holdings_table.setAlternatingRowColors(True)
        self.holdings_table.verticalHeader().setVisible(False)
        self.holdings_table.setMinimumHeight(180)
        h_layout.addWidget(self.holdings_table)
        c_layout.addWidget(holdings_frame)

        body.addWidget(content)

    def set_trade_handler(self, handler):
        """Connect the trade button to an external handler."""
        self.trade_btn.clicked.connect(handler)

    def refresh(self):
        """Reload all portfolio data in background thread."""
        self.loading_label.setText("Loading...")
        self.loading_label.show()
        self.portfolio.refresh()
        self._worker = PortfolioDataWorker(self.portfolio)
        self._worker.data_ready.connect(self._on_data_ready)
        self._worker.start()

    def _on_data_ready(self, data: dict):
        self.loading_label.hide()

        if "error" in data:
            self.loading_label.setText(f"Error: {data['error']}")
            self.loading_label.show()
            return

        # Update stat cards
        tv = data["total_value"]
        pr = data["port_return"]
        br = data["bench_return"]
        cash = data["cash"]

        self.card_value.set_value(f"Rs. {tv:,.0f}", ACCENT)
        self.card_return.set_value(
            f"{'+' if pr >= 0 else ''}{pr:.2f}%",
            ACCENT if pr >= 0 else RED,
        )
        self.card_bench.set_value(
            f"{'+' if br >= 0 else ''}{br:.2f}%",
            "#f0a030",
        )
        self.card_cash.set_value(f"Rs. {cash:,.0f}", "#80c8ff")

        # Update chart
        self._update_chart(data["value_series"], data["bench_series"])

        # Update holdings table
        self._update_holdings_table(data["holdings"])

    def _update_chart(self, value_series: pd.Series, bench_series: pd.Series):
        self.plot_widget.clear()

        if value_series.empty:
            return

        port_norm, bench_norm = align_series(value_series, bench_series)

        x_values = list(range(len(port_norm)))

        port_curve = self.plot_widget.plot(
            x_values, port_norm.values,
            pen=pg.mkPen(color=ACCENT, width=2),
            name=self.portfolio.name,
        )

        if not bench_norm.empty:
            bench_x = list(range(len(bench_norm)))
            self.plot_widget.plot(
                bench_x, bench_norm.values,
                pen=pg.mkPen(color="#f0a030", width=1.5, style=Qt.DashLine),
                name=self.portfolio.benchmark,
            )

        # Fill under portfolio curve
        fill = pg.FillBetweenItem(
            port_curve,
            self.plot_widget.plot(x_values, [100.0] * len(x_values), pen=pg.mkPen(None)),
            brush=pg.mkBrush(color=(0, 212, 170, 25)),
        )
        self.plot_widget.addItem(fill)

        # Date tick labels (show every ~10 ticks)
        if not port_norm.empty:
            dates = [str(d)[:10] for d in port_norm.index]
            step = max(1, len(dates) // 8)
            ticks = [(i, dates[i]) for i in range(0, len(dates), step)]
            self.plot_widget.getAxis("bottom").setTicks([ticks])

    def _update_holdings_table(self, holdings: list[dict]):
        self.holdings_table.setRowCount(0)
        if not holdings:
            return

        self.holdings_table.setRowCount(len(holdings))
        for row_idx, h in enumerate(holdings):
            pnl_color = QColor(ACCENT) if h["pnl_abs"] >= 0 else QColor(RED)

            def cell(text, align=Qt.AlignCenter, color=None):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(align)
                if color:
                    item.setForeground(QBrush(color))
                return item

            self.holdings_table.setItem(row_idx, 0, cell(h["symbol"], Qt.AlignLeft | Qt.AlignVCenter))
            self.holdings_table.setItem(row_idx, 1, cell(f"{h['quantity']:.4f}"))
            self.holdings_table.setItem(row_idx, 2, cell(f"Rs. {h['avg_price']:,.2f}"))
            self.holdings_table.setItem(row_idx, 3, cell(f"Rs. {h['current_price']:,.2f}"))
            self.holdings_table.setItem(row_idx, 4, cell(f"Rs. {h['invested_value']:,.0f}"))
            self.holdings_table.setItem(row_idx, 5, cell(f"Rs. {h['current_value']:,.0f}"))
            self.holdings_table.setItem(row_idx, 6, cell(
                f"{'+'if h['pnl_abs']>=0 else ''}Rs. {h['pnl_abs']:,.0f}", color=pnl_color
            ))
            self.holdings_table.setItem(row_idx, 7, cell(
                f"{'+'if h['pnl_pct']>=0 else ''}{h['pnl_pct']:.2f}%", color=pnl_color
            ))
            self.holdings_table.setItem(row_idx, 8, cell(f"{h['allocation_pct']:.1f}%"))

    def _on_export(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Export Folder")
        if not folder:
            return

        import os
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"{self.portfolio.name.replace(' ', '_')}_{ts}"

        try:
            trades = self.portfolio.get_all_trades()
            holdings = self.portfolio.get_holdings_with_market_data()

            export_trades_to_csv(trades, os.path.join(folder, f"{base}_trades.csv"))
            export_holdings_to_csv(holdings, os.path.join(folder, f"{base}_holdings.csv"))
            export_to_excel(trades, holdings, os.path.join(folder, f"{base}.xlsx"))

            QMessageBox.information(self, "Export Complete",
                f"Files saved to:\n{folder}\n\n"
                f"- {base}_trades.csv\n"
                f"- {base}_holdings.csv\n"
                f"- {base}.xlsx")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    def _apply_styles(self):
        self.setStyleSheet(f"""
            Dashboard {{
                background: {DARK_BG};
            }}
            QFrame#topBar {{
                background: #0d1018;
                border-bottom: 1px solid {BORDER};
            }}
            QLabel#topBrand {{
                font-family: 'Courier New', monospace;
                font-size: 14px;
                font-weight: 700;
                color: {ACCENT};
                letter-spacing: 5px;
            }}
            QLabel#portfolioName {{
                font-family: 'Courier New', monospace;
                font-size: 12px;
                color: {DIM};
                letter-spacing: 2px;
            }}
            QPushButton#topBtn {{
                background: transparent;
                color: {ACCENT};
                border: none;
                font-size: 12px;
                padding: 4px 0;
            }}
            QPushButton#topBtn:hover {{
                color: #80f0d8;
            }}
            QFrame#sidebar {{
                background: #0d1018;
                border-right: 1px solid {BORDER};
            }}
            QLabel#navLabel {{
                font-family: 'Courier New', monospace;
                font-size: 10px;
                color: {DIM};
                letter-spacing: 3px;
                margin-bottom: 4px;
            }}
            QPushButton#sideBtn {{
                background: transparent;
                color: #a0b0c0;
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 10px 14px;
                text-align: left;
                font-size: 13px;
            }}
            QPushButton#sideBtn:hover {{
                background: #161a26;
                color: #e8e8e8;
                border-color: #3a3d4a;
            }}
            QPushButton#sideBtnAccent {{
                background: #001a14;
                color: {ACCENT};
                border: 1px solid #00503a;
                border-radius: 6px;
                padding: 10px 14px;
                text-align: left;
                font-size: 13px;
            }}
            QPushButton#sideBtnAccent:hover {{
                background: #002a20;
            }}
            QWidget#content {{
                background: {DARK_BG};
            }}
            QFrame#statCard {{
                background: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            QLabel#statTitle {{
                font-family: 'Courier New', monospace;
                font-size: 10px;
                color: {DIM};
                letter-spacing: 2px;
            }}
            QFrame#chartFrame {{
                background: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
            QLabel#sectionTitle {{
                font-family: 'Courier New', monospace;
                font-size: 11px;
                color: {DIM};
                letter-spacing: 3px;
            }}
            QLabel#loadingLabel {{
                color: {DIM};
                font-size: 12px;
            }}
            QTableWidget {{
                background: {DARK_BG};
                alternate-background-color: #111520;
                border: none;
                gridline-color: {BORDER};
                color: {TEXT};
                font-size: 13px;
                font-family: 'Courier New', monospace;
                outline: none;
            }}
            QHeaderView::section {{
                background: #0d1018;
                color: {DIM};
                border: none;
                border-bottom: 1px solid {BORDER};
                padding: 8px;
                font-family: 'Courier New', monospace;
                font-size: 11px;
                letter-spacing: 1px;
            }}
            QTableWidget::item {{
                padding: 6px 8px;
                border-bottom: 1px solid #161920;
            }}
            QTableWidget::item:selected {{
                background: #1a2a3a;
                color: #e8e8e8;
            }}
        """)