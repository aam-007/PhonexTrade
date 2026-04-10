"""
Portfolio Selector screen.
First screen shown on app launch. Allows creating or selecting a portfolio.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QDialog, QLineEdit,
    QDoubleSpinBox, QComboBox, QFormLayout, QMessageBox,
    QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

import data.database as db


class CreatePortfolioDialog(QDialog):
    """Dialog for creating a new portfolio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Portfolio")
        self.setMinimumWidth(400)
        self.setModal(True)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("New Portfolio")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Growth Portfolio")
        form.addRow("Name:", self.name_input)

        self.capital_input = QDoubleSpinBox()
        self.capital_input.setMinimum(1000.0)
        self.capital_input.setMaximum(100_000_000.0)
        self.capital_input.setValue(100_000.0)
        self.capital_input.setSingleStep(10_000.0)
        self.capital_input.setPrefix("Rs. ")
        form.addRow("Initial Capital:", self.capital_input)

        self.benchmark_combo = QComboBox()
        self.benchmark_combo.addItems(["Nifty 500", "Nifty 50"])
        form.addRow("Benchmark:", self.benchmark_combo)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        create_btn = QPushButton("Create")
        create_btn.setObjectName("createBtn")
        create_btn.clicked.connect(self._on_create)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(create_btn)
        layout.addLayout(btn_layout)

    def _on_create(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Portfolio name cannot be empty.")
            return
        self.accept()

    def get_values(self) -> tuple[str, float, str]:
        return (
            self.name_input.text().strip(),
            self.capital_input.value(),
            self.benchmark_combo.currentText(),
        )

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background: #0f1117;
            }
            QLabel#dialogTitle {
                font-size: 20px;
                font-weight: 700;
                color: #e8e8e8;
                font-family: 'Courier New', monospace;
                letter-spacing: 1px;
            }
            QLabel {
                color: #a0a0a0;
                font-size: 13px;
            }
            QLineEdit, QDoubleSpinBox, QComboBox {
                background: #1a1d27;
                border: 1px solid #2a2d3a;
                border-radius: 6px;
                color: #e8e8e8;
                padding: 8px 12px;
                font-size: 13px;
                min-height: 36px;
            }
            QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus {
                border-color: #00d4aa;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 8px;
            }
            QPushButton#createBtn {
                background: #00d4aa;
                color: #0f1117;
                border: none;
                border-radius: 6px;
                padding: 9px 24px;
                font-weight: 700;
                font-size: 13px;
                min-width: 90px;
            }
            QPushButton#createBtn:hover {
                background: #00eabb;
            }
            QPushButton#cancelBtn {
                background: transparent;
                color: #a0a0a0;
                border: 1px solid #2a2d3a;
                border-radius: 6px;
                padding: 9px 20px;
                font-size: 13px;
                min-width: 80px;
            }
            QPushButton#cancelBtn:hover {
                color: #e8e8e8;
                border-color: #4a4d5a;
            }
        """)


class PortfolioSelector(QWidget):
    """
    Portfolio selector screen.
    Emits portfolio_selected(int) when a portfolio is chosen.
    """

    portfolio_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._apply_styles()
        self._load_portfolios()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Center card
        center = QHBoxLayout()
        center.setAlignment(Qt.AlignCenter)
        outer.addStretch(1)
        outer.addLayout(center)
        outer.addStretch(2)

        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(520)
        center.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 40, 40, 40)

        # Branding
        brand = QLabel("PHONEX TRADE")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignCenter)
        layout.addWidget(brand)

        tagline = QLabel("Paper Trading & Portfolio Analytics")
        tagline.setObjectName("tagline")
        tagline.setAlignment(Qt.AlignCenter)
        layout.addWidget(tagline)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setObjectName("divider")
        layout.addWidget(divider)

        # Portfolio list
        list_label = QLabel("SELECT PORTFOLIO")
        list_label.setObjectName("sectionLabel")
        layout.addWidget(list_label)

        self.portfolio_list = QListWidget()
        self.portfolio_list.setObjectName("portfolioList")
        self.portfolio_list.setMinimumHeight(200)
        self.portfolio_list.itemDoubleClicked.connect(self._on_open)
        layout.addWidget(self.portfolio_list)

        # Buttons
        btn_layout = QHBoxLayout()
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setObjectName("deleteBtn")
        self.delete_btn.clicked.connect(self._on_delete)
        self.new_btn = QPushButton("+ New Portfolio")
        self.new_btn.setObjectName("newBtn")
        self.new_btn.clicked.connect(self._on_new)
        self.open_btn = QPushButton("Open")
        self.open_btn.setObjectName("openBtn")
        self.open_btn.clicked.connect(self._on_open)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.new_btn)
        btn_layout.addWidget(self.open_btn)
        layout.addLayout(btn_layout)

    def _load_portfolios(self):
        self.portfolio_list.clear()
        portfolios = db.get_all_portfolios()
        for p in portfolios:
            item = QListWidgetItem(f"  {p['name']}   |   Rs. {p['initial_capital']:,.0f}   |   {p['benchmark']}")
            item.setData(Qt.UserRole, p["id"])
            self.portfolio_list.addItem(item)

    def _on_new(self):
        dialog = CreatePortfolioDialog(self)
        if dialog.exec() == QDialog.Accepted:
            name, capital, benchmark = dialog.get_values()
            try:
                portfolio_id = db.create_portfolio(name, capital, benchmark)
                self._load_portfolios()
                # Auto-open newly created portfolio
                self.portfolio_selected.emit(portfolio_id)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not create portfolio:\n{e}")

    def _on_open(self):
        item = self.portfolio_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Select Portfolio", "Please select a portfolio to open.")
            return
        portfolio_id = item.data(Qt.UserRole)
        self.portfolio_selected.emit(portfolio_id)

    def _on_delete(self):
        item = self.portfolio_list.currentItem()
        if item is None:
            return
        name = item.text().split("|")[0].strip()
        portfolio_id = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete portfolio '{name}' and all its trades?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            db.delete_portfolio(portfolio_id)
            self._load_portfolios()

    def _apply_styles(self):
        self.setStyleSheet("""
            PortfolioSelector {
                background: #0b0d14;
            }
            QFrame#card {
                background: #12151f;
                border: 1px solid #1e2130;
                border-radius: 12px;
            }
            QLabel#brand {
                font-family: 'Courier New', monospace;
                font-size: 28px;
                font-weight: 700;
                color: #00d4aa;
                letter-spacing: 6px;
            }
            QLabel#tagline {
                font-size: 12px;
                color: #505878;
                letter-spacing: 2px;
                font-family: 'Courier New', monospace;
            }
            QFrame#divider {
                border: none;
                border-top: 1px solid #1e2130;
                margin: 4px 0;
            }
            QLabel#sectionLabel {
                font-size: 11px;
                color: #505878;
                letter-spacing: 2px;
                font-family: 'Courier New', monospace;
            }
            QListWidget#portfolioList {
                background: #0f1117;
                border: 1px solid #1e2130;
                border-radius: 8px;
                color: #c8c8c8;
                font-size: 13px;
                outline: none;
                padding: 4px;
            }
            QListWidget#portfolioList::item {
                padding: 10px 8px;
                border-radius: 6px;
                border-bottom: 1px solid #1a1d27;
            }
            QListWidget#portfolioList::item:selected {
                background: #1a3040;
                color: #00d4aa;
            }
            QListWidget#portfolioList::item:hover {
                background: #161a26;
            }
            QPushButton#openBtn {
                background: #00d4aa;
                color: #0f1117;
                border: none;
                border-radius: 6px;
                padding: 9px 28px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton#openBtn:hover {
                background: #00eabb;
            }
            QPushButton#newBtn {
                background: transparent;
                color: #00d4aa;
                border: 1px solid #00d4aa;
                border-radius: 6px;
                padding: 9px 20px;
                font-size: 13px;
            }
            QPushButton#newBtn:hover {
                background: #001f1a;
            }
            QPushButton#deleteBtn {
                background: transparent;
                color: #ff6060;
                border: 1px solid #3a1a1a;
                border-radius: 6px;
                padding: 9px 16px;
                font-size: 13px;
            }
            QPushButton#deleteBtn:hover {
                background: #2a0a0a;
                border-color: #ff6060;
            }
        """)