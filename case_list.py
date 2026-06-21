import sys
import os
import sqlite3
from functools import partial
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QComboBox, QPushButton, QFrame,
    QHBoxLayout, QLineEdit, QCompleter, QDateEdit, QCheckBox
)
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtCore import Qt, QDate


def resource_path(relative_path):
    try:
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(__file__)
        return os.path.normpath(os.path.join(base_path, relative_path))
    except Exception:
        return relative_path


class CaseListStudy(QWidget):
    def __init__(self, db_path="viscan.db", parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.main_window = parent
        self.setWindowTitle("Case List")
        self.resize(1500, 850)

        # Pagination variables
        self.current_page = 1
        self.rows_per_page = 25
        self.total_rows = 0
        self.total_pages = 1

        # keep patient IDs list for matching
        self._pid_list = []

        self.setup_ui()
        self.populate_filters()

        self.table.setRowCount(0)
        self.page_label.setText("Page 0 / 0")

    # ---------- UI ----------
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        self.setStyleSheet("background-color: #004a99;")

        title = QLabel("Case List")
        title.setFont(QFont("Arial", 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: white; padding: 10px;")
        main_layout.addWidget(title)

        # ---------- FILTER BOX ----------
        filter_box = QFrame()
        filter_box.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #b0c4de; border-radius: 10px; }
            QLabel { font-weight: bold; color: #004a99; }
            QComboBox, QLineEdit, QDateEdit {
                min-height: 28px; padding: 2px 6px; border: 1px solid #b0c4de;
                border-radius: 4px; background-color: white;
            }
            QPushButton {
                background-color: #1976d2; color: white;
                padding: 5px 15px; border: none; border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1565c0; }
        """)
        filter_layout = QVBoxLayout(filter_box)
        filter_layout.setContentsMargins(20, 20, 20, 20)
        filter_layout.setSpacing(12)

        # ---------- ROW 0 ----------
        row0 = QHBoxLayout()
        self.select_all_checkbox = QCheckBox("Select All")
        self.select_all_checkbox.stateChanged.connect(self.on_select_all)
        self.select_all_checkbox.setStyleSheet("""
            QCheckBox {
                background-color: white; color: #004a99;
                font-weight: bold; padding: 4px 8px;
                border: 1px solid #b0c4de; border-radius: 5px;
            }
            QCheckBox::indicator { width: 16px; height: 16px; }
        """)
        row0.addWidget(self.select_all_checkbox)
        row0.addStretch()
        filter_layout.addLayout(row0)

        # ---------- ROW 1 ----------
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(QLabel("Patient ID:"))
        self.pid_filter = QComboBox()
        self.pid_filter.setEditable(True)
        self.pid_filter.lineEdit().setPlaceholderText("Select or type Patient ID")
        self.pid_filter.setMaximumWidth(300)
        row1.addWidget(self.pid_filter)


        row1.addWidget(QLabel("Name:"))
        self.name_filter = QLineEdit()
        self.name_filter.setMaximumWidth(180)
        row1.addWidget(self.name_filter)

        row1.addWidget(QLabel("Gender:"))
        self.gender_filter = QComboBox()
        self.gender_filter.addItems(["Select", "Male", "Female", "Other"])
        self.gender_filter.setMaximumWidth(120)
        row1.addWidget(self.gender_filter)
        row1.addStretch()
        filter_layout.addLayout(row1)

        # ---------- ROW 2 ----------
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        # Date frame
        date_frame = QFrame()
        date_frame.setStyleSheet("QFrame { border: 1px solid #b0c4de; border-radius: 6px; padding: 5px; background-color: #fefefe; }")
        date_layout = QHBoxLayout(date_frame)
        date_layout.setContentsMargins(5, 5, 5, 5)
        date_layout.setSpacing(6)

        date_layout.addWidget(QLabel("Search by Date:"))
        self.from_date = QDateEdit(calendarPopup=True)
        self.from_date.setDate(QDate.currentDate().addDays(-30))
        self.from_date.setDisplayFormat("dd-MM-yyyy")
        self.from_date.setMaximumWidth(120)
        date_layout.addWidget(QLabel("From:"))
        date_layout.addWidget(self.from_date)

        self.to_date = QDateEdit(calendarPopup=True)
        self.to_date.setDate(QDate.currentDate())
        self.to_date.setDisplayFormat("dd-MM-yyyy")
        self.to_date.setMaximumWidth(120)
        date_layout.addWidget(QLabel("To:"))
        date_layout.addWidget(self.to_date)

        date_layout.addWidget(QLabel("Search by:"))
        self.quick_date = QComboBox()
        self.quick_date.setMaximumWidth(150)
        self.quick_date.addItems(["Select", "Today", "Yesterday", "Last 1 Week", "Last 2 Weeks", "Last 1 Month", "Last 2 Months"])
        self.quick_date.currentIndexChanged.connect(self.on_quick_date_changed)
        date_layout.addWidget(self.quick_date)
        row2.addWidget(date_frame)

        # Status + Buttons
        row2.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Select", "Registered", "Scan Completed", "View Report"])
        self.status_filter.setMaximumWidth(140)
        row2.addWidget(self.status_filter)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.apply_filters_with_page)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_filters)
        row2.addWidget(search_btn)
        row2.addWidget(clear_btn)
        row2.addStretch()
        filter_layout.addLayout(row2)

        center_layout = QHBoxLayout()
        center_layout.addStretch()
        center_layout.addWidget(filter_box)
        center_layout.addStretch()
        main_layout.addLayout(center_layout)

        # ---------- TABLE ----------
        table_frame = QFrame()
        table_frame.setStyleSheet("QFrame { background-color: white; border: 1px solid #dcdcdc; border-radius: 8px; }")
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(10, 10, 10, 10)

        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Sl No.", "Patient ID", "Name", "Age", "Gender", "Phone",
            "Tobacco", "Alcohol", "Status", "Action"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        table_layout.addWidget(self.table)
        main_layout.addWidget(table_frame)

        # ---------- PAGINATION ----------
        pagination_frame = QFrame()
        pagination_layout = QHBoxLayout(pagination_frame)
        pagination_layout.setSpacing(10)

        self.prev_btn = QPushButton("Prev")
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.next_page)
        self.page_label = QLabel("Page 0 / 0")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setMinimumWidth(100)
        self.page_label.setStyleSheet("color: white; font-weight: bold;")

        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_btn)
        pagination_layout.addStretch()
        main_layout.addWidget(pagination_frame)

        if self.pid_filter.lineEdit():
            self.pid_filter.lineEdit().returnPressed.connect(self.apply_filters_with_page)

    # ---------- Populate Filters ----------
    def populate_filters(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Fetch patient IDs
        cursor.execute("""
            SELECT DISTINCT Patient_id 
            FROM Patient_Details 
            WHERE Patient_id IS NOT NULL 
            ORDER BY Patient_id
        """)
        ids = [str(r[0]) for r in cursor.fetchall()]
        self._pid_list = ids.copy()

        # Populate Patient ID dropdown
        self.pid_filter.clear()
        self.pid_filter.setEditable(True)
        self.pid_filter.lineEdit().setPlaceholderText("Select or type Patient ID")
        self.pid_filter.addItem("Select")
        self.pid_filter.addItems(ids)
        self.pid_filter.setInsertPolicy(QComboBox.NoInsert)

        # Fetch patient names for autocomplete
        cursor.execute("SELECT DISTINCT Patient_Name FROM Patient_Details ORDER BY Patient_Name")
        names = [r[0] for r in cursor.fetchall()]
        conn.close()

        # Attach completer only to name field (this is correct)
        name_completer = QCompleter(names, self.name_filter)
        name_completer.setCaseSensitivity(Qt.CaseInsensitive)
        name_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.name_filter.setCompleter(name_completer)

    # ---------- Quick Date ----------
    def on_quick_date_changed(self, index):
        self.select_all_checkbox.setChecked(False)
        today = QDate.currentDate()
        if index == 1:
            self.from_date.setDate(today)
            self.to_date.setDate(today)
        elif index == 2:
            self.from_date.setDate(today.addDays(-1))
            self.to_date.setDate(today.addDays(-1))
        elif index == 3:
            self.from_date.setDate(today.addDays(-7))
            self.to_date.setDate(today)
        elif index == 4:
            self.from_date.setDate(today.addDays(-14))
            self.to_date.setDate(today)
        elif index == 5:
            self.from_date.setDate(today.addMonths(-1))
            self.to_date.setDate(today)
        elif index == 6:
            self.from_date.setDate(today.addMonths(-2))
            self.to_date.setDate(today)
        self.apply_filters_with_page()

    # ---------- Apply Filters ----------
    def apply_filters_with_page(self):
        if self.select_all_checkbox.isChecked():
            self.load_data(filters=None, page=self.current_page)
            return

        filters = {
            "pid": self.pid_filter.currentText().strip(),
            "name": self.name_filter.text().strip(),
            "gender": self.gender_filter.currentText(),
            "status": self.status_filter.currentText(),
            "from_date": self.from_date.date().toString("yyyy-MM-dd"),
            "to_date": self.to_date.date().toString("yyyy-MM-dd"),
        }
        self.load_data(filters, self.current_page)

        # ---------- Load Data ----------
    def load_data(self, filters=None, page=1):
        self.table.setRowCount(0)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Base query
        query = """
            SELECT 
                pd.Patient_id,
                pd.Patient_Name,
                pd.Age,
                pd.Sex,
                pd.Phone_no,
                pd.Tobacco_Use,
                pd.Alcohol_Use,
                MAX(COALESCE(ic.scan_complete, 0)) AS scan_complete,
                MAX(COALESCE(pr.report_approved, 0)) AS report_approved
            FROM Patient_Details pd
            LEFT JOIN Image_Capture ic ON pd.Patient_id = ic.Patient_id
            LEFT JOIN Patient_Report pr ON pd.Patient_id = pr.Patient_id
            WHERE 1=1
        """
        params = []

        # ✅ Apply filters safely
        if filters:
            pid = filters.get("pid", "")
            if pid and pid.lower() not in ("select", "select all"):
                query += " AND pd.Patient_id LIKE ?"
                params.append(f"%{pid}%")

            name = filters.get("name", "").strip()
            if name:
                query += " AND LOWER(pd.Patient_Name) LIKE ?"
                params.append(f"%{name.lower()}%")

            gender = filters.get("gender", "")
            if gender and gender.lower() != "select":
                query += " AND pd.Sex = ?"
                params.append(gender)

            status = filters.get("status", "")
            if status and status.lower() != "select":
                if status == "Registered":
                    query += " AND (ic.scan_complete IS NULL OR ic.scan_complete = 0)"
                elif status == "Scan Completed":
                    query += " AND (ic.scan_complete = 1 AND (pr.report_approved IS NULL OR pr.report_approved = 0))"
                elif status == "View Report":
                    query += " AND ic.scan_complete = 1 AND pr.report_approved = 1"

            # ✅ Filter by Registration_date range
            from_date = filters.get("from_date")
            to_date = filters.get("to_date")
            if from_date and to_date:
                query += " AND date(pd.Registration_date) BETWEEN date(?) AND date(?)"
                params.extend([from_date, to_date])

        # ✅ Sort by newest registration first
        query += " GROUP BY pd.Patient_id ORDER BY date(pd.Registration_date) DESC"

        # Run and fetch results
        cursor.execute(query, params)
        all_rows = cursor.fetchall()
        conn.close()

        # Pagination logic
        self.total_rows = len(all_rows)
        self.total_pages = max(1, (self.total_rows + self.rows_per_page - 1) // self.rows_per_page)
        self.current_page = max(1, min(page, self.total_pages))

        start = (self.current_page - 1) * self.rows_per_page
        end = start + self.rows_per_page
        rows = all_rows[start:end]

        # Update pagination display
        self.page_label.setText(f"Page {self.current_page} / {self.total_pages}")
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)

        # ✅ Populate table
        self.table.setRowCount(len(rows))
        for i, (pid, name, age, sex, phone, tob, alc, scan, report) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(str(start + i + 1)))
            self.table.setItem(i, 1, QTableWidgetItem(str(pid)))
            self.table.setItem(i, 2, QTableWidgetItem(name or ""))
            self.table.setItem(i, 3, QTableWidgetItem(str(age or "")))
            self.table.setItem(i, 4, QTableWidgetItem(sex or ""))
            self.table.setItem(i, 5, QTableWidgetItem(phone or ""))
            self.table.setItem(i, 6, QTableWidgetItem(tob or ""))
            self.table.setItem(i, 7, QTableWidgetItem(alc or ""))

            # Determine case status
            if not scan:
                status, color, action = "Registered", QColor("#fdd835"), "Go to Scan"
            elif scan and not report:
                status, color, action = "Scan Completed", QColor("#ffb74d"), "Go to Reporting"
            else:
                status, color, action = "Signed Off", QColor("#81c784"), "View Report"

            status_item = QTableWidgetItem(status)
            status_item.setBackground(color)
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 8, status_item)

            btn = QPushButton(action)
            btn.setStyleSheet("color: #1565c0; background: transparent; font-weight: bold;")
            btn.clicked.connect(partial(self.on_action_clicked, pid, action))
            self.table.setCellWidget(i, 9, btn)

    # ---------- Pagination ----------
    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.apply_filters_with_page()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.apply_filters_with_page()

    # ---------- Actions ----------
    def on_action_clicked(self, patient_id, action):
        if not self.main_window:
            return
        if action == "Go to Scan":
            self.main_window.go_to_capture(patient_id)
        elif action == "Go to Reporting":
            self.main_window.go_to_report(patient_id)
        elif action == "View Report":
            self.main_window.go_to_view_report(patient_id)

    # ---------- Clear Filters ----------
    def clear_filters(self):
        self.select_all_checkbox.setChecked(False)
        self.pid_filter.setCurrentIndex(0)
        self.name_filter.clear()
        self.gender_filter.setCurrentIndex(0)
        self.status_filter.setCurrentIndex(0)
        self.from_date.setDate(QDate.currentDate().addDays(-30))
        self.to_date.setDate(QDate.currentDate())
        self.table.setRowCount(0)
        self.page_label.setText("Page 0 / 0")
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)

    # ---------- Select All ----------
    def on_select_all(self, state):
        if state == Qt.Checked:
            self.apply_filters_with_page()
        else:
            self.clear_filters()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CaseListStudy()
    win.show()
    sys.exit(app.exec_())
