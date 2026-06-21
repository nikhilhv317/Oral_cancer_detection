import sys
import sqlite3
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction



def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base_path, relative_path))


class AddUserPage(QWidget):
    user_added = pyqtSignal()

    def __init__(self, db_path=None):
        super().__init__()
        self.db_path = db_path or resource_path("viscan.db")
        self.setWindowTitle("Add New User")
        self.setStyleSheet("font-size: 16px; background-color: #3A4ED0;")
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignCenter)

        # Form Frame
        form_frame = QFrame()
        form_frame.setFixedWidth(900)
        form_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
                padding: 30px;
            }
        """)
        form_layout = QVBoxLayout(form_frame)
        form_layout.setSpacing(20)

        yellow_input_style = """
            QLineEdit, QComboBox {
                background-color: #FFD700;
                border: none;
                border-radius: 10px;
                padding: 10px;
                font-size: 16px;
                color: #333;
            }
        """

        # ---------------- ROW 1 ----------------
        row1 = QHBoxLayout()

        self.prefix_combo = QComboBox()
        self.prefix_combo.addItems(["Select", "Dr.", "Mr.", "Mrs.", "Miss", "Ms."])
        self.prefix_combo.setStyleSheet(yellow_input_style)
        self.prefix_combo.setFixedWidth(120)

        # NAME – ONLY LETTERS
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Name")
        self.name_input.setStyleSheet(yellow_input_style)
        self.name_input.textChanged.connect(self.validate_name)

        # PHONE – ONLY DIGITS
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Phone Number")
        self.phone_input.setStyleSheet(yellow_input_style)
        self.phone_input.setMaxLength(10)
        self.phone_input.textChanged.connect(self.validate_phone)

        row1.addWidget(self.prefix_combo)
        row1.addWidget(self.name_input)
        row1.addWidget(self.phone_input)
        form_layout.addLayout(row1)

        # Email
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Email ID ")
        self.email_input.setStyleSheet(yellow_input_style)
        form_layout.addWidget(self.email_input)

        # Role
        self.role_combo = QComboBox()
        self.role_combo.addItems(["Select Role", "Doctor", "Technician", "Admin"])
        self.role_combo.setStyleSheet(yellow_input_style)
        form_layout.addWidget(self.role_combo)

        # PASSWORD WITH EYE ICON
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setStyleSheet(yellow_input_style)

        # Eye Icon Action
        self.toggle_action = QAction("👁")
        self.toggle_action.triggered.connect(self.toggle_password)
        self.password_input.addAction(self.toggle_action, QLineEdit.TrailingPosition)

        form_layout.addWidget(self.password_input)

        # Submit Button
        submit_btn = QPushButton("Add User")
        submit_btn.setFixedSize(180, 45)
        submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFD700;
                border: 2px solid black;
                border-radius: 25px;
                font-size: 20px;
                font-weight: bold;
                color: black;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #ffcc00;
            }
        """)
        submit_btn.clicked.connect(self.submit_user)
        form_layout.addWidget(submit_btn, alignment=Qt.AlignCenter)

        # Message Label
        self.message_label = QLabel("")
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet("font-size: 16px;")
        form_layout.addWidget(self.message_label)

        main_layout.addWidget(form_frame)
        self.setLayout(main_layout)

    # ---------------- VALIDATION ----------------

    def validate_name(self):
        """Allow only letters and spaces."""
        text = self.name_input.text()
        if not all(c.isalpha() or c.isspace() for c in text):
            self.name_input.setText(''.join(c for c in text if c.isalpha() or c.isspace()))

    def validate_phone(self):
        """Allow only digits."""
        text = self.phone_input.text()
        if not text.isdigit():
            self.phone_input.setText(''.join(filter(str.isdigit, text)))

    def toggle_password(self):
        """Show / Hide password"""
        if self.password_input.echoMode() == QLineEdit.Password:
            self.password_input.setEchoMode(QLineEdit.Normal)
            self.toggle_action.setText("🙈")
        else:
            self.password_input.setEchoMode(QLineEdit.Password)
            self.toggle_action.setText("👁")

    # ---------------- USER ID ----------------
    def generate_user_id(self, cursor):
        cursor.execute("SELECT user_id FROM User_M WHERE user_id LIKE 'U%' ORDER BY user_id DESC LIMIT 1")
        last_id = cursor.fetchone()
        if last_id:
            new_num = int(last_id[0][1:]) + 1
        else:
            new_num = 1
        return f"U{new_num:03d}"

    # ---------------- SUBMIT ----------------
    def submit_user(self):
        prefix = self.prefix_combo.currentText()
        name = self.name_input.text().strip()
        phone = self.phone_input.text().strip()
        email = self.email_input.text().strip().lower()
        password = self.password_input.text().strip()
        role = self.role_combo.currentText()

        self.message_label.setText("")
        self.message_label.setStyleSheet("color: red; font-size: 16px;")

        if prefix == "Select" or role == "Select Role" or not all([name, phone, email, password]):
            self.message_label.setText("⚠️ Please fill all fields.")
            return

        if len(phone) != 10:
            self.message_label.setText("⚠️ Phone number must be 10 digits.")
            return

        role_map = {"Doctor": "R1", "Technician": "R2", "Admin": "R3"}
        role_id = role_map.get(role)
        full_name = f"{prefix} {name}"

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            new_user_id = self.generate_user_id(cursor)

            cursor.execute("""
                INSERT INTO User_M (user_id, name, email, phone_no, Role_id, password, status, Active)
                VALUES (?, ?, ?, ?, ?, ?, 'approved', 1)
            """, (new_user_id, full_name, email, phone, role_id, password))

            conn.commit()
            conn.close()

            self.message_label.setStyleSheet("color: green; font-size: 16px;")
            self.message_label.setText(f"✅ User '{email}' added successfully as {new_user_id}.")

            # Clear
            self.prefix_combo.setCurrentIndex(0)
            self.name_input.clear()
            self.phone_input.clear()
            self.email_input.clear()
            self.password_input.clear()
            self.role_combo.setCurrentIndex(0)

            QTimer.singleShot(3000, self.message_label.clear)
            self.user_added.emit()

        except sqlite3.IntegrityError:
            self.message_label.setText("❌ User already exists.")
        except sqlite3.Error as e:
            self.message_label.setText(f"Database Error: {e}")


# ---------------- TEST ----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AddUserPage()
    window.resize(1000, 550)
    window.show()
    sys.exit(app.exec_())
