import sys
import sqlite3
import os
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QFrame, QLineEdit, QTextEdit, QComboBox, QScrollArea
)
from PyQt5.QtCore import Qt, QSize, QTimer, QDateTime
from PyQt5.QtGui import QPixmap, QFont, QTextCursor, QTextCharFormat
# Session import
try:
    from global_session import Session
except Exception:
    class Session:
        user_id = None
        user_name = None
        role = None

def resource_path(relative_path):
    try:
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
        full_path = os.path.normpath(os.path.join(base_path, relative_path))
        print(f"[DEBUG] Resource path: {full_path}, exists: {os.path.exists(full_path)}")
        if not os.path.exists(full_path):
            print(f"[ERROR] Resource not found: {full_path}")
        return full_path
    except Exception as e:
        print(f"[ERROR] Resource path error: {e}")
        return relative_path

def sanitize(text):
    if not text:
        return "Unknown"
    return (text.replace("&", "\\&").replace("%", "\\%").replace("$", "\\$")
            .replace("#", "\\#").replace("_", "\\_")
            .replace("{", "\\{").replace("}", "\\}").replace("~", "\\~"))

class DraggableLabel(QLabel):
    def __init__(self, image_path, parent=None, report_page=None):
        super().__init__(parent)
        self.image_path = image_path
        self.original_pixmap = None
        self.setCursor(Qt.OpenHandCursor)
        self.zoomed = False
        self.setStyleSheet("border: 2px solid transparent;")
        self.setAlignment(Qt.AlignCenter)
        self.report_page = report_page

    def set_pixmap(self, pixmap):
        self.original_pixmap = pixmap
        self.setPixmap(pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.setFixedSize(160, 160)

    def set_zoomed(self, zoomed):
        if self.original_pixmap:
            self.zoomed = zoomed
            if zoomed:
                self.setPixmap(self.original_pixmap.scaled(175, 175, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.setFixedSize(185, 185)
                QTimer.singleShot(100, lambda: self.setPixmap(self.original_pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                QTimer.singleShot(100, lambda: self.setFixedSize(210, 210))
                self.setStyleSheet("border: 2px solid #00ff00;")
            else:
                self.setPixmap(self.original_pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.setFixedSize(160, 160)
                self.setStyleSheet("border: 2px solid transparent;")
            self.parent().layout().update()
            print(f"[DEBUG] Image {self.image_path} {'zoomed' if zoomed else 'unzoomed'}")

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.report_page.move_image_to_selected(self.image_path)

class ImageThumbnail(QLabel):
    def __init__(self, pixmap, image_path, parent=None, report_page=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setPixmap(pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.setFixedSize(160, 160)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("border: 2px solid transparent;")
        self.selected = False
        self.report_page = report_page

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.report_page.move_image_back_to_images(self.image_path)

class DropArea(QWidget):
    def __init__(self, parent=None, report_page=None, cursor=None):
        super().__init__(parent)
        self.report_page = report_page
        self.cursor = cursor
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        self.layout = QGridLayout(self)
        self.layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.row = 0
        self.col = 0
        self.images = []

    def add_image(self, full_path, rel_path, pixmap):
        thumb = ImageThumbnail(pixmap, rel_path, report_page=self.report_page)
        self.layout.addWidget(thumb, self.row, self.col)
        self.images.append({"path": rel_path, "pixmap": pixmap, "widget": thumb})
        self.col = (self.col + 1) % 4
        if self.col == 0:
            self.row += 1
        print(f"[DEBUG] Added image to DropArea: {rel_path}")

    def remove_image(self, rel_path):
        for i in range(self.layout.count()):
            widget = self.layout.itemAt(i).widget()
            if isinstance(widget, ImageThumbnail) and widget.image_path == rel_path:
                widget.deleteLater()
                self.images = [img for img in self.images if img["path"] != rel_path]
                break
        self.row = (len(self.images) - 1) // 4 + 1 if self.images else 0
        self.col = len(self.images) % 4 if self.images else 0
        print(f"[DEBUG] Removed image from DropArea: {rel_path}")

    def get_all_images(self):
        return self.images

class ReportPage(QWidget):
    def __init__(self, tab_widget=None, view_report_page=None, db_path=None):
        super().__init__()

        self.setWindowTitle("Patient Report")
        self.setStyleSheet("background-color: #1a237e;")
        self.tab_widget = tab_widget
        self.view_report_page = view_report_page
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        self.db_path = db_path or resource_path("viscan.db")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.report_approved = False
        self.patient_dynamic_fields = {}
        self.ai_categories = []
        self.zoomed_images = []
        self.initial_data = {}
        self.ensure_image_capture_schema()
        self.ensure_patient_report_schema()
        self.ensure_extra_fields_schema()
        self.init_ui()

    def set_patient_id(self, patient_id: str):
        if not patient_id:
            return
        try:
            # ✅ Clear center panel (DropArea) before loading any patient
            if hasattr(self, "drop_area"):
                self.clear_layout(self.drop_area.layout)
                self.drop_area.images = []
                self.drop_area.row = 0
                self.drop_area.col = 0
                print("[INFO] Center panel cleared before loading new patient")

            self.cursor.execute("SELECT report_approved FROM Patient_Report WHERE Patient_id = ?", (patient_id,))
            result = self.cursor.fetchone()
            if result and result[0] == 1:
                self.show_status(f"Report for Patient ID {patient_id} is approved and can only be viewed in View Report.", "orange")
                print(f"[INFO] Blocked loading approved report for Patient ID: {patient_id}")
                return
            if self.patient_id_dropdown.findText(patient_id) == -1:
                self.patient_id_dropdown.addItem(patient_id)
            self.patient_id_dropdown.setCurrentText(patient_id)
            self.load_patient_data(patient_id)
            print(f"[INFO] Report page auto-populated with Patient ID: {patient_id}")
        except Exception as e:
            self.show_status(f"Error checking patient ID: {str(e)}", "red")
            print(f"[ERROR] set_patient_id: {e}")


    def ensure_image_capture_schema(self):
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS Image_Capture (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Patient_id TEXT,
                    visit_date TEXT,
                    image_path TEXT,
                    capture_time TEXT,
                    ai_label TEXT,
                    is_selected INTEGER DEFAULT 0,
                    scan_complete INTEGER DEFAULT 0,
                    FOREIGN KEY (Patient_id) REFERENCES Patient_Details(Patient_id)
                )
            """)
            self.cursor.execute("PRAGMA table_info(Image_Capture)")
            cols = [r[1] for r in self.cursor.fetchall()]
            for col, col_type, default in [
                
                ('ai_label', 'TEXT', None),
                ('visit_date', 'TEXT', None),
                ('scan_complete', 'INTEGER', '0')
            ]:
                if col not in cols:
                    self.cursor.execute(f"ALTER TABLE Image_Capture ADD COLUMN {col} {col_type}" +
                                       (f" DEFAULT {default}" if default is not None else ""))
            self.conn.commit()
            print("[INFO] Image_Capture schema verified")
        except Exception as e:
            print(f"[ERROR] ensure_image_capture_schema: {e}")
            self.show_status(f"Error setting up Image_Capture table: {str(e)}", "red")

    def ensure_patient_report_schema(self):
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS Patient_Report (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Patient_id TEXT,
                    Patient_Name TEXT,
                    Overall_findings TEXT,
                    Find_impression TEXT,
                    Performed_by TEXT,
                    Doctor_name TEXT,
                    Visit_date DATE,
                    report_approved INTEGER DEFAULT 0,
                    FOREIGN KEY (Patient_id) REFERENCES Patient_Details(Patient_id)
                )
            """)
            # Ensure new columns exist if old DB already present
            self.cursor.execute("PRAGMA table_info(Patient_Report)")
            cols = [r[1] for r in self.cursor.fetchall()]
            for col, col_type, default in [
                ('Patient_Name', 'TEXT', None),
                ('Performed_by', 'TEXT', None),
                ('Doctor_name', 'TEXT', None),
                ('Visit_date', 'DATE', None),
                ('report_approved', 'INTEGER', '0')
            ]:
                if col not in cols:
                    self.cursor.execute(
                        f"ALTER TABLE Patient_Report ADD COLUMN {col} {col_type}" +
                        (f" DEFAULT {default}" if default is not None else "")
                    )
                    print(f"[INFO] Added column {col} to Patient_Report")
            self.conn.commit()
            print("[INFO] Patient_Report schema verified")
        except Exception as e:
            print(f"[ERROR] ensure_patient_report_schema: {e}")
            self.show_status(f"Error setting up Patient_Report table: {str(e)}", "red")

    def ensure_extra_fields_schema(self):
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS Patient_ExtraFields (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Patient_id TEXT,
                    Field_name TEXT,
                    Field_value TEXT,
                    FOREIGN KEY (Patient_id) REFERENCES Patient_Details(Patient_id)
                )
            """)
            self.conn.commit()
            print("[INFO] Patient_ExtraFields schema verified")
        except Exception as e:
            print(f"[ERROR] ensure_extra_fields_schema: {e}")
            self.show_status(f"Error setting up Patient_ExtraFields table: {str(e)}", "red")

    def init_ui(self):
        self.patient_dynamic_fields = {}
        main_layout = QVBoxLayout()

        # ===================== TOP SECTION =====================
        top_frame = QFrame()
        top_frame.setStyleSheet("background-color: #1a237e; border-radius: 10px;")
        top_layout = QGridLayout(top_frame)
        top_layout.setAlignment(Qt.AlignLeft)

        patient_id_label = QLabel("Patient ID:")
        patient_id_label.setStyleSheet("color: white; font-weight: bold;")
        self.patient_id_dropdown = QComboBox()
        self.patient_id_dropdown.setEditable(True)
        self.patient_id_dropdown.setFixedWidth(200)
        self.patient_id_dropdown.setStyleSheet("""
            QComboBox { background-color: white; color: black; border: 1px solid gray; border-radius: 4px; padding: 4px; }
            QComboBox::drop-down { background-color: white; border-left: 1px solid gray; }
            QComboBox QAbstractItemView { background-color: white; color: black; selection-background-color: #1a237e; selection-color: white; }
        """)
        self.patient_id_dropdown.currentTextChanged.connect(
            lambda text: self.load_patient_data(text)
        )

        name_label = QLabel("Name:")
        name_label.setStyleSheet("color: white; font-weight: bold;")
        self.name_input = QLineEdit()
        self.name_input.setReadOnly(True)
        self.name_input.setFixedWidth(180)

        self.age_label = QLabel("Age/Sex:")
        self.age_label.setStyleSheet("color: white; font-weight: bold;")
        self.age_input = QLineEdit()
        self.age_input.setReadOnly(True)
        self.age_input.setFixedWidth(180)

        date_label = QLabel("Date:")
        date_label.setStyleSheet("color: white; font-weight: bold;")
        self.date_input = QLineEdit()
        self.date_input.setReadOnly(True)
        self.date_input.setFixedWidth(180)

        for field in [self.name_input, self.age_input, self.date_input]:
            field.setStyleSheet("background-color: #808080; color: white; border: 1px solid #808080; border-radius: 4px; padding: 4px;")

        top_layout.addWidget(patient_id_label, 0, 0, Qt.AlignLeft)
        top_layout.addWidget(self.patient_id_dropdown, 0, 1, Qt.AlignLeft)
        top_layout.addWidget(name_label, 0, 2, Qt.AlignLeft)
        top_layout.addWidget(self.name_input, 0, 3, Qt.AlignLeft)
        top_layout.addWidget(self.age_label, 1, 0, Qt.AlignLeft)
        top_layout.addWidget(self.age_input, 1, 1, Qt.AlignLeft)
        top_layout.addWidget(date_label, 1, 2, Qt.AlignLeft)
        top_layout.addWidget(self.date_input, 1, 3, Qt.AlignLeft)

        # ===================== MIDDLE SECTION =====================
        middle_layout = QHBoxLayout()

        # -------- LEFT PANEL --------
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)

        ai_prediction_label = QLabel("AI Prediction")
        ai_prediction_label.setFont(QFont("Arial", 16, QFont.Bold))
        left_panel.addWidget(ai_prediction_label)

        self.ai_prediction_text = QTextEdit()
        self.ai_prediction_text.setPlaceholderText("AI Prediction categories...")
        self.ai_prediction_text.setReadOnly(True)
        self.ai_prediction_text.setFixedHeight(100)
        self.ai_prediction_text.setStyleSheet("background-color: white; color: black; border: 1px solid #1a237e; border-radius: 4px;")
        self.ai_prediction_text.setText("Select a patient to view predictions...")
        self.ai_prediction_text.mousePressEvent = self.handle_ai_prediction_click
        left_panel.addWidget(self.ai_prediction_text)

        findings_label = QLabel("Overall Findings")
        findings_label.setFont(QFont("Arial", 16, QFont.Bold))
        left_panel.addWidget(findings_label)

        self.findings_text = QTextEdit()
        self.findings_text.setPlaceholderText("Enter findings here...")
        self.findings_text.setReadOnly(False)
        self.findings_text.setStyleSheet("background-color: white; color: black; border: 1px solid #1a237e; border-radius: 4px;")
        self.findings_text.textChanged.connect(self.check_for_changes)
        left_panel.addWidget(self.findings_text)

        impression_label = QLabel("Impression")
        impression_label.setFont(QFont("Arial", 16, QFont.Bold))
        left_panel.addWidget(impression_label)

        self.impression_text = QTextEdit()
        self.impression_text.setPlaceholderText("Enter impression here...")
        self.impression_text.setReadOnly(False)
        self.impression_text.setStyleSheet("background-color: white; color: black; border: 1px solid #1a237e; border-radius: 4px;")
        self.impression_text.textChanged.connect(self.check_for_changes)
        left_panel.addWidget(self.impression_text)

        # ----- Add Dynamic Fields -----
        add_field_title = QLabel("Add Field")
        add_field_title.setFont(QFont("Arial", 12, QFont.Bold))
        left_panel.addWidget(add_field_title)

        add_field_layout = QHBoxLayout()
        self.new_field_name_input = QLineEdit()
        self.new_field_name_input.setPlaceholderText("Field Name")
        self.new_field_name_input.setMinimumWidth(120)
        self.new_field_content_input = QLineEdit()
        self.new_field_content_input.setPlaceholderText("Field Content")
        self.new_field_content_input.setMinimumWidth(200)
        self.add_field_button = QPushButton("Add")
        self.add_field_button.setFixedHeight(30)
        self.add_field_button.setStyleSheet("""
            QPushButton { background-color: #1a237e; color: white; border-radius: 6px; padding: 5px 15px; }
            QPushButton:hover { background-color: #3949ab; }
        """)
        self.add_field_button.clicked.connect(self.add_dynamic_field)

        add_field_layout.addWidget(self.new_field_name_input)
        add_field_layout.addWidget(self.new_field_content_input)
        add_field_layout.addWidget(self.add_field_button)
        left_panel.addLayout(add_field_layout)

        self.dynamic_fields_layout = QVBoxLayout()
        left_panel.addLayout(self.dynamic_fields_layout)

        # ----- Doctor & Performed By -----
        bottom_inputs_layout = QHBoxLayout()

        # Doctor (Reported By)
        doctor_label = QLabel("Doctor :")
        doctor_label.setFont(QFont("Arial", 10, QFont.Bold))
        doctor_label.setStyleSheet("color: black;")

        self.doctor_input = QLineEdit()
        self.doctor_input.setFixedWidth(200)
        self.doctor_input.setReadOnly(True)
        self.doctor_input.setStyleSheet("background-color: #d3d3d3; color: black; border-radius: 4px; padding: 4px;")

        # Auto-fill doctor name only if a doctor logs in
        if Session.role == "DOCTOR":
            self.doctor_input.setText(Session.user_name)
        else:
            self.doctor_input.setText("")

        # Performed By
        performed_by_label = QLabel("Performed By:")
        performed_by_label.setFont(QFont("Arial", 10, QFont.Bold))
        performed_by_label.setStyleSheet("color: black;")

        self.performed_by_input = QLineEdit()
        self.performed_by_input.setFixedWidth(200)
        self.performed_by_input.setReadOnly(True)
        self.performed_by_input.setStyleSheet("background-color: #d3d3d3; color: black; border-radius: 4px; padding: 4px;")

        # Add to layout
        bottom_inputs_layout.addWidget(doctor_label)
        bottom_inputs_layout.addWidget(self.doctor_input)
        bottom_inputs_layout.addSpacing(30)
        bottom_inputs_layout.addWidget(performed_by_label)
        bottom_inputs_layout.addWidget(self.performed_by_input)

        left_panel.addLayout(bottom_inputs_layout)

        self.left_container = QFrame()
        self.left_container.setLayout(left_panel)
        self.left_container.setFrameShape(QFrame.StyledPanel)
        self.left_container.setStyleSheet("background-color: white; border: 2px solid #1a237e; border-radius: 8px;")

        # -------- CENTER PANEL --------
        center_layout = QVBoxLayout()
        selected_images_title = QLabel("Selected Images")
        selected_images_title.setFont(QFont("Arial", 10, QFont.Bold))
        selected_images_title.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(selected_images_title)

        self.drop_area = DropArea(parent=self, report_page=self, cursor=self.cursor)
        self.drop_area.setStyleSheet("background-color: white; border: 2px dashed #1a237e; border-radius: 8px;")
        self.drop_area.setMinimumWidth(500)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.drop_area)
        center_layout.addWidget(scroll_area)

        center_container = QFrame()
        center_container.setLayout(center_layout)
        center_container.setFrameShape(QFrame.StyledPanel)
        center_container.setStyleSheet("background-color: white; border: 2px solid #1a237e; border-radius: 8px;")

        # -------- RIGHT PANEL --------
        right_panel = QVBoxLayout()
        images_title = QLabel("Images")
        images_title.setFont(QFont("Arial", 10, QFont.Bold))
        images_title.setAlignment(Qt.AlignCenter)
        right_panel.addWidget(images_title)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFixedWidth(600)

        self.image_list_widget = QWidget()
        self.image_list_layout = QGridLayout(self.image_list_widget)
        self.image_list_layout.setContentsMargins(10, 10, 10, 10)
        self.image_list_layout.setSpacing(10)
        self.scroll_area.setWidget(self.image_list_widget)
        right_panel.addWidget(self.scroll_area)

        right_container = QFrame()
        right_container.setLayout(right_panel)
        right_container.setFrameShape(QFrame.StyledPanel)
        right_container.setStyleSheet("background-color: white; border: 2px solid #1a237e; border-radius: 8px;")

        middle_layout.addWidget(self.left_container, 2)
        middle_layout.addWidget(center_container, 2)
        middle_layout.addWidget(right_container, 2)

        # ===================== BOTTOM BUTTONS =====================
        bottom_button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.approve_button = QPushButton("Approve Report")
        # Start both disabled
        self.save_button.setEnabled(False)
        self.approve_button.setEnabled(False)
        bottom_button_layout.addWidget(self.save_button)
        bottom_button_layout.addWidget(self.approve_button)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: yellow; font-weight: bold; padding: 5px;")

        # ===================== MAIN LAYOUT ASSEMBLY =====================
        main_layout.addWidget(top_frame)
        main_layout.addLayout(middle_layout)
        main_layout.addLayout(bottom_button_layout)
        main_layout.addWidget(self.status_label)

        self.setLayout(main_layout)
        self.setMinimumSize(1200, 800)

        self.load_patient_ids()
        self.save_button.clicked.connect(self.save_report_data)
        self.approve_button.clicked.connect(self.approve_report)
        self.update_button_styles()

    def update_button_styles(self):
        disabled_style = """
            QPushButton {
                background-color: #808080;
                color: white;
                padding: 8px 20px;
                border: 2px solid white;
                border-radius: 4px;
            }
        """
        enabled_style = """
            QPushButton {
                background-color: #1a237e;
                color: white;
                padding: 8px 20px;
                border: 2px solid white;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3949ab;
            }
        """
        approved_style = """
            QPushButton {
                background-color: #4caf50;
                color: white;
                padding: 8px 20px;
                border: 2px solid white;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #66bb6a;
            }
        """
        if self.save_button.isEnabled():
            if self.report_approved:
                self.save_button.setStyleSheet(approved_style)
            else:
                self.save_button.setStyleSheet(enabled_style)
        else:
            self.save_button.setStyleSheet(disabled_style)

        if self.approve_button.isEnabled():
            self.approve_button.setStyleSheet(enabled_style)
        else:
            self.approve_button.setStyleSheet(disabled_style)
        print("[DEBUG] Updated button styles")

    def show_status(self, message, color="yellow", duration=3000):
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold; padding: 5px;")
        if duration > 0:
            QTimer.singleShot(duration, lambda: self.status_label.setText(""))
        print(f"[INFO] Status: {message}")

    def load_patient_details(self, patient_id):
        if not patient_id:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT examined_by FROM Patient_Details WHERE patient_id = ?", (patient_id,))
            result = cursor.fetchone()
            if result and result[0]:
                print("Examined by from DB:", result[0])
                self.doctor_input.setText(result[0])
            else:
                self.doctor_input.setText("")

            # Set Performed By depending on logged-in user role
            if Session.role == "TECHNICIAN":
                self.performed_by_input.setText(Session.user_name)
                self.doctor_input.setText("Select Doctor")
            elif Session.role == "DOCTOR":
                self.doctor_input.setText(Session.user_name)
                self.performed_by_input.setText(Session.user_name)

            print("Performed by set to:", self.performed_by_input.text())
        except Exception as e:
            print("Error loading patient details:", e)
        finally:
            conn.close()

    def load_patient_ids(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT ic.Patient_id
                FROM Image_Capture ic
                LEFT JOIN Patient_Report pr ON ic.Patient_id = pr.Patient_id
                WHERE ic.scan_complete = 1
                AND (pr.report_approved IS NULL OR pr.report_approved = 0)
                ORDER BY ic.Patient_id
            """)
            patient_ids = [row[0] for row in cursor.fetchall()]
            print(f"[INFO] Loaded patient IDs with scan_complete = 1 and report not approved: {patient_ids}")
            self.patient_id_dropdown.clear()
            self.patient_id_dropdown.addItem("Select")
            if patient_ids:
                self.patient_id_dropdown.addItems(patient_ids)
                self.show_status(f"Loaded {len(patient_ids)} patient(s) with completed scans and unapproved reports.", "lightgreen")
            else:
                self.show_status("No patients with completed scans and unapproved reports found.", "yellow")
                print("[WARN] No patient IDs found with scan_complete = 1 and report_approved = 0 or NULL.")
            conn.close()
        except Exception as e:
            print(f"[ERROR] load_patient_ids: {e}")
            self.show_status(f"Error loading patient IDs: {str(e)}", "red")

    def check_for_changes(self):
        pid = self.patient_id_dropdown.currentText()
        if not pid or pid == "Select":
            self.save_button.setEnabled(False)
            self.approve_button.setEnabled(False)
            self.show_status("Please select a patient.", "yellow")
            self.update_button_styles()
            return

        try:
            current_findings = self.findings_text.toPlainText().strip()
            current_impression = self.impression_text.toPlainText().strip()
            selected_images = len(self.drop_area.get_all_images())

            # Enable Save only if findings, impression, and at least one image are present
            if current_findings and current_impression and selected_images > 0:
                self.save_button.setEnabled(True)
                self.approve_button.setEnabled(False)
                self.show_status("✅ Save enabled. Approve will be available after saving.", "lightgreen")
            else:
                self.save_button.setEnabled(False)
                self.approve_button.setEnabled(True)
                missing = []
                if not current_findings:
                    missing.append("Overall Findings")
                if not current_impression:
                    missing.append("Impression")
                if selected_images == 0:
                    missing.append("at least one image")
                self.show_status(f"Please provide {', '.join(missing)}.", "orange")

            self.update_button_styles()

        except Exception as e:
            print(f"[ERROR] check_for_changes: {e}")
            self.save_button.setEnabled(False)
            self.approve_button.setEnabled(False)
            self.show_status("Error checking changes.", "red")
            self.update_button_styles()


    def approve_report(self):
        try:
            patient_id = self.patient_id_dropdown.currentText().strip()
            if not patient_id or patient_id == "Select":
                self.show_status("Please select a valid Patient ID.", "red")
                return

            # Ensure at least one image is selected for the report
            self.cursor.execute("""
                SELECT COUNT(*) FROM Image_Capture
                WHERE Patient_id = ? AND is_selected = 1
            """, (patient_id,))
            image_count = self.cursor.fetchone()[0]

            if image_count == 0:
                self.show_status("⚠️ Please select at least one image before approving the report.", "orange")
                print(f"[WARN] No images selected for Patient_id={patient_id}. Approval blocked.")
                return

            # Validate required fields
            findings = self.findings_text.toPlainText().strip()
            impression = self.impression_text.toPlainText().strip()
            doctor = self.doctor_input.text().strip()
            performed_by = self.performed_by_input.text().strip()
            patient_name = self.name_input.text().strip()
            visit_date = datetime.now().strftime("%Y-%m-%d")

            if not findings or not impression:
                self.show_status("Please fill in both Findings and Impression before approving.", "orange")
                print(f"[WARN] Approval blocked: Missing findings/impression for Patient_id={patient_id}.")
                return

            # Approve report in DB
            self.cursor.execute("""
                UPDATE Patient_Report
                SET report_approved = 1,
                    Patient_Name = ?,
                    Overall_findings = ?,
                    Find_impression = ?,
                    Doctor_name = ?,
                    Performed_by = ?,
                    Visit_date = ?
                WHERE Patient_id = ?
            """, (
                patient_name,
                findings,
                impression,
                doctor,
                performed_by,
                visit_date,
                patient_id
            ))

          
           
            self.conn.commit()
            self.report_approved = True

            # Reload patient list (so approved one disappears)
            self.load_patient_ids()

            # Fully clear all UI fields
            self.clear_all_inputs()

            # Explicitly clear dynamic states
            self.patient_dynamic_fields.clear()
            self.ai_categories.clear()
            self.zoomed_images.clear()
            self.initial_data.clear()
            self.report_approved = False

            # Reset dropdown selection to “Select”
            if self.patient_id_dropdown.count() > 0:
                self.patient_id_dropdown.setCurrentIndex(0)

            # Reset buttons
            self.save_button.setEnabled(False)
            self.approve_button.setEnabled(False)
            self.update_button_styles()

            # Success message
            self.show_status("✅ Report approved successfully and form reset.", "green")
            print(f"[SUCCESS] Report approved and cleared for Patient_id={patient_id}")

            # Notify View Report Page (if linked)
            if self.view_report_page is not None:
                try:
                    self.view_report_page.set_patient_id(patient_id)
                    print(f"[INFO] ViewReportPage refreshed for {patient_id}")
                except Exception as e:
                    print(f"[WARN] Could not update ViewReportPage: {e}")

        except Exception as e:
            self.show_status(f"❌ Failed to approve report: {str(e)}", "red")
            print(f"[ERROR] approve_report: {e}")

    def handle_new_patient(self, patient_id):
        if patient_id:
            try:
                self.cursor.execute("SELECT report_approved FROM Patient_Report WHERE Patient_id = ?", (patient_id,))
                result = self.cursor.fetchone()
                if result and result[0] == 1:
                    self.show_status(f"Report for Patient ID {patient_id} is approved and can only be viewed in View Report.", "orange")
                    print(f"[INFO] Blocked loading approved report for Patient ID: {patient_id}")
                    return
                self.patient_id_dropdown.setCurrentText(patient_id)
                self.load_patient_data()
            except Exception as e:
                self.show_status(f"Error handling new patient: {str(e)}", "red")
                print(f"[ERROR] handle_new_patient: {e}")

    def on_patient_selected(self, patient_id):
        self.load_patient_details(patient_id)
        self.set_performed_by()

    def set_performed_by(self):
        if Session.role == "TECHNICIAN":
            self.performed_by_input.setText(Session.user_name)
            self.doctor_input.setText("Select Doctor")
        elif Session.role == "DOCTOR":
            self.doctor_input.setText(Session.user_name)
            self.performed_by_input.setText(Session.user_name)

    def load_patient_data(self, patient_id: str = None):
        pid = patient_id or self.patient_id_dropdown.currentText()

        # Restrict technicians
        if Session.role == "TECHNICIAN":
            self.show_status("Technicians cannot access the report page.", "red")
            print(f"[ACCESS DENIED] Technician tried to access ReportPage for Patient ID: {pid}")
            self.clear_all_inputs()
            return

        # Handle invalid selection
        if pid == "Select" or not pid:
            self.show_status("Please select a patient.", "yellow")
            self.approve_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.update_button_styles()
            return

        try:
            # Check if already approved
            self.cursor.execute("SELECT report_approved FROM Patient_Report WHERE Patient_id = ?", (pid,))
            result = self.cursor.fetchone()
            if result and result[0] == 1:
                self.show_status(f"Report for Patient ID {pid} is approved and can only be viewed in View Report.", "orange")
                print(f"[INFO] Approved report blocked for Patient ID: {pid}")
                self.approve_button.setEnabled(False)
                self.clear_all_inputs()
                return

            self.report_approved = False

            # Load Patient Details
            self.cursor.execute("SELECT Patient_name, Age, Sex FROM Patient_Details WHERE Patient_id = ?", (pid,))
            patient = self.cursor.fetchone()
            if patient:
                name, age, sex = patient
                self.name_input.setText(name or "")
                self.age_input.setText(f"{sex} ({age})" if age and sex else sex or "")
            else:
                self.show_status(f"Patient {pid} not found in Patient_Details.", "orange")
                return

            # Load Report Details (if any)
            self.cursor.execute("""
                SELECT Overall_findings, Find_impression, Doctor_name, Performed_by, Visit_date
                FROM Patient_Report WHERE Patient_id = ?
            """, (pid,))
            report = self.cursor.fetchone()

            if report:
                findings, impression, doctor_name, performed_by, visit_date = report
                self.findings_text.setText(findings or "")
                self.impression_text.setText(impression or "")
                self.doctor_input.setText(Session.user_name if Session.role == "DOCTOR" else (doctor_name or ""))
                self.performed_by_input.setText(performed_by or "")
                self.date_input.setText(visit_date or datetime.today().strftime("%Y-%m-%d"))
            else:
                # No report found → fresh entry
                self.findings_text.clear()
                self.impression_text.clear()
                self.date_input.setText(datetime.today().strftime("%Y-%m-%d"))
                if Session.role == "DOCTOR":
                    self.doctor_input.setText(Session.user_name)
                    self.performed_by_input.setText(Session.user_name)
                elif Session.role == "TECHNICIAN":
                    self.performed_by_input.setText(Session.user_name)
                    self.doctor_input.setText("Select Doctor")
                else:
                    self.doctor_input.setText("Select Doctor")
                    self.performed_by_input.setText("")

            # Load Dynamic Fields
            self.cursor.execute("SELECT Field_name, Field_value FROM Patient_ExtraFields WHERE Patient_id = ?", (pid,))
            extra_fields = self.cursor.fetchall()
            self.patient_dynamic_fields[pid] = [(row[0], row[1]) for row in extra_fields]

            self.clear_layout(self.dynamic_fields_layout)
            for field_name, field_value in self.patient_dynamic_fields.get(pid, []):
                row_layout = QHBoxLayout()
                field_label = QLabel(f"{field_name}:")
                field_label.setStyleSheet("font-weight: bold; color: #1a237e;")
                field_value_label = QLabel(str(field_value))
                field_value_label.setStyleSheet("color: black;")
                row_layout.addWidget(field_label)
                row_layout.addWidget(field_value_label)
                row_layout.addStretch()
                container = QFrame()
                container.setLayout(row_layout)
                self.dynamic_fields_layout.addWidget(container)

            # Load AI predictions
            self.cursor.execute("""
                SELECT DISTINCT ai_label FROM Image_Capture
                WHERE Patient_id = ? AND ai_label IS NOT NULL ORDER BY ai_label
            """, (pid,))
            ai_labels = [row[0] for row in self.cursor.fetchall()]
            self.ai_categories = [f"{i+1}. {label}" for i, label in enumerate(ai_labels)] if ai_labels else ["No predictions available"]
            self.ai_prediction_text.setText("\n".join(self.ai_categories))
            self.make_categories_clickable()

            # 🧹 Clear all existing image displays (center + right)
            self.clear_all_images()

            # 🧩 Reset all previously selected images so the center starts empty
            self.cursor.execute("""
                UPDATE Image_Capture
                SET is_selected = 0
                WHERE Patient_id = ?
            """, (pid,))
            self.conn.commit()
            print(f"[INFO] Cleared all selected images for Patient ID: {pid}")

            # ✅ Right Panel → show all captured images (scan_complete = 1)
            self.cursor.execute("""
                SELECT DISTINCT image_path 
                FROM Image_Capture 
                WHERE Patient_id = ? AND scan_complete = 1 
                ORDER BY capture_time ASC
            """, (pid,))
            all_images = [row[0] for row in self.cursor.fetchall()]
            print(f"[DEBUG] All captured images for {pid}: {all_images}")

            for idx, img_path in enumerate(all_images):
                full_path = os.path.normpath(os.path.join(self.project_root, img_path))
                if not os.path.exists(full_path):
                    print(f"[ERROR] Missing image: {full_path}")
                    continue
                pixmap = QPixmap(full_path)
                if pixmap.isNull():
                    continue
                pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                label = DraggableLabel(img_path, report_page=self)
                label.set_pixmap(pixmap)
                self.image_list_layout.addWidget(label, idx // 3, idx % 3)

            # ✅ Center Panel → remains empty on patient load
            print(f"[INFO] Center panel is empty for {pid} until manual image selection.")

            # Disable approve until saved
            self.check_for_changes()
            self.update_button_styles()
            self.show_status(f"Loaded data for Patient ID: {pid}", "lightgreen")
            print(f"[INFO] Loaded data for Patient_id={pid}")

        except Exception as e:
            self.show_status(f"Error loading patient data: {str(e)}", "red")
            print(f"[ERROR] load_patient_data: {e}")
            self.update_ui_for_role()



    def clear_layout(self, layout):
        try:
            if layout is None:
                return
            while layout.count():
                item = layout.takeAt(0)
                if item is None:
                    continue
                widget = item.widget()
                child_layout = item.layout()
                if widget is not None:
                    widget.deleteLater()
                elif child_layout is not None:
                    self.clear_layout(child_layout)
        except Exception as e:
            print(f"[ERROR] clear_layout: {e}")

    def clear_all_images(self):
        try:
            for zoomed_image in self.zoomed_images:
                try:
                    zoomed_image.set_zoomed(False)
                except RuntimeError:
                    print(f"[DEBUG] Skipped deleted widget in zoomed_images")
            self.zoomed_images.clear()
            print(f"[DEBUG] Cleared zoomed_images list")
            if hasattr(self, "image_list_layout") and self.image_list_layout is not None:
                self.clear_layout(self.image_list_layout)
            if hasattr(self, "drop_area") and getattr(self.drop_area, "layout", None) is not None:
                self.clear_layout(self.drop_area.layout)
                self.drop_area.images = []
                self.drop_area.row = 0
                self.drop_area.col = 0
            print(f"[DEBUG] Cleared all images from layouts")
        except Exception as e:
            print(f"[ERROR] clear_all_images: {e}")

    def make_categories_clickable(self):
        cursor = self.ai_prediction_text.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.setCharFormat(QTextCharFormat())
        for category in self.ai_categories:
            pos = self.ai_prediction_text.toPlainText().find(category)
            if pos != -1:
                cursor.setPosition(pos)
                cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(category))
                char_format = QTextCharFormat()
                char_format.setForeground(Qt.blue)
                char_format.setFontUnderline(True)
                cursor.setCharFormat(char_format)
        print("[DEBUG] Made AI prediction categories clickable")

    def clear_all_inputs(self):
        try:
            self.patient_id_dropdown.setCurrentIndex(0)
            self.name_input.clear()
            self.age_input.clear()
            self.date_input.clear()
            self.ai_prediction_text.clear()
            self.findings_text.clear()
            self.impression_text.clear()
            self.doctor_input.clear()
            self.performed_by_input.clear()
            self.clear_layout(self.dynamic_fields_layout)
            self.clear_all_images()
            print("[INFO] Report Page inputs cleared successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to clear inputs: {e}")

    def handle_ai_prediction_click(self, event):
        cursor = self.ai_prediction_text.cursorForPosition(event.pos())
        cursor.select(QTextCursor.LineUnderCursor)
        selected_text = cursor.selectedText()
        patient_id = self.patient_id_dropdown.currentText()
        if not patient_id or patient_id == "Select":
            self.show_status("Select a patient.", "orange")
            print("[ERROR] handle_ai_prediction_click: No patient selected")
            return
        for category in self.ai_categories:
            category_name = category.split(". ")[1] if ". " in category else category
            if category_name in selected_text:
                try:
                    self.cursor.execute("""
                        SELECT image_path
                        FROM Image_Capture
                        WHERE Patient_id = ? AND ai_label = ?
                        ORDER BY capture_time DESC
                    """, (patient_id, category_name))
                    results = self.cursor.fetchall()
                    if not results:
                        self.show_status(f"No images for {category_name}.", "orange")
                        print(f"[INFO] No images for {category_name}")
                        return
                    valid_zoomed_images = []
                    for zoomed_image in self.zoomed_images:
                        try:
                            zoomed_image.set_zoomed(False)
                            valid_zoomed_images.append(zoomed_image)
                        except RuntimeError:
                            print(f"[DEBUG] Skipped deleted widget in zoomed_images during unzoom")
                    self.zoomed_images = valid_zoomed_images
                    print(f"[DEBUG] Cleared invalid zoomed_images, remaining: {len(self.zoomed_images)}")
                    image_paths = [row[0] for row in results]
                    found_images = 0
                    for i in range(self.image_list_layout.count()):
                        widget = self.image_list_layout.itemAt(i).widget()
                        if isinstance(widget, DraggableLabel) and widget.image_path in image_paths:
                            try:
                                widget.set_zoomed(True)
                                self.zoomed_images.append(widget)
                                found_images += 1
                                print(f"[DEBUG] Zoomed image: {widget.image_path}")
                            except RuntimeError:
                                print(f"[DEBUG] Skipped deleted widget during zoom: {widget.image_path}")
                    if found_images == 0:
                        self.show_status(f"No images for {category_name} found in list.", "orange")
                        print(f"[WARN] No images found in list for {category_name}")
                    else:
                        self.show_status(f"Zoomed {found_images} image(s) for {category_name}.", "lightgreen")
                        print(f"[INFO] Zoomed {found_images} images for {category_name}: {image_paths}")
                except Exception as e:
                    self.show_status(f"Error zooming images: {str(e)}", "red")
                    print(f"[ERROR] handle_ai_prediction_click: {e}")
                break
        super(QTextEdit, self.ai_prediction_text).mousePressEvent(event)

    def add_dynamic_field(self):
        pid = self.patient_id_dropdown.currentText()
        if not pid or pid == "Select":
            self.show_status("Select a patient before adding fields.", "orange")
            print("[ERROR] add_dynamic_field: No patient selected")
            return
        field_name = self.new_field_name_input.text().strip()
        field_content = self.new_field_content_input.text().strip()
        if not field_name:
            self.show_status("Field name is required.", "orange")
            print("[ERROR] add_dynamic_field: Field name missing")
            return
        if pid not in self.patient_dynamic_fields:
            self.patient_dynamic_fields[pid] = []
        self.patient_dynamic_fields[pid].append((field_name, field_content))
        row_layout = QHBoxLayout()
        field_label = QLabel(f"{field_name}:")
        field_label.setStyleSheet("font-weight: bold; color: #1a237e;")
        field_value = QLabel(field_content)
        field_value.setStyleSheet("color: black;")
        row_layout.addWidget(field_label)
        row_layout.addWidget(field_value)
        row_layout.addStretch()
        container = QFrame()
        container.setLayout(row_layout)
        self.dynamic_fields_layout.addWidget(container)
        self.new_field_name_input.clear()
        self.new_field_content_input.clear()
        self.show_status(f"Added field '{field_name}'.", "lightgreen")
        print(f"[INFO] Added field for Patient_id={pid}: {field_name} = {field_content}")
        # New dynamic field means changes -> require save again
        self.check_for_changes()

    def save_report_data(self):
        pid = self.patient_id_dropdown.currentText().strip()
        if not pid or pid == "Select":
            self.show_status("No patient selected.", "orange")
            print("[ERROR] save_report_data: No patient selected")
            return

        findings = self.findings_text.toPlainText().strip()
        impression = self.impression_text.toPlainText().strip()
        doctor = self.doctor_input.text().strip()
        performed_by = self.performed_by_input.text().strip()
        patient_name = self.name_input.text().strip()
        visit_date = datetime.now().strftime("%Y-%m-%d")

        # Require at least findings & impression (or dynamic fields)
        if not (findings and impression) and (
            pid not in self.patient_dynamic_fields or not self.patient_dynamic_fields[pid]
        ):
            self.show_status("Please enter Overall Findings and Impression (or add fields) before saving.", "yellow")
            print("[INFO] No sufficient data entered to save.")
            return

        try:
            # Check if Patient_Report already exists
            self.cursor.execute("SELECT COUNT(*) FROM Patient_Report WHERE Patient_id = ?", (pid,))
            exists = self.cursor.fetchone()[0]

            if exists:
                # Update existing report
                self.cursor.execute("""
                    UPDATE Patient_Report
                    SET Patient_Name = ?,
                        Overall_findings = ?,
                        Find_impression = ?,
                        Doctor_name = ?,
                        Performed_by = ?,
                        Visit_date = ?,
                        report_approved = 0
                    WHERE Patient_id = ?
                """, (patient_name, findings, impression, doctor, performed_by, visit_date, pid))
                print(f"[INFO] Updated existing Patient_Report for {pid}")
            else:
                # Insert new report
                self.cursor.execute("""
                    INSERT INTO Patient_Report
                    (Patient_id, Patient_Name, Overall_findings, Find_impression, Doctor_name, Performed_by, Visit_date, report_approved)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """, (pid, patient_name, findings, impression, doctor, performed_by, visit_date))
                print(f"[INFO] Inserted new Patient_Report for {pid}")

            # Update Patient_ExtraFields
            self.cursor.execute("DELETE FROM Patient_ExtraFields WHERE Patient_id = ?", (pid,))
            if pid in self.patient_dynamic_fields:
                for field_name, field_value in self.patient_dynamic_fields[pid]:
                    self.cursor.execute("""
                        INSERT INTO Patient_ExtraFields (Patient_id, Field_name, Field_value)
                        VALUES (?, ?, ?)
                    """, (pid, field_name, field_value))
                print(f"[INFO] Updated extra fields for {pid}")

            # Update Image_Capture: keep only selected images (is_selected = 1)
          # 🔧 Reset all images first
            self.cursor.execute("""
                UPDATE Image_Capture
                SET is_selected = 0
                WHERE Patient_id = ?
            """, (pid,))

            # 🔧 Mark ONLY center panel images as selected
            selected_images = self.drop_area.get_all_images()
            for image in selected_images:
                rel_path = image.get("path")
                self.cursor.execute("""
                    UPDATE Image_Capture
                    SET is_selected = 1
                    WHERE Patient_id = ? AND image_path = ?
                """, (pid, rel_path))

            self.conn.commit()
            print(f"[INFO] Set {len(selected_images)} image(s) as selected for Patient_id={pid}")


            # Commit changes
            self.conn.commit()

            # Cache initial data
            self.initial_data[pid] = {
                "findings": findings,
                "impression": impression,
                "doctor": doctor,
                "performed_by": performed_by,
                "dynamic_fields": self.patient_dynamic_fields.get(pid, [])[:],
            }

            # UI feedback
            self.save_button.setEnabled(False)
            self.approve_button.setEnabled(True)
            self.update_button_styles()
            self.show_status("💾 Report data saved successfully. You can now approve the report.", "lightgreen")
            print(f"[SUCCESS] Saved report for Patient_id={pid}, Visit_date={visit_date}")

        except Exception as e:
            self.show_status(f"Error saving report data: {str(e)}", "red")
            print(f"[ERROR] save_report_data: {e}")

    def get_patient_images(self, patient_id):
        try:
            self.cursor.execute("""
                SELECT image_path
                FROM Image_Capture
                WHERE Patient_id = ? AND scan_complete = 1
                ORDER BY capture_time ASC
            """, (patient_id,))
            return [row[0] for row in self.cursor.fetchall()]
        except Exception as e:
            print(f"[ERROR] get_patient_images: {e}")
            return []

    def move_image_to_selected(self, image_path):
        pid = self.patient_id_dropdown.currentText()
        if not pid or pid == "Select":
            self.show_status("No patient selected.", "orange")
            return

        full_path = os.path.normpath(os.path.join(self.project_root, image_path))
        if not os.path.exists(full_path):
            self.show_status(f"Image not found: {image_path}", "orange")
            return

        pixmap = QPixmap(full_path)
        if pixmap.isNull():
            self.show_status(f"Invalid image: {image_path}", "orange")
            return

        # Add image to the selected (center) area
        self.drop_area.add_image(full_path, image_path, pixmap)

        # Remove from the right-side image list
        for i in range(self.image_list_layout.count()):
            widget = self.image_list_layout.itemAt(i).widget()
            if isinstance(widget, DraggableLabel) and widget.image_path == image_path:
                widget.deleteLater()
                break

        # Mark the image as selected in DB
        self.cursor.execute("""
            UPDATE Image_Capture
            SET is_selected = 1
            WHERE Patient_id = ? AND image_path = ?
        """, (pid, image_path))
        self.conn.commit()

        print(f"[INFO] Moved image to selected: {image_path}")
        self.save_button.setEnabled(True)
        self.approve_button.setEnabled(False)
        self.update_button_styles()
        self.check_for_changes()


    def update_ui_for_role(self):
        if Session.role == "TECHNICIAN":
            self.findings_text.setReadOnly(True)
            self.impression_text.setReadOnly(True)
            self.new_field_name_input.setEnabled(False)
            self.new_field_content_input.setEnabled(False)
            self.add_field_button.setEnabled(False)
            self.doctor_input.setEnabled(False)
            self.save_button.setEnabled(False)
            self.approve_button.setEnabled(False)
        elif Session.role == "DOCTOR":
            self.findings_text.setReadOnly(False)
            self.impression_text.setReadOnly(False)
            self.new_field_name_input.setEnabled(True)
            self.new_field_content_input.setEnabled(True)
            self.add_field_button.setEnabled(True)
            self.doctor_input.setEnabled(True)
            # Do NOT auto-enable approve here — wait until after explicit save
            self.save_button.setEnabled(False)
            self.approve_button.setEnabled(False)

        self.update_button_styles()
        print(f"[INFO] UI updated for role: {Session.role}")

    def move_image_back_to_images(self, image_path):
        pid = self.patient_id_dropdown.currentText()
        if not pid or pid == "Select":
            self.show_status("No patient selected.", "orange")
            return
        full_path = os.path.normpath(os.path.join(self.project_root, image_path))
        if not os.path.exists(full_path):
            self.show_status(f"Image not found: {image_path}", "orange")
            return
        pixmap = QPixmap(full_path)
        if pixmap.isNull():
            self.show_status(f"Invalid image: {image_path}", "orange")
            return
        img_label = DraggableLabel(image_path, report_page=self)
        img_label.set_pixmap(pixmap)
        self.image_list_layout.addWidget(img_label, (self.image_list_layout.count() // 3), self.image_list_layout.count() % 3)
        self.drop_area.remove_image(image_path)
        self.cursor.execute("""
            UPDATE Image_Capture
            SET is_selected = 0
            WHERE Patient_id = ? AND image_path = ?
        """, (pid, image_path))
        self.conn.commit()
        print(f"[INFO] Moved image back to images: {image_path}")
        # Removing an image is a change — require save again
        self.save_button.setEnabled(True)
        self.approve_button.setEnabled(False)
        self.update_button_styles()
        self.check_for_changes()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ReportPage()
    window.show()
    sys.exit(app.exec_())
