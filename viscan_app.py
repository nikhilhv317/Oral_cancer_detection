import sys
import os
import cv2
import sqlite3
from datetime import datetime
import time
import pathlib
from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QFrame, QLineEdit, QScrollArea, QGridLayout,
    QStackedLayout, QSizePolicy, QTabWidget, QCheckBox, QComboBox, QFileDialog
)
from PyQt5.QtGui import QPixmap, QImage, QIcon
import torch
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from ultralytics import YOLO
from global_session import Session


try:
    from global_session import Session
except Exception:
    class Session:
        user_id = None
        user_name = None
        role = None

def resource_path(relative_path):
    try:
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(__file__)
        full_path = os.path.normpath(os.path.join(base_path, relative_path))
        print(f"[DEBUG] Resource path for {relative_path}: {full_path}")
        if not os.path.exists(full_path):
            print(f"[ERROR] Resource not found: {full_path}")
        return full_path
    except Exception as e:
        print(f"[ERROR] Failed to resolve resource path for {relative_path}: {e}")
        return relative_path

# AI Model Configuration
CLASSIFICATION_MODEL_PATH = resource_path("yolo_cls.pt")
DETECTION_MODEL_PATH = resource_path("yolo_detect.pt")
SCORE_THRESHOLD = 0.5
CLASS_LABELS = ['normal', 'non_oral', 'potential_cancer']
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

