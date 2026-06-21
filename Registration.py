import sys
import sqlite3
import random
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QLineEdit, QComboBox, QDateEdit, QRadioButton, QButtonGroup, QCheckBox
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal, QTimer, QRegularExpression
from PyQt5.QtGui import QFont, QIntValidator, QRegularExpressionValidator
from PyQt5.QtWidgets import QAbstractSpinBox

# Session import
try:
    from global_session import Session
except Exception:
    class Session:
        user_id = None
        user_name = None
        role = None


class RegistrationPage(QWidget):
    go_back = pyqtSignal()
    patient_registered = pyqtSignal(str)

    def __init__(self, db_path=None):
        super().__init__()
        self.db_path = db_path or "viscan.db"
        self.setWindowTitle("Patient Registration")
        self.setGeometry(100, 100, 1000, 600)
        self.setStyleSheet("background-color: #303F9F;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)

        # ---------------- Header ----------------
        header = QLabel("PATIENT STUDY REGISTRATION")
        header.setFont(QFont("Arial", 26, QFont.Bold))
        header.setStyleSheet("color: white;")
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)

        # ---------------- Form Card ----------------
        form_card = QFrame()
        form_card.setStyleSheet("background-color: white; border-radius: 10px;")
        form_layout = QGridLayout(form_card)
        form_layout.setContentsMargins(30, 30, 30, 30)
        form_layout.setSpacing(20)

        field_style = """
            QLineEdit, QComboBox, QDateEdit {
                background-color: #d3d3d3;
                padding: 8px 12px;
                border-radius: 15px;
                color: black;
                font: 14px 'Arial';
            }
        """
        label_style = """
            QLabel {
                color: #303F9F;
                font: 20px 'Arial';
            }
        """

        # ---------------- Fields ----------------
        self.patient_id_field = QLineEdit()
        self.patient_id_field.setReadOnly(True)
        self.first_name_field = QLineEdit()
        self.last_name_field = QLineEdit()

        # Examination Date (Today, read-only, no arrows)
        self.registration_date_field = QDateEdit()
        self.registration_date_field.setDate(QDate.currentDate())
        self.registration_date_field.setReadOnly(True)
        self.registration_date_field.lineEdit().setReadOnly(True)
        self.registration_date_field.setButtonSymbols(QAbstractSpinBox.NoButtons)


        self.gender_field = QComboBox()
        self.gender_field.addItems(["Select", "Male", "Female", "Other"])

        # Age (numbers only, max 3 digits)
        self.age_field = QLineEdit()
        self.age_field.setValidator(QIntValidator(0, 999, self))
        self.age_field.setMaxLength(3)
        self.age_field.setPlaceholderText("Enter Age (max 3 digits)")

        # Phone (exactly 10 digits, numbers only)
        self.phone_field = QLineEdit()
        phone_regex = QRegularExpression(r"\d{0,10}")  # allows 0 to 10 digits
        phone_validator = QRegularExpressionValidator(phone_regex, self)
        self.phone_field.setValidator(phone_validator)
        self.phone_field.setPlaceholderText("Enter 10-digit phone number")

        # Registered By (auto-filled)
        self.registered_by_field = QLineEdit()
        self.registered_by_field.setReadOnly(True)
        self.set_registered_by_field()

        # Quick Register checkbox
        self.quick_register_checkbox = QCheckBox("Quick Register")
        self.quick_register_checkbox.setStyleSheet("font: 14px 'Century Gothic'; color: #303F9F;")
        self.quick_register_checkbox.stateChanged.connect(self.handle_quick_register_toggle)
        form_layout.addWidget(self.quick_register_checkbox, 0, 4, 1, 2)

        # Labels and fields
        labels_fields = [
            ("Patient ID ", self.patient_id_field),
            ("First Name *", self.first_name_field),
            ("Last Name *", self.last_name_field),
            ("Registration Date ", self.registration_date_field),
            ("Gender *", self.gender_field),
            ("Age *", self.age_field),
            ("Phone no. *", self.phone_field),
            ("Registered by ", self.registered_by_field),
        ]
        positions = [(0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1), (1, 2), (1, 3)]

        for pos, (label, widget) in zip(positions, labels_fields):
            lbl = QLabel(label)
            lbl.setStyleSheet(label_style)
            form_layout.addWidget(lbl, pos[0]*2 + 1, pos[1])
            widget.setStyleSheet(field_style)
            form_layout.addWidget(widget, pos[0]*2 + 2, pos[1])

        # ---------------- Tobacco & Alcohol ----------------
        self.tobacco_group = QButtonGroup(self)
        self.alcohol_group = QButtonGroup(self)

        for i, (label_text, group) in enumerate([("Tobacco *", self.tobacco_group), ("Alcohol *", self.alcohol_group)]):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(label_style)
            form_layout.addWidget(lbl, 5, i * 2)

            yes_radio = QRadioButton("Yes")
            no_radio = QRadioButton("No")
            yes_radio.setStyleSheet("font: 14px 'Arial'; color: #303F9F;")
            no_radio.setStyleSheet("font: 14px 'Arial'; color: #303F9F;")
            no_radio.setChecked(True)

            group.addButton(yes_radio)
            group.addButton(no_radio)

            box_layout = QHBoxLayout()
            box_layout.addWidget(yes_radio)
            box_layout.addWidget(no_radio)
            form_layout.addLayout(box_layout, 6, i * 2)

        main_layout.addWidget(form_card)

        # ---------------- Submit Button ----------------
        submit_btn = QPushButton("Submit")
        submit_btn.setFixedSize(100, 40)
        submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: Black;
                font: 20px 'Arial';
                border-radius: 20px;
            }
            QPushButton:hover {
                background-color: #5C6BC0;
            }
        """)
        submit_btn.clicked.connect(self.submit_data)
        main_layout.addWidget(submit_btn, alignment=Qt.AlignCenter)

        # ---------------- Status Label ----------------
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: white; font: 18px 'Arial';")
        main_layout.addWidget(self.status_label)

        # Generate Patient ID
        self.set_patient_id()

    # ---------- Helper Functions ----------
    def set_registered_by_field(self):
        """Set 'Registered By' with the logged-in user's name, if available."""
        user_name = getattr(Session, "user_name", "")
        if user_name is None:
            user_name = ""
        self.registered_by_field.setText(user_name)

    def set_patient_id(self):
        """Auto-generate next Patient ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT Patient_id FROM Patient_Details ORDER BY Patient_id DESC LIMIT 1")
            result = cursor.fetchone()
            conn.close()
            if result and result[0].startswith("P"):
                last_id_num = int(result[0][1:])
                new_id = f"P{last_id_num + 1:03d}"
            else:
                new_id = "P001"
            self.patient_id_field.setText(new_id)
        except Exception as e:
            print("Error generating Patient ID:", e)
            self.patient_id_field.setText("P001")

    def handle_quick_register_toggle(self, state):
        if state == Qt.Checked:
            self.first_name_field.setText(f"Quick{random.randint(1000,9999)}")
            self.last_name_field.setText("Patient")
            self.age_field.setText("000")
            self.phone_field.setText("0000000000")
            self.gender_field.setCurrentText("Other")
            for group in [self.tobacco_group, self.alcohol_group]:
                for btn in group.buttons():
                    if btn.text() == "No":
                        btn.setChecked(True)
        else:
            self.clear_fields()

    def clear_fields(self):
        self.first_name_field.clear()
        self.last_name_field.clear()
        self.gender_field.setCurrentIndex(0)
        self.age_field.clear()
        self.phone_field.clear()
        self.registration_date_field.setDate(QDate.currentDate())
        for group in [self.tobacco_group, self.alcohol_group]:
            for btn in group.buttons():
                if btn.text() == "No":
                    btn.setChecked(True)
        self.set_registered_by_field()
 
    def validate_inputs(self):
        if not self.first_name_field.text().strip():
            self.status_label.setText("First Name is required.")
            return False
        if not self.last_name_field.text().strip():
            self.status_label.setText("Last Name is required.")
            return False
        if self.gender_field.currentText() == "Select":
            self.status_label.setText("Please select a gender.")
            return False
        if not self.age_field.text().isdigit():
            self.status_label.setText("Age must be a number (max 3 digits).")
            return False
        if not (self.phone_field.text().isdigit() and len(self.phone_field.text()) == 10):
            self.status_label.setText("Phone must be exactly 10 digits.")
            return False
        if not self.registered_by_field.text().strip():
            self.status_label.setText("Registered by name is missing.")
            return False
        return True

    def submit_data(self):
        if not self.validate_inputs():
            return

        patient_id = self.patient_id_field.text()
        patient_name = f"{self.first_name_field.text().strip()} {self.last_name_field.text().strip()}"
        exam_date = self.registration_date_field.date().toString("yyyy-MM-dd")
        gender = self.gender_field.currentText()
        age = self.age_field.text().strip()
        phone = self.phone_field.text().strip()
        registered_by = self.registered_by_field.text().strip()
        tobacco = "Yes" if any(btn.isChecked() and btn.text() == "Yes" for btn in self.tobacco_group.buttons()) else "No"
        alcohol = "Yes" if any(btn.isChecked() and btn.text() == "Yes" for btn in self.alcohol_group.buttons()) else "No"

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO Patient_Details 
                (Patient_id, Patient_Name, Age, Sex, Phone_no, Registration_date, Registered_by, Tobacco_Use, Alcohol_Use)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (patient_id, patient_name, age, gender, phone, exam_date, registered_by, tobacco, alcohol))
            conn.commit()
            conn.close()

            self.status_label.setText("Patient registered successfully!")
            self.status_label.setStyleSheet("color: lightgreen; font: 20px 'Arial';")
            self.patient_registered.emit(patient_id)
            self.set_patient_id()
            self.clear_fields()
            QTimer.singleShot(5000, lambda: self.status_label.setText(""))

        except Exception as e:
            print("Error inserting data:", e)
            self.status_label.setText("Failed to save patient record.")
            self.status_label.setStyleSheet("color: red; font: 14px 'Arial';")
            QTimer.singleShot(5000, lambda: self.status_label.setText(""))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    reg = RegistrationPage()
    reg.resize(1000, 700)
    reg.show()
    sys.exit(app.exec_())
