import sys
import os
import sqlite3
from pathlib import Path
import fitz  # PyMuPDF
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QComboBox, QLineEdit, QFrame, QScrollArea, QPushButton, QGridLayout,
    QMessageBox, QCompleter, QSizePolicy
)
from PyQt5.QtGui import QPixmap, QImage, QPainter
from PyQt5.QtCore import Qt, QStringListModel
from jinja2 import Environment, FileSystemLoader, select_autoescape
import pdfkit
from markupsafe import Markup
import base64
from datetime import date


# ----------------------------- Helper: Resource Path -----------------------------
def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS  # for PyInstaller
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base_path, relative_path))


# Path to wkhtmltopdf executable
WKHTMLTOPDF_PATH = resource_path("wkhtmltopdf.exe")
wk_dir = os.path.dirname(WKHTMLTOPDF_PATH)
os.environ['PATH'] = wk_dir + os.pathsep + os.environ.get('PATH', '')


# ----------------------------- ViewReportPage -----------------------------
class ViewReportPage(QWidget):
    def __init__(self, db_path: str = None):
        super().__init__()
        self.setWindowTitle("View Report")
        self.setGeometry(100, 100, 1000, 800)
        self.project_root = os.path.dirname(os.path.abspath(__file__))

        # PDF config
        if os.path.exists(WKHTMLTOPDF_PATH):
            try:
                self.pdfkit_config = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)
            except Exception:
                self.pdfkit_config = None
        else:
            self.pdfkit_config = None

        # Database connection
        self.db_path = db_path or resource_path("viscan.db")
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            self._ensure_patient_details_columns()
            self._ensure_image_capture_schema()   # <- ensure flags exist
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Database Error", f"Failed to connect: {e}")
            self.conn = None
            self.cursor = None

        # Template setup
        self.template_dir = self.project_root
        self.template_name = "report_template.html"
        if not os.path.exists(resource_path(self.template_name)):
            QMessageBox.critical(self, "Template Missing",
                                 f"Template '{self.template_name}' not found in {self.project_root}")

        # Build UI
        self._init_ui()

        # Load approved patients
        if self.conn:
            self.load_patient_ids()

    def __del__(self):
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass

    # ----------------------------- Ensure Tables -----------------------------
    def _ensure_patient_details_columns(self):
        if not self.cursor:
            return
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Patient_Details (
                Patient_id TEXT PRIMARY KEY,
                Patient_Name TEXT,
                Age INTEGER,
                Sex TEXT,
                Phone_no TEXT,
                Registration_date DATE,
                Registered_by TEXT,
                Tobacco_Use TEXT DEFAULT 'No',
                Alcohol_Use TEXT DEFAULT 'No'
            )
        """)
        # Patient_Report minimal scaffold (used elsewhere in code)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Patient_Report (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                Patient_id TEXT,
                Overall_findings TEXT,
                Find_impression TEXT,
                Doctor_name TEXT,
                Performed_by TEXT,
                Visit_date DATE,
                report_approved INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()

    def _ensure_image_capture_schema(self):
        """Ensure Image_Capture table exists with 'is_selected' column."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Image_Capture (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                Patient_id TEXT,
                image_path TEXT,
                scan_date TEXT,
                capture_time TEXT,
                ai_label TEXT,
                scan_complete INTEGER DEFAULT 0,
                is_selected INTEGER DEFAULT 0,
                FOREIGN KEY (Patient_id) REFERENCES Patient_Details(Patient_id)
            )
        """)
        # If the table already existed, ensure 'is_selected' exists
        self.cursor.execute("PRAGMA table_info(Image_Capture)")
        cols = {row[1] for row in self.cursor.fetchall()}
        if "is_selected" not in cols:
            self.cursor.execute("ALTER TABLE Image_Capture ADD COLUMN is_selected INTEGER DEFAULT 0")
        self.conn.commit()


    # ----------------------------- UI Layout -----------------------------
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # -------- FONT STYLES --------
        label_style = """
            color: #1a237e;
            font-weight: bold;
            font-size: 18px;
        """
        field_style = """
            background-color: #E8E8E8;
            color: black;
            border-radius: 4px;
            padding: 4px;
            font-size: 20px;
        """
        button_style = """
            QPushButton {
                background-color: #1a237e;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #283593;
            }
        """

        # ---------- Top Frame ----------
        top_frame = QFrame()
        top_frame.setStyleSheet("""
            background-color: white;
            border: 1px solid #CCCCCC;
            border-radius: 10px;
            padding: 10px;
        """)
        top_layout = QGridLayout(top_frame)
        top_layout.setSpacing(10)

        # ComboBox setup
        self.patient_id_combo = QComboBox()
        self.patient_id_combo.setEditable(True)
        self.patient_id_combo.setInsertPolicy(QComboBox.NoInsert)
        self.patient_id_combo.setFixedWidth(220)
        self.patient_id_combo.currentIndexChanged.connect(self.load_patient_data)
        self.completer = QCompleter(self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.patient_id_combo.setCompleter(self.completer)

        # Read-only field setup
        def ro_field(width=220):
            f = QLineEdit()
            f.setReadOnly(True)
            f.setFixedWidth(width)
            f.setStyleSheet(field_style)
            return f

        # Create all text fields
        self.name_input = ro_field()
        self.age_input = ro_field()
        self.registration_date_input = ro_field()
        self.visit_date_input = ro_field()
        self.scan_date_input = ro_field()
        self.registered_by_input = ro_field()
        self.performed_by_input = ro_field()

        # Add widgets (3-column grid layout)
        items = [
            ("Patient ID:", self.patient_id_combo, "Name:", self.name_input, "Age / Sex:", self.age_input),
            ("Registered By:", self.registered_by_input, "Performed By:", self.performed_by_input, "Registration Date:", self.registration_date_input),
            ("Visit Date (Report):", self.visit_date_input, "Scan Date (Capture):", self.scan_date_input, "", None)
        ]

        for row, (lbl1, w1, lbl2, w2, lbl3, w3) in enumerate(items):
            if lbl1:
                l1 = QLabel(lbl1)
                l1.setStyleSheet(label_style)
                top_layout.addWidget(l1, row, 0)
                top_layout.addWidget(w1, row, 1)
            if lbl2:
                l2 = QLabel(lbl2)
                l2.setStyleSheet(label_style)
                top_layout.addWidget(l2, row, 2)
                top_layout.addWidget(w2, row, 3)
            if lbl3:
                l3 = QLabel(lbl3)
                l3.setStyleSheet(label_style)
                top_layout.addWidget(l3, row, 4)
                if w3:
                    top_layout.addWidget(w3, row, 5)

        main_layout.addWidget(top_frame)

        # ---------- Scroll Area ----------
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.pdf_container = QFrame()
        self.pdf_layout = QVBoxLayout(self.pdf_container)
        self.pdf_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.pdf_container)
        main_layout.addWidget(self.scroll_area)

        # ---------- Footer ----------
        footer_layout = QHBoxLayout()
        footer_layout.setAlignment(Qt.AlignCenter)
        self.print_button = QPushButton("Print")
        self.print_button.setFixedSize(160, 45)
        self.print_button.setStyleSheet(button_style)
        self.print_button.clicked.connect(self.print_report)
        footer_layout.addWidget(self.print_button)
        main_layout.addLayout(footer_layout)

    # ----------------------------- Load Patient IDs -----------------------------
    def load_patient_ids(self):
        if not self.cursor:
            return
        self.patient_id_combo.clear()
        self.patient_id_combo.addItem("Select")
        try:
            self.cursor.execute("""
                SELECT DISTINCT Patient_id
                FROM Patient_Report
                WHERE report_approved = 1 OR report_approved = '1'
                ORDER BY Patient_id COLLATE NOCASE
            """)
            rows = self.cursor.fetchall()
            ids = [str(r[0]) for r in rows if r and r[0]]
            if ids:
                self.patient_id_combo.addItems(ids)
                model = QStringListModel(ids)
                self.completer.setModel(model)
        except sqlite3.Error as e:
            print(f"[ERROR] load_patient_ids: {e}")

    # ----------------------------- Patient Selection Helper (optional) -----------------------------
    def select_patient_id(self, patient_id: str) -> bool:
        """Programmatically select a patient in the combo (adds if missing) and load."""
        if not patient_id:
            return False
        try:
            pid = str(patient_id).strip()
            if not pid:
                return False
            if self.patient_id_combo.count() <= 1:
                self.load_patient_ids()
            index = self.patient_id_combo.findText(pid, Qt.MatchExactly)
            if index == -1:
                self.patient_id_combo.addItem(pid)
                index = self.patient_id_combo.findText(pid, Qt.MatchExactly)
            if index != -1:
                self.patient_id_combo.blockSignals(True)
                self.patient_id_combo.setCurrentIndex(index)
                self.patient_id_combo.blockSignals(False)
                self.load_patient_data()
                return True
        except Exception as e:
            print(f"[ERROR] select_patient_id: {e}")
        return False

    def print_report(self):
        from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
        from PyQt5.QtWidgets import QApplication

        pid = self.patient_id_combo.currentText().strip()
        if not pid or pid == "Select":
            QMessageBox.information(self, "Select Patient", "Please select a patient to print.")
            return

        # --- Show temporary loading message ---
        loading_box = QMessageBox(self)
        loading_box.setWindowTitle("Please Wait")
        loading_box.setText("⏳ Generating report for printing...\nThis may take a few seconds.")
        loading_box.setStandardButtons(QMessageBox.NoButton)
        loading_box.show()
        QApplication.processEvents()  # Make sure popup appears immediately

        try:
            # Fetch the same data as display
            self.cursor.execute("""
                SELECT Overall_findings, Find_impression, Doctor_name, Performed_by, Visit_date
                FROM Patient_Report WHERE Patient_id = ? ORDER BY id DESC LIMIT 1
            """, (pid,))
            report = self.cursor.fetchone()
            if not report:
                loading_box.close()
                QMessageBox.warning(self, "No Report", "No approved report found for this patient.")
                return

            findings, impression, doctor, performed_by, visit_date = report

            self.cursor.execute("""
                SELECT image_path FROM Image_Capture
                WHERE Patient_id = ? AND IFNULL(is_selected, 0) = 1
            """, (pid,))
            image_rows = self.cursor.fetchall()
            image_list = []
            for (rel_path,) in image_rows:
                abs_path = os.path.join(self.project_root, rel_path)
                if os.path.exists(abs_path):
                    with open(abs_path, "rb") as img_file:
                        encoded = base64.b64encode(img_file.read()).decode("utf-8")
                        mime = "image/png" if abs_path.lower().endswith(".png") else "image/jpeg"
                        image_list.append(f"data:{mime};base64,{encoded}")

            # Patient info
            self.cursor.execute("SELECT Patient_Name, Age, Sex FROM Patient_Details WHERE Patient_id=?", (pid,))
            patient = self.cursor.fetchone() or ("", "", "")
            context = {
                "patient_id": pid,
                "patient_name": patient[0],
                "age": patient[1],
                "sex": patient[2],
                "findings": findings,
                "impression": impression,
                "doctor_name": doctor,
                "performed_by": performed_by,
                "date": visit_date,
                "images": image_list,
            }

            # Build HTML again
            env = Environment(loader=FileSystemLoader(self.template_dir),
                            autoescape=select_autoescape(["html", "xml"]))
            env.filters["nl2br"] = self.nl2br
            html = env.get_template(self.template_name).render(**context)

            # Generate PDF in memory
            pdf_bytes = self._generate_pdf_bytes(html)
            if not pdf_bytes:
                loading_box.close()
                QMessageBox.warning(self, "Error", "Failed to generate PDF for printing.")
                return

            # Show print dialog
            printer = QPrinter()
            dialog = QPrintDialog(printer, self)
            if dialog.exec_() != QPrintDialog.Accepted:
                loading_box.close()
                return

            # Render and print PDF directly from memory
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            painter = QPainter(printer)
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=300)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                            QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888)
                painter.drawPixmap(printer.pageRect(), QPixmap.fromImage(img))
                if i < doc.page_count - 1:
                    printer.newPage()
            painter.end()
            doc.close()
            loading_box.close()  # ✅ close before showing success
            QMessageBox.information(self, "Printed", f"Report for {pid} sent to printer successfully.")

        except Exception as e:
            if 'loading_box' in locals():
                loading_box.close()
            QMessageBox.critical(self, "Error", f"Failed to print report: {str(e)}")
            print(f"[ERROR] print_report: {e}")



    # ----------------------------- Load Patient Data -----------------------------
    def load_patient_data(self):
        if not self.cursor:
            return
        pid = self.patient_id_combo.currentText().strip()
        if not pid or pid == "Select":
            self._clear_pdf_display()
            for field in [self.name_input, self.age_input, self.registration_date_input,
                          self.visit_date_input, self.scan_date_input,
                          self.registered_by_input, self.performed_by_input]:
                field.clear()
            return

        try:
            self.cursor.execute("""
                SELECT Patient_Name, Age, Sex, Phone_no, Registration_date, Registered_by
                FROM Patient_Details WHERE Patient_id = ?
            """, (pid,))
            patient = self.cursor.fetchone()
            if patient:
                name, age, sex, phone, reg_date, reg_by = patient
                self.name_input.setText(name or "")
                self.age_input.setText(f"{age} / {sex}" if age and sex else str(age or sex or ""))
                self.registration_date_input.setText(reg_date or "")
                self.registered_by_input.setText(reg_by or "")
        except sqlite3.Error:
            pass

        try:
            self.cursor.execute("""
                SELECT Visit_date, Performed_by FROM Patient_Report
                WHERE Patient_id = ? ORDER BY id DESC LIMIT 1
            """, (pid,))
            rpt = self.cursor.fetchone()
            if rpt:
                self.visit_date_input.setText(rpt[0] or "")
                self.performed_by_input.setText(rpt[1] or "")
        except sqlite3.Error:
            pass

        try:
            self.cursor.execute("""
                SELECT scan_date FROM Image_Capture
                WHERE Patient_id = ? AND scan_date IS NOT NULL
                ORDER BY capture_time DESC LIMIT 1
            """, (pid,))
            row = self.cursor.fetchone()
            self.scan_date_input.setText(row[0] if row else "")
        except sqlite3.Error:
            self.scan_date_input.clear()

        self.load_report_for_patient(pid)

        # ----------------------------- Report Rendering -----------------------------
    def load_report_for_patient(self, pid: str):
        """Render report with selected images + dynamic extra fields."""
        if not pid or not self.conn or pid == "Select":
            self._clear_pdf_display()
            return

        try:
            # ---------------- PATIENT DETAILS ----------------
            self.cursor.execute("""
                SELECT Patient_Name, Age, Sex, Phone_no, Registration_date, Registered_by
                FROM Patient_Details WHERE Patient_id = ?
            """, (pid,))
            patient = self.cursor.fetchone()

            if patient:
                name, age, sex, phone, reg_date, reg_by = patient
            else:
                name = age = sex = phone = reg_date = reg_by = ""

            # ---------------- REPORT DETAILS ----------------
            self.cursor.execute("""
                SELECT Overall_findings, Find_impression, Doctor_name, Performed_by, Visit_date
                FROM Patient_Report WHERE Patient_id = ?
                ORDER BY id DESC LIMIT 1
            """, (pid,))
            report = self.cursor.fetchone()

            if report:
                findings, impression, doctor, performed_by, visit_date = report
            else:
                findings = impression = doctor = performed_by = ""
                visit_date = str(date.today())

            # ---------------- SELECTED IMAGES ----------------
            self.cursor.execute("""
                SELECT image_path FROM Image_Capture
                WHERE Patient_id = ?
                AND image_path IS NOT NULL
                AND IFNULL(is_selected, 0) = 1
                ORDER BY id ASC
            """, (pid,))
            rows = self.cursor.fetchall()

            image_list = []
            for (rel_path,) in rows:
                abs_path = os.path.join(self.project_root, rel_path)
                if os.path.exists(abs_path):
                    with open(abs_path, "rb") as img_file:
                        encoded = base64.b64encode(img_file.read()).decode("utf-8")
                        mime = "image/png" if abs_path.lower().endswith(".png") else "image/jpeg"
                        image_list.append(f"data:{mime};base64,{encoded}")

            if not image_list:
                self._clear_pdf_display()
                warn = QLabel("No selected images (is_selected=1) found for this patient.")
                warn.setStyleSheet("color:red;")
                self.pdf_layout.addWidget(warn)
                return

            # ---------------- EXTRA FIELDS (DYNAMIC) ----------------
            self.cursor.execute("""
                SELECT Field_name, Field_value
                FROM Patient_ExtraFields
                WHERE Patient_id = ?
                ORDER BY id ASC
            """, (pid,))
            extra_fields = self.cursor.fetchall()

            print("[DEBUG] Extra fields loaded for report:", extra_fields)

            # ---------------- JINJA CONTEXT ----------------
            context = {
                "patient_id": pid,
                "patient_name": name,
                "age": str(age),
                "sex": sex,
                "visit_date": visit_date,
                "registered_by": reg_by,
                "performed_by": performed_by,
                "doctor_name": doctor,
                "findings": findings,
                "impression": impression,
                "images": image_list,
                "extra_fields": extra_fields  # ✅ Correctly passed to template
            }

            # ---------------- RENDER HTML → PDF BYTES ----------------
            env = Environment(
                loader=FileSystemLoader(self.template_dir),
                autoescape=select_autoescape(["html", "xml"])
            )
            env.filters["nl2br"] = self.nl2br

            html = env.get_template(self.template_name).render(**context)

            pdf_bytes = self._generate_pdf_bytes(html)
            self.display_pdf_from_bytes(pdf_bytes)

        except Exception as e:
            print("[ERROR] load_report_for_patient:", e)
            self._clear_pdf_display()
            err = QLabel(f"Failed to load report: {str(e)}")
            err.setStyleSheet("color:red;")
            self.pdf_layout.addWidget(err)


    def nl2br(self, value):
        return Markup(str(value).replace("\n", "<br>\n") if value else "")

    def _generate_pdf_bytes(self, html: str):
        """
        Generate a PDF in memory (returns bytes) using pdfkit without saving to disk.
        """
        if not self.pdfkit_config:
            raise RuntimeError("wkhtmltopdf not configured.")
        pdf_bytes = pdfkit.from_string(
            html,
            False,  # False => return PDF bytes instead of saving
            configuration=self.pdfkit_config,
            options={"enable-local-file-access": None}
        )
        return pdf_bytes


    def set_patient_id(self, patient_id: str):
        """
        Called from ReportPage after a report is approved.
        Refreshes the dropdown and auto-loads the latest approved report.
        """
        if not patient_id:
            return
        try:
            # Refresh the approved patient list
            self.load_patient_ids()

            # Check if the patient is now approved and exists
            index = self.patient_id_combo.findText(patient_id)
            if index == -1:
                self.load_patient_ids()
                index = self.patient_id_combo.findText(patient_id)

            # If the approved patient exists in combo, select it
            if index != -1:
                self.patient_id_combo.setCurrentIndex(index)
                self.load_patient_data()
                print(f"[SUCCESS] Auto-refreshed ViewReportPage for approved patient: {patient_id}")
            else:
                print(f"[WARN] Approved patient {patient_id} not found in ViewReportPage list.")
        except Exception as e:
            print(f"[ERROR] set_patient_id: {e}")

    def display_pdf_from_path(self, pdf_path):
        self._clear_pdf_display()
        pdf_path = resource_path(pdf_path)
        if not os.path.exists(pdf_path):
            lbl = QLabel(f"PDF not found: {pdf_path}")
            lbl.setStyleSheet("color:red;")
            self.pdf_layout.addWidget(lbl)
            return
        doc = fitz.open(pdf_path)
        for page in doc:
            pix = page.get_pixmap(dpi=100)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                         QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888)
            lbl = QLabel()
            lbl.setPixmap(QPixmap.fromImage(img))
            lbl.setAlignment(Qt.AlignCenter)
            self.pdf_layout.addWidget(lbl)
        doc.close()

    def display_pdf_from_bytes(self, pdf_bytes: bytes):
        """Display the generated PDF directly from memory (no saving)."""
        self._clear_pdf_display()
        if not pdf_bytes:
            lbl = QLabel("Failed to generate PDF.")
            lbl.setStyleSheet("color:red;")
            self.pdf_layout.addWidget(lbl)
            return

        # Open PDF directly from bytes
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            pix = page.get_pixmap(dpi=100)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                        QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888)
            lbl = QLabel()
            lbl.setPixmap(QPixmap.fromImage(img))
            lbl.setAlignment(Qt.AlignCenter)
            self.pdf_layout.addWidget(lbl)
        doc.close()


    def _clear_pdf_display(self):
        while self.pdf_layout.count():
            w = self.pdf_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

    def print_report(self):
        from PyQt5.QtPrintSupport import QPrinter, QPrintDialog

        pid = self.patient_id_combo.currentText().strip()
        if not pid or pid == "Select":
            QMessageBox.information(self, "Select Patient", "Please select a patient to print.")
            return

        try:
            # Fetch the same data as display
            self.cursor.execute("""
                SELECT Overall_findings, Find_impression, Doctor_name, Performed_by, Visit_date
                FROM Patient_Report WHERE Patient_id = ? ORDER BY id DESC LIMIT 1
            """, (pid,))
            report = self.cursor.fetchone()
            if not report:
                QMessageBox.warning(self, "No Report", "No approved report found for this patient.")
                return

            findings, impression, doctor, performed_by, visit_date = report

            self.cursor.execute("""
                SELECT image_path FROM Image_Capture
                WHERE Patient_id = ? AND IFNULL(is_selected, 0) = 1
            """, (pid,))
            image_rows = self.cursor.fetchall()
            image_list = []
            for (rel_path,) in image_rows:
                abs_path = os.path.join(self.project_root, rel_path)
                if os.path.exists(abs_path):
                    with open(abs_path, "rb") as img_file:
                        encoded = base64.b64encode(img_file.read()).decode("utf-8")
                        mime = "image/png" if abs_path.lower().endswith(".png") else "image/jpeg"
                        image_list.append(f"data:{mime};base64,{encoded}")

            # Patient info
            self.cursor.execute("SELECT Patient_Name, Age, Sex FROM Patient_Details WHERE Patient_id=?", (pid,))
            patient = self.cursor.fetchone() or ("", "", "")
            context = {
                "patient_id": pid,
                "patient_name": patient[0],
                "age": patient[1],
                "sex": patient[2],
                "findings": findings,
                "impression": impression,
                "doctor_name": doctor,
                "performed_by": performed_by,
                "date": visit_date,
                "images": image_list,
            }

            # Build HTML again
            env = Environment(loader=FileSystemLoader(self.template_dir),
                            autoescape=select_autoescape(["html", "xml"]))
            env.filters["nl2br"] = self.nl2br
            html = env.get_template(self.template_name).render(**context)

            # Generate PDF in memory
            pdf_bytes = self._generate_pdf_bytes(html)
            if not pdf_bytes:
                QMessageBox.warning(self, "Error", "Failed to generate PDF for printing.")
                return

            # Show print dialog
            printer = QPrinter()
            dialog = QPrintDialog(printer, self)
            if dialog.exec_() != QPrintDialog.Accepted:
                return

            # Render and print PDF directly from memory
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            painter = QPainter(printer)
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=300)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                            QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888)
                painter.drawPixmap(printer.pageRect(), QPixmap.fromImage(img))
                if i < doc.page_count - 1:
                    printer.newPage()
            painter.end()
            doc.close()
            QMessageBox.information(self, "Printed", f"Report for {pid} sent to printer successfully.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to print report: {str(e)}")
            print(f"[ERROR] print_report: {e}")



# ----------------------------- Entry -----------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ViewReportPage()
    w.show()
    sys.exit(app.exec_())