class ViscanUI(QWidget):
    scan_completed = pyqtSignal()
    quickRegisterClicked = pyqtSignal()
    def __init__(self, patient_id=None, main_tabs=None, report_page=None, db_path=None):
        super().__init__()
        self.patient_id = patient_id
        self.main_tabs = main_tabs
        self.report_page = report_page
        self.db_path = db_path if db_path is not None else resource_path("viscan.db")
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        self.setWindowTitle("VISCAN - Patient Scanning")
        self.setStyleSheet("background-color: #1a237e;")
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)

        self.camera_index = 0
        self.available_cameras = []
        self.selected_border_style = "border: 3px solid yellow;"
        self.default_border_style = "border: none;"
        self.selected_thumb = None
        self.icon_buttons = []
        self.selected_image_path = None
        self.cap = None
        self.timer = None

        self.cls_model, self.det_model = self.load_detection_model()
        self.detect_cameras()
        self.setup_db()
        self.setup_ui()

        if self.patient_id:
            self.fetch_patient_details()

    def setup_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Image_Capture (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Patient_id TEXT,
                    image_path TEXT,
                    capture_time TEXT,
                    scan_date DATE,
                    ai_label TEXT,
                    is_selected INTEGER DEFAULT 0,
                    scan_complete INTEGER DEFAULT 0,
                    FOREIGN KEY (Patient_id) REFERENCES Patient_Details(Patient_id)
                )
            """)
            cursor.execute("PRAGMA table_info(Image_Capture)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'is_in_report' not in cols:
                cursor.execute("ALTER TABLE Image_Capture ADD COLUMN is_in_report INTEGER DEFAULT 0")
            if 'ai_label' not in cols:
                cursor.execute("ALTER TABLE Image_Capture ADD COLUMN ai_label TEXT")
            if 'visit_date' not in cols:
                cursor.execute("ALTER TABLE Image_Capture ADD COLUMN visit_date TEXT")
            conn.commit()
            conn.close()
            print("[INFO] Database schema verified for Image_Capture")
        except Exception as e:
            print(f"[ERROR] setup_db: {e}")

    def load_detection_model(self):
        try:
            if not os.path.exists(CLASSIFICATION_MODEL_PATH):
                self.record_caption.setText(f"Classification model file not found: {CLASSIFICATION_MODEL_PATH}")
                print(f"[ERROR] Classification model file not found: {CLASSIFICATION_MODEL_PATH}")
                return None, None
            if not os.path.exists(DETECTION_MODEL_PATH):
                self.record_caption.setText(f"Detection model file not found: {DETECTION_MODEL_PATH}")
                print(f"[ERROR] Detection model file not found: {DETECTION_MODEL_PATH}")
                return None, None
            print("Loading YOLOv8 classification model...")
            cls_model = YOLO(CLASSIFICATION_MODEL_PATH)
            print("Loading YOLOv5 detection model...")
            det_model = YOLO(DETECTION_MODEL_PATH)
            print("[INFO] YOLO models loaded successfully")
            return cls_model, det_model
        except Exception as e:
            self.record_caption.setText(f"Failed to load YOLO models: {str(e)}")
            print(f"[ERROR] Failed to load YOLO models: {e}")
            return None, None

    def detect_cameras(self):
        start_time = time.time()
        self.available_cameras = []
        max_cameras = 3
        for index in range(max_cameras):
            try:
                cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                if cap.isOpened():
                    ret, _ = cap.read()
                    if ret:
                        cam_name = f"Camera {index}" if index == 0 else f"USB Camera {index}"
                        self.available_cameras.append((index, cam_name))
                        print(f"[INFO] Detected camera {index}: {cam_name}")
                    cap.release()
                else:
                    print(f"[DEBUG] Camera {index} not available")
            except Exception as e:
                print(f"[ERROR] Failed to access camera {index}: {e}")
                continue

        if not self.available_cameras:
            self.record_caption.setText("No cameras detected. Please connect a camera and restart.")
            print("[ERROR] No cameras detected")
        else:
            if hasattr(self, 'camera_selector'):
                self.camera_selector.clear()
                for index, (cam_index, name) in enumerate(self.available_cameras):
                    self.camera_selector.addItem(name, cam_index)
        print(f"[DEBUG] Camera detection time: {time.time() - start_time} seconds")

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # ---------- LEFT FRAME ----------
        self.left_frame = QFrame()
        self.left_frame.setStyleSheet("background-color: #f0f0f0; border: 4px solid #283593;")
        self.left_layout = QVBoxLayout(self.left_frame)

        # Camera tabs
        self.camera_tabs = QTabWidget()
        self.camera_tabs.setStyleSheet("QTabBar::tab { height: 30px; width: 120px; }")

        # Camera feed label
        self.camera_label = QLabel()
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.camera_label.setMinimumSize(640, 480)
        self.camera_label.setStyleSheet("background-color: white;")

        camera_tab = QWidget()
        camera_layout = QVBoxLayout(camera_tab)
        camera_layout.addWidget(self.camera_label)
        self.camera_tabs.addTab(camera_tab, "Camera")

        # Image tab
        self.image_tab_widget = QWidget()
        self.image_tab_layout = QVBoxLayout(self.image_tab_widget)
        self.left_image_preview = QLabel("Full image preview will appear here")
        self.left_image_preview.setAlignment(Qt.AlignCenter)
        self.left_image_preview.setStyleSheet("background-color: white; border: 2px solid #283593;")
        self.left_image_preview.setMinimumSize(640, 480)
        self.left_image_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_tab_layout.addWidget(self.left_image_preview)
        self.image_tab_widget.setLayout(self.image_tab_layout)
        self.camera_tabs.addTab(self.image_tab_widget, "Images")
        self.left_layout.addWidget(self.camera_tabs)

        # ---------- BOTTOM FRAME ----------
        bottom_frame = QFrame()
        bottom_frame.setFixedHeight(70)
        bottom_frame.setStyleSheet("background-color: #1a237e;")
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(20, 0, 20, 0)
        bottom_layout.setSpacing(20)
        bottom_layout.setAlignment(Qt.AlignLeft)

 
        # Camera selector
        self.camera_selector = QComboBox()
        for index, name in self.available_cameras:
            self.camera_selector.addItem(name, index)
        self.camera_selector.currentIndexChanged.connect(self.change_camera)
        self.camera_selector.setStyleSheet("""
            QComboBox {
                background-color: #3949AB;
                color: white;
                font-size: 14px;
                padding: 5px;
                border-radius: 5px;
                min-width: 150px;
                max-width: 200px;
            }
            QComboBox:hover {
                background-color: #5c6bc0;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        self.camera_selector.setFixedHeight(36)
        bottom_layout.addWidget(self.camera_selector)

        # Start Scan button
        self.start_scan_btn = QPushButton("Start Scan")
        self.start_scan_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 18px;
                padding: 30px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.start_scan_btn.setFixedHeight(36)
        self.start_scan_btn.clicked.connect(self.start_scan)
        bottom_layout.addWidget(self.start_scan_btn)

        # AI Predict Button
        self.ai_predict_btn = QPushButton("AI Predict")
        self.ai_predict_btn.setFixedHeight(36)
        self.ai_predict_btn.setStyleSheet("""
            QPushButton {
                background-color: #388E3C;
                color: white;
                font-size: 16px;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 8px;
                min-width: 140px;
            }
            QPushButton:hover {
                background-color: #2E7D32;
                color: white;
            }
        """)
        self.ai_predict_btn.clicked.connect(self.run_ai_prediction)
        bottom_layout.addWidget(self.ai_predict_btn)


        # End Scan button
        self.end_scan_btn = QPushButton("End Scan")
        self.end_scan_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-size: 18px;
                padding: 30px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.end_scan_btn.setFixedHeight(36)
        self.end_scan_btn.clicked.connect(self.end_scan)
        self.end_scan_btn.setEnabled(False)
        bottom_layout.addWidget(self.end_scan_btn)

        # Caption label
        self.record_caption = QLabel("")
        self.record_caption.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        bottom_layout.addWidget(self.record_caption)


        self.left_layout.addWidget(bottom_frame)

        # ---------- RIGHT FRAME ----------
        self.right_frame = QFrame()
        self.right_frame.setStyleSheet("background-color: #0D47A1; border-radius: 10px;")
        self.right_layout = QVBoxLayout(self.right_frame)

        # Quick register checkbox
        self.patient_inputs = []
        self.quick_register_checkbox = QCheckBox("Quick Register")
        self.quick_register_checkbox.setStyleSheet("color: white;")
        self.right_layout.addWidget(self.quick_register_checkbox)
        self.quick_register_checkbox.stateChanged.connect(self.handle_quick_register)

        # Patient info section
        patient_info = QFrame()
        patient_info.setStyleSheet("color: Black; font-size: 16px;")
        patient_layout = QVBoxLayout(patient_info)

        labels = ["Patient ID", "Patient Name", "Gender (Age)", "Date"]
        for label_text in labels:
            label = QLabel(label_text)
            if label_text == "Patient ID":
                self.patient_id_combo = QComboBox()
                self.patient_id_combo.setEditable(True)
                self.patient_id_combo.setStyleSheet("background-color: white; border-radius: 5px; padding: 5px;")
                self.patient_id_combo.lineEdit().returnPressed.connect(self.fetch_patient_details)
                self.patient_id_combo.currentTextChanged.connect(self.fetch_patient_details)
                patient_layout.addWidget(label)
                patient_layout.addWidget(self.patient_id_combo)
            else:
                line_edit = QLineEdit()
                line_edit.setReadOnly(True)
                line_edit.setStyleSheet("background-color: #808080; color: white; border-radius: 5px; padding: 5px;")
                patient_layout.addWidget(label)
                patient_layout.addWidget(line_edit)
                self.patient_inputs.append(line_edit)

        patient_info.setLayout(patient_layout)
        self.right_layout.addWidget(patient_info)

        # Icons row
        icons_row = QHBoxLayout()
        self.icon_buttons = []
        for index, icon in enumerate(["icons/images.png", "icons/setting.png"]):
            resolved_path = resource_path(icon)
            btn = QPushButton()
            btn.setIcon(QIcon(resolved_path))
            btn.setIconSize(QSize(32, 32))
            btn.setCheckable(True)
            btn.setStyleSheet("background-color: transparent;")
            btn.clicked.connect(lambda checked, i=index, b=btn: self.set_active_panel(i, b))
            icons_row.addWidget(btn)
            self.icon_buttons.append(btn)
        self.right_layout.addLayout(icons_row)

        # Stacked layout
        self.stack_layout = QStackedLayout()
        self.image_widget = QWidget()
        self.image_grid = QGridLayout(self.image_widget)
        self.stack_layout.addWidget(self.image_widget)

        self.settings_widget = QLabel("Settings Panel (Coming soon...)")
        self.settings_widget.setStyleSheet("color: white; font-size: 14px;")
        self.stack_layout.addWidget(self.settings_widget)

        container = QWidget()
        container.setLayout(self.stack_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidget(container)
        scroll_area.setWidgetResizable(True)

        scroll_container = QFrame()
        scroll_container.setStyleSheet("border: 2px solid white; border-radius: 8px;")
        scroll_layout = QVBoxLayout(scroll_container)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.addWidget(scroll_area)
        self.right_layout.addWidget(scroll_container)

        # Control frame
        control_frame = QFrame()
        control_frame.setFixedHeight(60)
        control_frame.setStyleSheet("background-color: white; border-radius: 25px;")
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(10, 5, 10, 5)
        control_layout.setSpacing(20)

        self.capture_btn_center = QPushButton()
        self.capture_btn_center.setIcon(QIcon(resource_path("icons/capture.png")))
        self.capture_btn_center.setIconSize(QSize(28, 28))
        self.capture_btn_center.setFixedSize(36, 36)
        self.capture_btn_center.setStyleSheet("background-color: transparent; border: none;")
        self.capture_btn_center.clicked.connect(self.capture_image)
        control_layout.addWidget(self.capture_btn_center)
        self.right_layout.addWidget(control_frame)

        self.upload_btn = QPushButton()
        self.upload_btn.setIcon(QIcon(resource_path("icons/upload.png")))
        self.upload_btn.setIconSize(QSize(28, 28))
        self.upload_btn.setFixedSize(36, 36)
        self.upload_btn.setStyleSheet("background-color: transparent; border: none;")
        self.upload_btn.clicked.connect(self.upload_image)
        control_layout.addWidget(self.upload_btn)

        # ---------- COMBINE ----------
        main_layout.addWidget(self.left_frame, 4)
        main_layout.addWidget(self.right_frame, 1)

        self.load_patient_ids()
        self.setLayout(main_layout)

    def start_scan(self):
        try:
            if self.available_cameras:
                selected_index = 0
                for i, (index, name) in enumerate(self.available_cameras):
                    if "Camera 0" in name:
                        selected_index = i
                        break

                self.camera_index = self.available_cameras[selected_index][0]
                self.camera_selector.setCurrentIndex(selected_index)
                self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    self.record_caption.setText(f"Failed to open camera: {self.available_cameras[selected_index][1]}")
                    print(f"[ERROR] Failed to open camera {self.camera_index}")
                    return
                self.timer = QTimer()
                self.timer.timeout.connect(self.update_frame)
                self.timer.start(30)
                self.camera_label.setStyleSheet("")
                self.start_scan_btn.setEnabled(False)
                self.end_scan_btn.setEnabled(True)
                self.record_caption.setText("Camera scan started.")
                print(f"[INFO] Camera scan started with camera {self.camera_index}")
            else:
                self.record_caption.setText("No cameras available. Please connect a camera.")
                print("[ERROR] No cameras available")
        except Exception as e:
            self.record_caption.setText(f"Error starting scan: {str(e)}")
            print(f"[ERROR] start_scan: {e}")

    def change_camera(self, index):
        new_index = self.camera_selector.itemData(index)
        if new_index is not None and new_index != self.camera_index:
            if self.timer:
                self.timer.stop()
            if self.cap and self.cap.isOpened():
                self.cap.release()
            self.camera_index = new_index
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.record_caption.setText(f"Failed to open camera: {self.camera_selector.currentText()}")
                print(f"[ERROR] Failed to open camera {self.camera_index}")
                return
            if self.timer:
                self.timer.start(30)
                    
    def upload_image(self):
        try:
            file_dialog = QFileDialog(self)
            file_dialog.setNameFilter("Images (*.png *.jpg *.jpeg *.bmp)")
            file_dialog.setFileMode(QFileDialog.ExistingFile)

            if file_dialog.exec_():
                selected_files = file_dialog.selectedFiles()
                if not selected_files:
                    return

                source_path = selected_files[0]
                if not os.path.exists(source_path):
                    self.record_caption.setText("Selected image file not found.")
                    print(f"[ERROR] Selected image file not found: {source_path}")
                    return

                # --- Validate patient ID ---
                patient_id = self.patient_id_combo.currentText().strip()
                if not patient_id or patient_id == "Select":
                    self.record_caption.setText("Please select a valid Patient ID.")
                    print("[ERROR] Invalid Patient ID")
                    return

                # --- Prepare destination path ---
                scan_date = datetime.now().strftime("%Y-%m-%d")
                image_folder = self.get_patient_folder(patient_id, scan_date, 'images')
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                image_filename = f"uploaded_image_{timestamp}.jpg"
                dest_path = os.path.join(image_folder, image_filename)
                relative_dest_path = os.path.relpath(dest_path, self.project_root)

                # --- Load and save image ---
                img = cv2.imread(source_path)
                if img is None:
                    self.record_caption.setText("Failed to load the selected image.")
                    print(f"[ERROR] Failed to load image: {source_path}")
                    return

                cv2.imwrite(dest_path, img)
                print(f"[INFO] Image uploaded and saved to: {dest_path}")

                # --- Insert into Image_Capture ---
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                capture_time = datetime.now().strftime("%H:%M:%S")

                cursor.execute("""
                    INSERT INTO Image_Capture 
                    (Patient_id, image_path, capture_time, scan_date, ai_label, is_selected, scan_complete)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (patient_id, relative_dest_path, capture_time, scan_date, None, 1, 0))

                conn.commit()
                conn.close()
                print(f"[INFO] Inserted uploaded image record into Image_Capture for {patient_id}")

                # --- Update UI thumbnail ---
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                q_img = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.shape[1] * 3, QImage.Format_RGB888)
                thumb = QLabel()
                thumb.setPixmap(QPixmap.fromImage(q_img).scaled(100, 80, Qt.KeepAspectRatio))
                thumb.setStyleSheet(self.default_border_style)
                thumb.mousePressEvent = lambda e, t=thumb, path=relative_dest_path: self.highlight_thumbnail(t, path)
                thumb.mouseDoubleClickEvent = lambda e, path=relative_dest_path: self.view_full_image(path)

                count = self.image_grid.count()
                self.image_grid.addWidget(thumb, (count // 2), count % 2)

                # --- Show success feedback ---
                self.stack_layout.setCurrentIndex(0)
                self.set_active_panel(0, self.icon_buttons[0])
                self.highlight_thumbnail(thumb, relative_dest_path)
                self.view_full_image(relative_dest_path)

                self.record_caption.setText("✅ Image uploaded and saved successfully.")
                print(f"[SUCCESS] Upload complete for patient {patient_id}")

        except Exception as e:
            print(f"[ERROR] upload_image: {str(e)}")
            self.record_caption.setText(f"Error uploading image: {str(e)}")


    def update_frame(self):
        try:
            ret, frame = self.cap.read()
            if ret:
                self.current_frame = frame.copy()
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                q_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(q_img)
                self.camera_label.setPixmap(pixmap.scaled(
                    self.camera_label.width(), self.camera_label.height(), Qt.KeepAspectRatio))
            else:
                self.record_caption.setText("Failed to capture frame from camera")
                print("[ERROR] Failed to capture frame")
        except Exception as e:
            self.record_caption.setText(f"Error capturing frame: {str(e)}")
            print(f"[ERROR] update_frame: {e}")

    def capture_image(self):
        try:
            # 1️⃣ Ensure current frame is available
            if not hasattr(self, 'current_frame') or self.current_frame is None:
                self.record_caption.setText("No frame available to capture.")
                print("[ERROR] No frame available to capture")
                return

            # 2️⃣ Ensure valid patient ID is selected
            patient_id = self.patient_id_combo.currentText().strip()
            if not patient_id or patient_id == "Select":
                self.record_caption.setText("Please select a valid Patient ID.")
                print("[ERROR] Invalid Patient ID")
                return

            # 3️⃣ Prepare folder and filenames
            today = datetime.today().strftime('%Y-%m-%d')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_folder = self.get_patient_folder(patient_id, today, 'images')
            image_filename = f"image_{timestamp}.jpg"
            image_path = os.path.join(image_folder, image_filename)
            relative_image_path = os.path.relpath(image_path, self.project_root)

            # 4️⃣ Save image to disk
            success = cv2.imwrite(image_path, self.current_frame)
            if not success:
                self.record_caption.setText("Failed to save image.")
                print(f"[ERROR] Failed to save image: {image_path}")
                return

            print(f"[INFO] Image saved to: {image_path}")

            # 5️⃣ Insert record into Image_Capture
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            scan_date = datetime.now().strftime("%Y-%m-%d")
            capture_time = datetime.now().strftime("%H:%M:%S")

            cursor.execute("""
                INSERT INTO Image_Capture 
                (Patient_id, scan_date, image_path, capture_time, scan_date, ai_label, is_selected, scan_complete)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (patient_id, today, relative_image_path, capture_time, scan_date, None, 0, 0))

            conn.commit()
            conn.close()

            print(f"[INFO] Image record added to Image_Capture for {patient_id}")

            # 6️⃣ Update UI thumbnails
            rgb = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
            q_img = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.shape[1] * 3, QImage.Format_RGB888)

            thumb = QLabel()
            thumb.setPixmap(QPixmap.fromImage(q_img).scaled(100, 80, Qt.KeepAspectRatio))
            thumb.setStyleSheet(self.default_border_style)
            thumb.mousePressEvent = lambda e, t=thumb, path=relative_image_path: self.highlight_thumbnail(t, path)
            thumb.mouseDoubleClickEvent = lambda e, path=relative_image_path: self.view_full_image(path)

            count = self.image_grid.count()
            self.image_grid.addWidget(thumb, (count // 2), count % 2)

            # 7️⃣ Show success feedback
            self.record_caption.setText("Image captured successfully.")
            print(f"[INFO] Image captured for {patient_id} at {scan_date} {capture_time}")

        except Exception as e:
            import traceback
            print("[ERROR] capture_image():", e)
            traceback.print_exc()
            self.record_caption.setText(f"Error capturing image: {str(e)}")

    def view_full_image(self, image_path):
        full_path = os.path.normpath(os.path.join(self.project_root, image_path)) if not os.path.isabs(image_path) else image_path
        if os.path.exists(full_path):
            pixmap = QPixmap(full_path).scaled(
                self.left_image_preview.width(),
                self.left_image_preview.height(),
                Qt.KeepAspectRatio
            )
            self.left_image_preview.setPixmap(pixmap)
            self.camera_tabs.setCurrentIndex(1)
            self.selected_image_path = full_path
            self.record_caption.setText("Image displayed.")
            print(f"[INFO] Displaying image: {full_path} (relative: {image_path})")
        else:
            self.record_caption.setText(f"Image file not found: {full_path}")
            print(f"[ERROR] Image file not found: {full_path}")

    def highlight_thumbnail(self, thumb, image_path=None):
        if self.selected_thumb:
            self.selected_thumb.setStyleSheet(self.default_border_style)
        thumb.setStyleSheet(self.selected_border_style)
        self.selected_thumb = thumb
        if image_path:
            self.selected_image_path = os.path.normpath(os.path.join(self.project_root, image_path)) if not os.path.isabs(image_path) else image_path
            print(f"[INFO] Thumbnail highlighted for image: {self.selected_image_path} (relative: {image_path})")

    def store_image_path(self, patient_id, image_path):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            capture_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
                INSERT INTO Image_Capture 
                (Patient_id, scan_date, image_path, capture_time, is_selected, ai_label, scan_complete)
                VALUES (?, ?, ?, ?, 0, NULL, 0)
            """, (patient_id, image_path, capture_time))
            conn.commit()
            conn.close()
            print(f"[INFO] Image stored: {image_path} for Patient_id={patient_id}")
        except Exception as e:
            print(f"[ERROR] Failed to store image path: {e}")
            self.record_caption.setText(f"Error storing image path: {str(e)}")

    def create_patient_if_not_exists(self, patient_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM Patient_Details WHERE Patient_id = ?", (patient_id,))
            if not cursor.fetchone():
                today = datetime.today().strftime("%Y-%m-%d")
                cursor.execute("""
                    INSERT INTO Patient_Details (Patient_id, Patient_Name, Age, Sex,Registration_date)
                    VALUES (?, ?, ?, ?, ?)
                """, (patient_id, "AutoGenerated", 0, "NA", today))
                conn.commit()
                self.save_patient_report_entry(
                    patient_id=patient_id,
                    patient_name="AutoGenerated"
                )
            conn.close()
            print(f"[INFO] Patient created or exists: {patient_id}")
        except Exception as e:
            print(f"[ERROR] Failed to create patient: {e}")
            self.record_caption.setText(f"Error creating patient: {str(e)}")

    def set_patient_id(self, patient_id, visit_date=None):
        """Sets the active patient ID in the capture page and ensures report linkage."""
        try:
            self.patient_id = patient_id

            # --- Update dropdown ---
            if hasattr(self, "patient_id_combo"):
                existing_items = [self.patient_id_combo.itemText(i) for i in range(self.patient_id_combo.count())]
                if patient_id not in existing_items:
                    self.patient_id_combo.addItem(patient_id)
                self.patient_id_combo.setCurrentText(patient_id)

            # --- Fetch patient details (updates UI fields) ---
            self.fetch_patient_details()

            # --- Fetch patient name from Patient_Details ---
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT Patient_Name FROM Patient_Details 
                WHERE Patient_id = ?
            """, (patient_id,))
            result = cursor.fetchone()
            patient_name = result[0] if result else "Unknown"

            # --- Fetch doctor name from Patient_Report (latest entry if exists) ---
            cursor.execute("""
                SELECT Doctor_name FROM Patient_Report
                WHERE Patient_id = ?
                ORDER BY id DESC LIMIT 1
            """, (patient_id,))
            doc_result = cursor.fetchone()
            doctor_name = doc_result[0] if doc_result and doc_result[0] else "Unknown Doctor"

            conn.close()

            # --- Save (or update) Patient_Report entry safely ---
            self.save_patient_report_entry(
                patient_id=patient_id,
                patient_name=patient_name,
                doctor_name=doctor_name
            )

            print(f"[INFO] Capture Page updated with Patient ID: {patient_id}, Doctor: {doctor_name}")

        except Exception as e:
            print(f"[ERROR] Failed to update Patient_Report in set_patient_id: {e}")
            if hasattr(self, "record_caption"):
                self.record_caption.setText(f"Error updating report: {str(e)}")

    def handle_quick_register(self, state):
        if state == Qt.Checked:
            self.quickRegisterClicked.emit()

    def get_patient_id(self):
        if not self.patient_id:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM Patient_Details")
                count = cursor.fetchone()[0]
                conn.close()
                new_id = f"P{count + 1:03d}"
                self.patient_id = new_id
                self.create_patient_if_not_exists(self.patient_id)
                print(f"[INFO] Generated new patient ID: {self.patient_id}")
            except Exception as e:
                print(f"[ERROR] Failed to generate patient ID: {e}")
                self.record_caption.setText(f"Error generating patient ID: {str(e)}")
        return self.patient_id

    def get_patient_folder(self, patient_id, visit_date, media_type):
        try:
            if not patient_id or patient_id == "Select":
                patient_id = "UnknownPatient"
            if not visit_date:
                visit_date = datetime.today().strftime('%Y-%m-%d')
            base_path = pathlib.Path("data") / patient_id / media_type
            base_path.mkdir(parents=True, exist_ok=True)
            full_path = str(base_path)
            print(f"[INFO] Patient folder: {full_path}")
            return full_path
        except Exception as e:
            print(f"[ERROR] Failed to create patient folder: {e}")
            self.record_caption.setText(f"Error creating patient folder: {str(e)}")
            return str(pathlib.Path("data/UnknownPatient"))

    def draw_label(self, image, label, confidence):
        """
        Draw a visually consistent label on the image,
        with fixed on-screen appearance — works for all image sizes.
        """
        try:
            from PIL import ImageDraw, ImageFont, Image

            # Convert to RGBA for transparency
            if image.mode != "RGBA":
                image = image.convert("RGBA")

            overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            # --- Get image size ---
            w, h = image.size

            # --- Normalized scale factor ---
            # Ensures consistent label size across resolutions
            # Cap the scale_factor between 0.5 and 1.5 for stability
            display_ref_width = 800  # your on-screen preview width in pixels
            scale_factor = min(max(w / display_ref_width, 0.5), 1.5)

            # --- Fixed box size (proportional to typical screen display) ---
            base_box_width = 220
            base_box_height = 45
            fixed_box_width = int(base_box_width * scale_factor)
            fixed_box_height = int(base_box_height * scale_factor)

            # --- Top-left position ---
            x0, y0 = 10, 10
            x1, y1 = x0 + fixed_box_width, y0 + fixed_box_height

            # --- Ensure label is always visible (avoid overflow on small images) ---
            if x1 > w:
                x1 = w - 5
                x0 = x1 - fixed_box_width
            if y1 > h:
                y1 = h - 5
                y0 = y1 - fixed_box_height

            # --- Semi-transparent orange background ---
            bg_color = (255, 140, 0, 200)
            draw.rectangle([x0, y0, x1, y1], fill=bg_color)

            # --- Font setup ---
            try:
                font_size = max(18, int(22 * scale_factor))
                font = ImageFont.truetype("arial.ttf", size=font_size)
            except IOError:
                font = ImageFont.load_default()

            # --- Text to display ---
            text = f"{label} ({confidence:.2f})"

            # Measure text size
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            # --- Center text ---
            text_x = x0 + (fixed_box_width - text_w) / 2
            text_y = y0 + (fixed_box_height - text_h) / 2 - 2

            # --- Draw the text ---
            draw.text((text_x, text_y), text, fill="white", font=font)

            # --- Merge overlay back into image ---
            image = Image.alpha_composite(image, overlay)
            return image.convert("RGB")

        except Exception as e:
            print(f"[ERROR] Error drawing label: {str(e)}")
            self.record_caption.setText(f"Error drawing label: {str(e)}")
            raise




    def run_ai_prediction(self):
        if not self.selected_image_path or not os.path.exists(self.selected_image_path):
            self.record_caption.setText("Please select an image to process.")
            print("[ERROR] No valid image selected for prediction")
            return

        if not self.cls_model or not self.det_model:
            self.record_caption.setText("YOLO models are not loaded properly.")
            print("[ERROR] YOLO models not loaded")
            return

        try:
            relative_selected_path = os.path.relpath(self.selected_image_path, self.project_root)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT Patient_id, scan_date
                FROM Image_Capture
                WHERE image_path = ?
            """, (relative_selected_path,))
            row = cursor.fetchone()
            if not row:
                self.record_caption.setText("Error: Original image not found in database.")
                print(f"[ERROR] No entry found for image_path: {relative_selected_path}")
                conn.close()
                return
            patient_id, scan_date = row
            conn.close()

            # --- Validate patient ID ---
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM Patient_Details WHERE Patient_id = ?", (patient_id,))
            if not cursor.fetchone():
                self.record_caption.setText(f"Invalid Patient ID: {patient_id}")
                print(f"[ERROR] Invalid Patient ID: {patient_id}")
                conn.close()
                return
            conn.close()

            # --- Perform prediction ---
            image = Image.open(self.selected_image_path).convert("RGB")
            output_img = image.copy()

            cls_results = self.cls_model(self.selected_image_path)
            cls_pred_idx = int(cls_results[0].probs.top1)
            cls_pred_label = CLASS_LABELS[cls_pred_idx]
            cls_conf = float(cls_results[0].probs.top1conf)
            prediction_label = cls_pred_label

            if cls_pred_label == "potential_cancer":
                print("→ Detected potential cancer, running YOLOv5 detection...")
                det_results = self.det_model(self.selected_image_path, save=False)
                for r in det_results:
                    im_bgr = r.plot()
                    output_img = Image.fromarray(cv2.cvtColor(im_bgr, cv2.COLOR_BGR2RGB))
                self.record_caption.setText("Potential cancer detected.")
            else:
                output_img = self.draw_label(output_img, cls_pred_label, cls_conf)
                if cls_pred_label == "normal":
                    self.record_caption.setText("Non-cancer detected.")
                else:
                    self.record_caption.setText("Non-oral image detected. Please insert oral image.")

            # --- Save predicted image ---
            image_folder = self.get_patient_folder(patient_id, scan_date, 'images')
            base, ext = os.path.splitext(os.path.basename(self.selected_image_path))
            pred_filename = f"{base}_predicted{ext}"
            pred_path = os.path.join(image_folder, pred_filename)
            relative_pred_path = os.path.relpath(pred_path, self.project_root)
            output_img.save(pred_path)

            # --- Insert prediction result into DB ---
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            capture_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
                INSERT INTO Image_Capture 
                (Patient_id, image_path, capture_time, scan_date, ai_label, is_selected, scan_complete)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (patient_id, relative_pred_path, capture_time, scan_date, prediction_label, 1, 0))
            conn.commit()
            conn.close()
            print(f"[INFO] Inserted predicted image for {patient_id}: {relative_pred_path}")

            # --- Display result ---
            output_img_rgb = output_img.convert("RGB")
            img_array = np.array(output_img_rgb)
            height, width, channel = img_array.shape
            bytes_per_line = channel * width
            qimage = QImage(img_array.data, width, height, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimage).scaled(
                self.left_image_preview.width(),
                self.left_image_preview.height(),
                Qt.KeepAspectRatio
            )
            self.left_image_preview.setPixmap(pixmap)
            self.camera_tabs.setCurrentIndex(1)
            self.selected_image_path = pred_path
            print("[INFO] AI prediction completed")

        except Exception as e:
            print(f"[ERROR] Prediction failed: {str(e)}")
            self.record_caption.setText(f"Prediction failed: {str(e)}")


    def set_active_panel(self, index, clicked_btn):
        try:
            self.stack_layout.setCurrentIndex(index)
            for btn in self.icon_buttons:
                if btn == clicked_btn:
                    btn.setStyleSheet("background-color: white; border: 2px solid yellow; border-radius: 5px;")
                else:
                    btn.setStyleSheet("background-color: transparent;")
            self.record_caption.setText("Panel switched.")
            print(f"[INFO] Switched to panel {index}")
        except Exception as e:
            print(f"[ERROR] set_active_panel: {e}")
            self.record_caption.setText(f"Error switching panel: {str(e)}")

    def fetch_patient_details(self):
        patient_id = self.patient_id_combo.currentText().strip()
        print(f"[DEBUG] Fetching details for Patient ID: {patient_id}")

        if not patient_id or patient_id == "Select":
            print("[DEBUG] No Patient ID selected.")
            self.record_caption.setText("No Patient ID selected.")
            for field in self.patient_inputs:
                field.clear()
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 1️⃣ Try main Patient_Details table
            cursor.execute("""
                SELECT Patient_Name, Sex, Age, Registration_date 
                FROM Patient_Details 
                WHERE Patient_id = ?
            """, (patient_id,))
            row = cursor.fetchone()

            # 2️⃣ Fallback to Quick_Register table if not found
            if not row:
                print("[DEBUG] Not found in Patient_Details. Trying Quick_Register table...")
                cursor.execute("""
                    SELECT Patient_Name, Sex, Age, Visit_date 
                    FROM Quick_Register 
                    WHERE Patient_id = ?
                """, (patient_id,))
                row = cursor.fetchone()

            conn.close()

            # 3️⃣ Fill data if found
            if row:
                full_name, sex, age, Registration_date = row
                print(f"[DEBUG] Raw DB values -> Name: {full_name}, Sex: {sex}, Age: {age}, Visit: {Registration_date}")

                # ✅ Handle 0 age properly
                sex = str(sex or "").strip()
                age_str = str(age).strip() if age is not None else ""

                # ✅ Format Gender (Age) — show (0) also
                if sex and age_str != "":
                    gender_age = f"{sex} ({age_str})"
                elif sex:
                    gender_age = sex
                elif age_str != "":
                    gender_age = f"({age_str})"
                else:
                    gender_age = ""

                print(f"[DEBUG] Formatted Gender/Age -> {gender_age}")

                # Fill fields
                self.patient_inputs[0].setText(full_name or "")
                self.patient_inputs[1].setText(gender_age)
                self.patient_inputs[2].setText(Registration_date or "")
                self.record_caption.setText("Patient details auto-filled from registration.")
                print(f"[INFO] Patient details loaded for ID: {patient_id}")

            else:
                print("[DEBUG] No matching patient found in either table.")
                for field in self.patient_inputs:
                    field.clear()
                self.record_caption.setText(f"No patient found for ID: {patient_id}")

        except Exception as e:
            print(f"[ERROR] fetch_patient_details: {e}")
            self.record_caption.setText(f"Error fetching patient data: {str(e)}")
            for field in self.patient_inputs:
                field.clear()



    def load_patient_data(self, patient_id: str):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT Patient_Name, Age, Sex, Phone_no, Performed_by
                FROM Patient_Details
                WHERE Patient_id = ?
            """, (patient_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                name, age, gender, phone, performed_by = row
                if hasattr(self, 'patient_name_field'):
                    self.patient_name_field.setText(name)
                if hasattr(self, 'age_field'):
                    self.age_field.setText(str(age))
                if hasattr(self, 'gender_field'):
                    self.gender_field.setCurrentText(gender)
                if hasattr(self, 'phone_field'):
                    self.phone_field.setText(phone)
                if hasattr(self, 'examined_by_field'):
                    self.examined_by_field.setText(performed_by)
        except Exception as e:
            print(f"[ERROR] Capture: Failed to load patient data -> {e}")

    def load_patient(self, patient_id):
        self.patient_id_input.setText(patient_id)
        details = self.fetch_patient_details(patient_id)
        if details:
            self.name_input.setText(details["name"])
            self.age_input.setText(str(details["age"]))
            self.gender_input.setText(details["gender"])

    def load_patient_ids(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT pd.Patient_id
                FROM Patient_Details pd
                LEFT JOIN Image_Capture ic ON pd.Patient_id = ic.Patient_id
                WHERE ic.scan_complete = 0 OR ic.scan_complete IS NULL
                ORDER BY pd.Patient_id
            """)
            patient_ids = [row[0] for row in cursor.fetchall()]
            conn.close()
            self.patient_id_combo.clear()
            self.patient_id_combo.addItem("Select")
            self.patient_id_combo.addItems(patient_ids)
            print(f"[INFO] Loaded incomplete patient IDs: {patient_ids}")
            if self.patient_id:
                index = self.patient_id_combo.findText(self.patient_id)
                if index >= 0:
                    self.patient_id_combo.setCurrentIndex(index)
                    self.fetch_patient_details()
                    print(f"[INFO] Auto-selected patient_id from registration: {self.patient_id}")
        except Exception as e:
            print(f"[ERROR] load_patient_ids: {e}")
            self.record_caption.setText(f"Error loading patient IDs: {str(e)}")

    def end_scan(self):
        patient_id = self.patient_id_combo.currentText().strip()
        if not patient_id or patient_id == "Select":
            self.record_caption.setText("Please select a valid Patient ID.")
            print("[ERROR] No valid Patient ID selected")
            return

        try:
            visit_date = datetime.now().strftime("%Y-%m-%d")

            # --- Stop timer and release camera ---
            if self.timer:
                self.timer.stop()
                self.timer = None
            if self.cap and self.cap.isOpened():
                self.cap.release()
                self.cap = None

            # --- Reset camera label ---
            self.camera_label.setPixmap(QPixmap())
            self.camera_label.setStyleSheet("background-color: white;")

            # --- Mark scan complete in database ---
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE Image_Capture
                SET scan_complete = 1
                WHERE Patient_id = ?
            """, (patient_id,))
            conn.commit()
            conn.close()
            print(f"[INFO] Scan marked complete for patient {patient_id}")

            # --- Fetch patient name (no Examined_by column anymore) ---
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT Patient_Name
                FROM Patient_Details
                WHERE Patient_id = ?
            """, (patient_id,))
            result = cursor.fetchone()
            conn.close()

            if result:
                patient_name = result[0]
            else:
                patient_name = "Unknown"

            # --- Get current user name as Doctor/Technician ---
            doctor_name = getattr(Session, "username", "Unknown")

            # --- Save to Patient_Report ---
            self.save_patient_report_entry(patient_id, patient_name, doctor_name)

            # --- Reset UI elements ---
            for i in reversed(range(self.image_grid.count())):
                widget = self.image_grid.itemAt(i).widget()
                if widget:
                    widget.setParent(None)

            self.selected_thumb = None
            self.selected_image_path = None
            self.left_image_preview.setPixmap(QPixmap())
            self.left_image_preview.setText("Full image preview will appear here")
            self.camera_tabs.setCurrentIndex(0)

            for field in self.patient_inputs:
                field.clear()

            index = self.patient_id_combo.findText(patient_id)
            if index >= 0:
                self.patient_id_combo.removeItem(index)
            self.patient_id_combo.setCurrentIndex(0)
            self.patient_id = None

            self.start_scan_btn.setEnabled(True)
            self.end_scan_btn.setEnabled(False)
            self.scan_completed.emit()

            # --- Success message ---
            self.record_caption.setText(f"✅ Scan completed for {patient_id}. Report entry saved.")
            print(f"[INFO] Patient_Report updated with Performed_by={Session.username}, Doctor_name={doctor_name}")

        except Exception as e:
            print(f"[ERROR] end_scan: {e}")
            self.record_caption.setText(f"Failed to mark scan complete: {str(e)}")


    def save_patient_report_entry(self, patient_id, patient_name, doctor_name):
        try:
            performed_by = Session.user_name if Session.user_name else "Unknown"
            if not doctor_name:
                doctor_name = "Unknown Doctor"
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM Patient_Report WHERE Patient_id = ?", (patient_id,))
            report_result = cursor.fetchone()
            if not report_result:
                cursor.execute("""
                    INSERT INTO Patient_Report 
                    (Patient_id, Patient_Name, Overall_findings, Find_impression, Performed_by, Doctor_name, report_approved)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                """, (patient_id, patient_name, "", "", performed_by, doctor_name))
                print(f"[INFO] Report entry created for {patient_id} with Performed_by={performed_by}, Doctor_name={doctor_name}")
            else:
                cursor.execute("""
                    UPDATE Patient_Report 
                    SET Performed_by = ?, Patient_Name = ?, Doctor_name = ?, report_approved = 0
                    WHERE Patient_id = ?
                """, (performed_by, patient_name, doctor_name, patient_id))
                print(f"[INFO] Report entry updated for {patient_id} with Performed_by={performed_by}, Doctor_name={doctor_name}")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[ERROR] Could not insert/update Patient_Report entry: {e}")
            self.record_caption.setText(f"Error saving report entry: {str(e)}")

class FullScreenImage(QWidget):
    def __init__(self, image_path):
        super().__init__()
        self.setWindowTitle("Full Image Preview")
        self.setStyleSheet("background-color: black;")
        self.setGeometry(300, 300, 1000, 700)
        layout = QVBoxLayout()
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        resolved_path = resource_path(image_path) if not os.path.isabs(image_path) else image_path
        if os.path.exists(resolved_path):
            pixmap = QPixmap(resolved_path)
            self.image_label.setPixmap(pixmap.scaled(self.width(), self.height(), Qt.KeepAspectRatio))
            print(f"[INFO] Full screen image loaded: {resolved_path}")
        else:
            print(f"[ERROR] Full screen image not found: {resolved_path}")
        layout.addWidget(self.image_label)
        self.setLayout(layout)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ViscanUI()
    window.show()
    sys.exit(app.exec_())