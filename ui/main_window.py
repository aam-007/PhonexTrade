"""
Main application window.
Manages screen navigation using QStackedWidget.
"""

from PySide6.QtWidgets import QMainWindow, QStackedWidget, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor

from ui.portfolio_selector import PortfolioSelector
from ui.dashboard import Dashboard
from ui.analytics_view import AnalyticsView
from ui.trade_dialog import TradeDialog
from core.portfolio import Portfolio


class MainWindow(QMainWindow):
    """
    Top-level application window.
    Hosts a QStackedWidget for screen transitions.
    """

    SCREEN_SELECTOR = 0
    SCREEN_DASHBOARD = 1
    SCREEN_ANALYTICS = 2

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PhonexTrade - Paper Trading & Portfolio Analytics")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)

        self._current_portfolio: Portfolio | None = None
        self._dashboard: Dashboard | None = None
        self._analytics: AnalyticsView | None = None

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._selector = PortfolioSelector()
        self._selector.portfolio_selected.connect(self._open_portfolio)
        self._stack.addWidget(self._selector)  # index 0

        # Placeholders (rebuilt dynamically per portfolio)
        self._stack.addWidget(QStackedWidget())  # index 1 (dashboard)
        self._stack.addWidget(QStackedWidget())  # index 2 (analytics)

        self._apply_global_styles()
        self._stack.setCurrentIndex(self.SCREEN_SELECTOR)

    def _open_portfolio(self, portfolio_id: int):
        """Load a portfolio and navigate to the dashboard."""
        try:
            portfolio = Portfolio(portfolio_id)
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Could not load portfolio: {e}")
            return

        self._current_portfolio = portfolio
        self._rebuild_dashboard()
        self._stack.setCurrentIndex(self.SCREEN_DASHBOARD)

    def _rebuild_dashboard(self):
        """Create a fresh dashboard for the current portfolio."""
        if self._dashboard is not None:
            old = self._stack.widget(self.SCREEN_DASHBOARD)
            self._stack.removeWidget(old)
            old.deleteLater()
            self._dashboard = None

        if self._analytics is not None:
            old = self._stack.widget(self.SCREEN_ANALYTICS)
            self._stack.removeWidget(old)
            old.deleteLater()
            self._analytics = None

        self._dashboard = Dashboard(self._current_portfolio)
        self._dashboard.go_back.connect(self._go_to_selector)
        self._dashboard.show_analytics.connect(self._show_analytics)
        self._dashboard.set_trade_handler(self._show_trade_dialog)

        # Insert at fixed positions
        self._stack.insertWidget(self.SCREEN_DASHBOARD, self._dashboard)

    def _show_analytics(self):
        """Navigate to analytics view."""
        if self._analytics is not None:
            old = self._stack.widget(self.SCREEN_ANALYTICS)
            self._stack.removeWidget(old)
            old.deleteLater()
            self._analytics = None

        self._analytics = AnalyticsView(self._current_portfolio)
        self._analytics.back_clicked.connect(lambda: self._stack.setCurrentIndex(self.SCREEN_DASHBOARD))
        self._stack.insertWidget(self.SCREEN_ANALYTICS, self._analytics)
        self._stack.setCurrentIndex(self.SCREEN_ANALYTICS)

    def _go_to_selector(self):
        """Return to portfolio selector."""
        self._selector._load_portfolios()
        self._stack.setCurrentIndex(self.SCREEN_SELECTOR)

    def _show_trade_dialog(self):
        """Show trade execution dialog."""
        if self._current_portfolio is None:
            return
        dialog = TradeDialog(self._current_portfolio, self)
        if dialog.exec():
            if self._dashboard:
                self._dashboard.refresh()

    def _apply_global_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background: #0b0d14;
            }
            QScrollBar:vertical {
                background: #0f1117;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #2a2d3a;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3a3d4a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                background: #0f1117;
                height: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background: #2a2d3a;
                border-radius: 4px;
            }
            QToolTip {
                background: #1a1d27;
                color: #e8e8e8;
                border: 1px solid #2a2d3a;
                padding: 4px 8px;
                font-size: 12px;
            }
        """)