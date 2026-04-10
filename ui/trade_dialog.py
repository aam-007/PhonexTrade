"""
Trade execution dialog.
Allows buying and selling stocks with autocomplete search and validation.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QDoubleSpinBox, QCompleter, QButtonGroup,
    QRadioButton, QMessageBox, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal, QStringListModel
from PySide6.QtGui import QFont

from data.fetch import fetch_current_price, search_symbols
from core.portfolio import Portfolio


class PriceFetchWorker(QThread):
    """Background worker for fetching stock price."""
    price_ready = Signal(float)
    error = Signal(str)

    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol

    def run(self):
        price = fetch_current_price(self.symbol)
        if price is not None:
            self.price_ready.emit(price)
        else:
            self.error.emit(f"Could not fetch price for {self.symbol}")


class TradeDialog(QDialog):
    """
    Dialog for executing buy/sell trades.
    """

    def __init__(self, portfolio: Portfolio, parent=None):
        super().__init__(parent)
        self.portfolio = portfolio
        self._current_price: float = 0.0
        self._worker: PriceFetchWorker | None = None
        self.setWindowTitle("Execute Trade")
        self.setMinimumWidth(440)
        self.setModal(True)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(28, 28, 28, 28)

        title = QLabel("EXECUTE TRADE")
        title.setObjectName("tradeTitle")
        layout.addWidget(title)

        # Trade type toggle
        type_layout = QHBoxLayout()
        self.buy_radio = QRadioButton("BUY")
        self.sell_radio = QRadioButton("SELL")
        self.buy_radio.setChecked(True)
        self.buy_radio.setObjectName("buyRadio")
        self.sell_radio.setObjectName("sellRadio")
        self._trade_type_group = QButtonGroup()
        self._trade_type_group.addButton(self.buy_radio, 0)
        self._trade_type_group.addButton(self.sell_radio, 1)
        type_layout.addWidget(self.buy_radio)
        type_layout.addWidget(self.sell_radio)
        type_layout.addStretch()
        layout.addLayout(type_layout)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setObjectName("divider")
        layout.addWidget(divider)

        # Symbol search
        sym_label = QLabel("SYMBOL")
        sym_label.setObjectName("fieldLabel")
        layout.addWidget(sym_label)

        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("Search NSE symbol, e.g. RELIANCE.NS")
        self.symbol_input.textChanged.connect(self._on_symbol_changed)

        self._completer_model = QStringListModel()
        self._completer = QCompleter()
        self._completer.setModel(self._completer_model)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self.symbol_input.setCompleter(self._completer)
        self._completer.activated.connect(self._on_symbol_selected)

        layout.addWidget(self.symbol_input)

        # Price display
        self.price_label = QLabel("Price: --")
        self.price_label.setObjectName("priceDisplay")
        layout.addWidget(self.price_label)

        # Cash display
        self.cash_label = QLabel(f"Available Cash: Rs. {self.portfolio.cash:,.2f}")
        self.cash_label.setObjectName("cashDisplay")
        layout.addWidget(self.cash_label)

        divider2 = QFrame()
        divider2.setFrameShape(QFrame.HLine)
        divider2.setObjectName("divider")
        layout.addWidget(divider2)

        # Input mode toggle
        mode_layout = QHBoxLayout()
        mode_label = QLabel("INPUT:")
        mode_label.setObjectName("fieldLabel")
        self.amount_radio = QRadioButton("Amount (Rs.)")
        self.qty_radio = QRadioButton("Quantity")
        self.amount_radio.setChecked(True)
        self._mode_group = QButtonGroup()
        self._mode_group.addButton(self.amount_radio, 0)
        self._mode_group.addButton(self.qty_radio, 1)
        self._mode_group.buttonClicked.connect(self._on_mode_changed)
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.amount_radio)
        mode_layout.addWidget(self.qty_radio)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        # Amount / Quantity spinbox
        self.value_input = QDoubleSpinBox()
        self.value_input.setMinimum(0.01)
        self.value_input.setMaximum(100_000_000.0)
        self.value_input.setValue(10_000.0)
        self.value_input.setSingleStep(1_000.0)
        self.value_input.setPrefix("Rs. ")
        self.value_input.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.value_input)

        # Auto-calculated field
        self.calc_label = QLabel("Quantity: --")
        self.calc_label.setObjectName("calcDisplay")
        layout.addWidget(self.calc_label)

        layout.addSpacing(8)

        # Execute button
        self.execute_btn = QPushButton("CONFIRM TRADE")
        self.execute_btn.setObjectName("executeBtn")
        self.execute_btn.clicked.connect(self._on_execute)
        layout.addWidget(self.execute_btn)

        # Cancel
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def _on_symbol_changed(self, text: str):
        suggestions = search_symbols(text)
        self._completer_model.setStringList(suggestions)
        self._current_price = 0.0
        self.price_label.setText("Price: --")
        self._update_calc()

        # If exact match, fetch price
        if text.upper() in [s.upper() for s in suggestions] or "." in text:
            self._fetch_price(text)

    def _on_symbol_selected(self, text: str):
        self.symbol_input.setText(text)
        self._fetch_price(text)

    def _fetch_price(self, symbol: str):
        self.price_label.setText("Fetching price...")
        self._worker = PriceFetchWorker(symbol)
        self._worker.price_ready.connect(self._on_price_ready)
        self._worker.error.connect(lambda e: self.price_label.setText(f"Error: {e}"))
        self._worker.start()

    def _on_price_ready(self, price: float):
        self._current_price = price
        self.price_label.setText(f"Current Price:  Rs. {price:,.2f}")
        self._update_calc()

    def _on_mode_changed(self):
        if self.amount_radio.isChecked():
            self.value_input.setPrefix("Rs. ")
            self.value_input.setValue(10_000.0)
            self.value_input.setSingleStep(1_000.0)
        else:
            self.value_input.setPrefix("")
            self.value_input.setValue(10.0)
            self.value_input.setSingleStep(1.0)
        self._update_calc()

    def _on_value_changed(self):
        self._update_calc()

    def _update_calc(self):
        if self._current_price <= 0:
            self.calc_label.setText("--")
            return
        if self.amount_radio.isChecked():
            qty = self.value_input.value() / self._current_price
            self.calc_label.setText(f"Quantity:  {qty:.4f} shares")
        else:
            amount = self.value_input.value() * self._current_price
            self.calc_label.setText(f"Total Amount:  Rs. {amount:,.2f}")

    def _on_execute(self):
        symbol = self.symbol_input.text().strip().upper()
        if not symbol:
            QMessageBox.warning(self, "Validation", "Please enter a stock symbol.")
            return
        if self._current_price <= 0:
            QMessageBox.warning(self, "Validation", "Please wait for price to load.")
            return

        if self.amount_radio.isChecked():
            amount = self.value_input.value()
            quantity = amount / self._current_price
        else:
            quantity = self.value_input.value()

        trade_type = "BUY" if self.buy_radio.isChecked() else "SELL"

        if trade_type == "BUY":
            result = self.portfolio.execute_buy(symbol, quantity, self._current_price)
        else:
            result = self.portfolio.execute_sell(symbol, quantity, self._current_price)

        if result == "ok":
            QMessageBox.information(
                self, "Trade Executed",
                f"{trade_type} {quantity:.4f} shares of {symbol} at Rs. {self._current_price:,.2f}"
            )
            self.accept()
        else:
            QMessageBox.warning(self, "Trade Failed", result)

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background: #0f1117;
            }
            QLabel#tradeTitle {
                font-family: 'Courier New', monospace;
                font-size: 18px;
                font-weight: 700;
                color: #00d4aa;
                letter-spacing: 4px;
            }
            QFrame#divider {
                border: none;
                border-top: 1px solid #1e2130;
                margin: 2px 0;
            }
            QLabel#fieldLabel {
                font-size: 11px;
                color: #506070;
                letter-spacing: 2px;
                font-family: 'Courier New', monospace;
            }
            QLabel#priceDisplay {
                font-size: 16px;
                color: #e8e8e8;
                font-family: 'Courier New', monospace;
                font-weight: 600;
            }
            QLabel#cashDisplay {
                font-size: 13px;
                color: #7090a0;
                font-family: 'Courier New', monospace;
            }
            QLabel#calcDisplay {
                font-size: 14px;
                color: #c8c8c8;
                font-family: 'Courier New', monospace;
            }
            QLineEdit, QDoubleSpinBox {
                background: #1a1d27;
                border: 1px solid #2a2d3a;
                border-radius: 6px;
                color: #e8e8e8;
                padding: 8px 12px;
                font-size: 14px;
                min-height: 38px;
                font-family: 'Courier New', monospace;
            }
            QLineEdit:focus, QDoubleSpinBox:focus {
                border-color: #00d4aa;
            }
            QRadioButton {
                color: #a0a0a0;
                font-size: 13px;
                spacing: 6px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 1px solid #2a2d3a;
                background: #1a1d27;
            }
            QRadioButton::indicator:checked {
                background: #00d4aa;
                border-color: #00d4aa;
            }
            QRadioButton#buyRadio:checked {
                color: #00d4aa;
            }
            QRadioButton#sellRadio:checked {
                color: #ff6060;
            }
            QPushButton#executeBtn {
                background: #00d4aa;
                color: #0f1117;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-weight: 700;
                font-size: 14px;
                letter-spacing: 1px;
                font-family: 'Courier New', monospace;
            }
            QPushButton#executeBtn:hover {
                background: #00eabb;
            }
            QPushButton#cancelBtn {
                background: transparent;
                color: #505878;
                border: none;
                padding: 8px;
                font-size: 13px;
            }
            QPushButton#cancelBtn:hover {
                color: #a0a0a0;
            }
        """)