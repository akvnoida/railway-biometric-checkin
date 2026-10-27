import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

import cv2
import face_recognition
import numpy as np
from PIL import Image, ImageTk

from enroll_passenger import enroll_passenger
from railway_data import (
    find_face_matches,
    load_manifest,
    redeem_qr_token,
    save_manifest,
)

NAVY = "#06162e"
PANEL = "#0c2343"
PANEL_LIGHT = "#102d52"
BLUE = "#0878d1"
CYAN = "#42d9ee"
GREEN = "#21d48a"
AMBER = "#ffbd4a"
RED = "#ff5f68"
WHITE = "#f4f8ff"
MUTED = "#9cb0ca"


class RailwayKiosk:
    def __init__(self, root):
        self.root = root
        self.root.title("Indian Railways | Smart Biometric Gate")
        self.root.geometry("1360x760")
        self.root.minsize(1000, 680)
        self.root.state("zoomed")
        self.root.configure(bg=NAVY)

        self.stop_event = threading.Event()
        self.state_lock = threading.Lock()
        self.latest_frame = None
        self.face_boxes = []
        self.state = {
            "camera": "STARTING",
            "face": "waiting",
            "message": "Position your face inside the camera frame",
            "passenger": None,
            "progress": 0,
            "gate_open": False,
        }
        self._photo = None

        self._configure_styles()
        self._build_header()
        self._build_gate_banner()
        self._build_main_area()
        self._build_status_bar()
        self._build_footer()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.worker = threading.Thread(target=self._camera_worker, daemon=True)
        self.worker.start()
        self.root.after(30, self._refresh_ui)

    def _configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Kiosk.Horizontal.TProgressbar",
            troughcolor="#193657",
            background=CYAN,
            bordercolor="#193657",
            lightcolor=CYAN,
            darkcolor=CYAN,
        )

    def _build_header(self):
        header = tk.Frame(self.root, bg="#082247", height=96)
        header.pack(fill="x")
        header.pack_propagate(False)

        brand_mark = tk.Frame(header, bg=BLUE, width=58, height=58)
        brand_mark.place(x=24, y=18)
        brand_mark.pack_propagate(False)
        tk.Label(
            brand_mark,
            text="IR",
            font=("Segoe UI", 22, "bold"),
            bg=BLUE,
            fg=WHITE,
        ).pack(expand=True)

        tk.Label(
            header,
            text="INDIAN RAILWAYS",
            font=("Segoe UI", 13, "bold"),
            bg="#082247",
            fg=WHITE,
        ).place(x=98, y=18)
        tk.Label(
            header,
            text="SMART BIOMETRIC CONCOURSE GATE",
            font=("Segoe UI", 21, "bold"),
            bg="#082247",
            fg=CYAN,
        ).place(x=98, y=40)
        tk.Label(
            header,
            text="Secure passenger verification",
            font=("Segoe UI", 10),
            bg="#082247",
            fg=MUTED,
        ).place(x=100, y=70)
        tk.Label(
            header,
            text="SAFE JOURNEY\nA STRONGER INDIA",
            justify="right",
            font=("Segoe UI", 9, "bold"),
            bg="#082247",
            fg=WHITE,
        ).place(relx=0.98, y=28, anchor="ne")

    def _build_gate_banner(self):
        self.gate_banner = tk.Frame(
            self.root, bg="#451c2d", height=54, highlightthickness=1,
            highlightbackground="#a6384a",
        )
        self.gate_banner.pack(fill="x", padx=22, pady=(10, 12))
        self.gate_banner.pack_propagate(False)

        self.gate_icon = tk.Label(
            self.gate_banner,
            text="●",
            font=("Segoe UI", 20, "bold"),
            bg="#451c2d",
            fg=RED,
        )
        self.gate_icon.pack(side="left", padx=(18, 12))
        self.gate_status = tk.Label(
            self.gate_banner,
            text="GATE STATUS: LOCKED",
            font=("Segoe UI", 15, "bold"),
            bg="#451c2d",
            fg="#ff8a8f",
        )
        self.gate_status.pack(side="left")
        self.gate_message = tk.Label(
            self.gate_banner,
            text="•  WAITING FOR VERIFICATION",
            font=("Segoe UI", 11, "bold"),
            bg="#451c2d",
            fg="#e1c4cb",
        )
        self.gate_message.pack(side="left", padx=12)

    def _build_main_area(self):
        body = tk.Frame(self.root, bg=NAVY)
        body.pack(fill="both", expand=True, padx=22)
        body.grid_columnconfigure(0, weight=3, uniform="main")
        body.grid_columnconfigure(1, weight=2, uniform="main")
        body.grid_rowconfigure(0, weight=1)

        self.camera_panel = tk.Frame(
            body, bg=PANEL, highlightthickness=1, highlightbackground="#315477"
        )
        self.camera_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        camera_header = tk.Frame(self.camera_panel, bg=PANEL, height=42)
        camera_header.pack(fill="x")
        camera_header.pack_propagate(False)
        tk.Label(
            camera_header,
            text="  ▣  LIVE CAMERA FEED  •  FACE + ONE-TIME KIOSK QR",
            font=("Segoe UI", 10, "bold"),
            bg=PANEL,
            fg=WHITE,
        ).pack(side="left", padx=10)
        self.camera_indicator = tk.Label(
            camera_header, text="●", font=("Segoe UI", 10), bg=PANEL, fg=AMBER
        )
        self.camera_indicator.pack(side="left", padx=4)

        self.video_label = tk.Label(
            self.camera_panel,
            text="Connecting to camera…",
            font=("Segoe UI", 14),
            bg="#020a14",
            fg=MUTED,
        )
        self.video_label.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.verification_panel = tk.Frame(
            body, bg=PANEL, highlightthickness=1, highlightbackground="#315477"
        )
        self.verification_panel.grid(row=0, column=1, sticky="nsew")
        self._build_verification_card()

    def _build_verification_card(self):
        title = tk.Frame(self.verification_panel, bg=PANEL, height=42)
        title.pack(fill="x")
        title.pack_propagate(False)
        tk.Label(
            title,
            text="  ●  PASSENGER VERIFICATION",
            font=("Segoe UI", 10, "bold"),
            bg=PANEL,
            fg=WHITE,
        ).pack(side="left", padx=10)
        tk.Frame(self.verification_panel, bg="#234161", height=1).pack(
            fill="x", padx=14
        )

        status_area = tk.Frame(self.verification_panel, bg=PANEL)
        status_area.pack(fill="x", padx=16, pady=10)
        self.avatar = tk.Label(
            status_area,
            text="IR",
            font=("Segoe UI", 22, "bold"),
            width=4,
            height=2,
            bg="#173c66",
            fg=CYAN,
        )
        self.avatar.pack(side="left", padx=(0, 12))
        self.verify_card = tk.Frame(status_area, bg="#19334d", height=70)
        self.verify_card.pack(side="left", fill="x", expand=True)
        self.verify_card.pack_propagate(False)
        self.verify_title = tk.Label(
            self.verify_card,
            text="WAITING",
            font=("Segoe UI", 16, "bold"),
            bg="#19334d",
            fg=AMBER,
        )
        self.verify_title.pack(anchor="w", padx=14, pady=(12, 0))
        self.verify_subtitle = tk.Label(
            self.verify_card,
            text="Passenger identity not checked",
            font=("Segoe UI", 9),
            bg="#19334d",
            fg=MUTED,
        )
        self.verify_subtitle.pack(anchor="w", padx=14)

        self.detail_vars = {}
        detail_rows = (
            ("Passenger", "name"),
            ("Ticket / PNR", "pnr"),
            ("Train", "train"),
            ("Journey date", "journey_date"),
            ("From → To", "route"),
            ("Platform", "platform"),
            ("Coach / Seat", "seat"),
        )
        details = tk.Frame(self.verification_panel, bg=PANEL)
        details.pack(fill="both", expand=True, padx=18, pady=(0, 6))
        for label, key in detail_rows:
            row = tk.Frame(details, bg=PANEL, height=30)
            row.pack(fill="x")
            row.pack_propagate(False)
            tk.Label(
                row,
                text=label,
                anchor="w",
                width=17,
                font=("Segoe UI", 9),
                bg=PANEL,
                fg=MUTED,
            ).pack(side="left")
            value = tk.Label(
                row,
                text="—",
                anchor="w",
                font=("Segoe UI", 9, "bold"),
                bg=PANEL,
                fg=WHITE,
            )
            value.pack(side="left", fill="x", expand=True)
            self.detail_vars[key] = value
            tk.Frame(details, bg="#203b5a", height=1).pack(fill="x")

        self.instruction_card = tk.Frame(
            self.verification_panel, bg="#063d78", height=64
        )
        self.instruction_card.pack(fill="x", padx=12, pady=(4, 12))
        self.instruction_card.pack_propagate(False)
        self.instruction_title = tk.Label(
            self.instruction_card,
            text="LOOK AT THE CAMERA TO VERIFY",
            font=("Segoe UI", 11, "bold"),
            bg="#063d78",
            fg=WHITE,
        )
        self.instruction_title.pack(pady=(13, 2))
        self.instruction_text = tk.Label(
            self.instruction_card,
            text="Keep your face clearly visible in the frame",
            font=("Segoe UI", 9),
            bg="#063d78",
            fg="#d0e7ff",
        )
        self.instruction_text.pack()

    def _build_status_bar(self):
        bar = tk.Frame(self.root, bg=NAVY)
        bar.pack(fill="x", padx=22, pady=(10, 8))
        for column in range(4):
            bar.grid_columnconfigure(column, weight=1, uniform="status")

        self.status_values = {}
        for column, (key, title, initial) in enumerate(
            (
                ("camera", "CAMERA STATUS", "CONNECTING"),
                ("face", "FACE MATCH", "WAITING"),
                ("ticket", "TICKET STATUS", "READY"),
            )
        ):
            card = tk.Frame(
                bar, bg=PANEL, height=56, highlightthickness=1,
                highlightbackground="#254567",
            )
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
            card.grid_propagate(False)
            color = GREEN if key == "camera" else CYAN
            dot = tk.Label(card, text="●", font=("Segoe UI", 17), bg=PANEL, fg=color)
            dot.pack(side="left", padx=(14, 10))
            texts = tk.Frame(card, bg=PANEL)
            texts.pack(side="left", pady=8)
            tk.Label(
                texts,
                text="FACE / QR STATUS" if key == "face" else title,
                font=("Segoe UI", 8, "bold"),
                bg=PANEL, fg=MUTED,
            ).pack(anchor="w")
            value = tk.Label(
                texts, text=initial, font=("Segoe UI", 10, "bold"),
                bg=PANEL, fg=color,
            )
            value.pack(anchor="w")
            self.status_values[key] = (value, dot)

        actions = tk.Frame(bar, bg=NAVY)
        actions.grid(row=0, column=3, sticky="ew", padx=(8, 0))
        bar.grid_columnconfigure(3, weight=2, uniform="status")
        self.enroll_button = tk.Button(
            actions,
            text="+  ENROLL PASSENGER",
            command=self._open_enrollment,
            font=("Segoe UI", 10, "bold"),
            bg=BLUE,
            fg=WHITE,
            activebackground="#1489e7",
            activeforeground=WHITE,
            relief="flat",
            cursor="hand2",
            padx=14,
            pady=13,
        )
        self.enroll_button.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Button(
            actions,
            text="EXIT",
            command=self.close,
            font=("Segoe UI", 10, "bold"),
            bg="#203750",
            fg=WHITE,
            activebackground="#304b68",
            activeforeground=WHITE,
            relief="flat",
            cursor="hand2",
            padx=18,
            pady=13,
        ).pack(side="left")

    def _build_footer(self):
        footer = tk.Frame(self.root, bg="#041125", height=30)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Label(
            footer,
            text="  INDIAN RAILWAYS   |   PASSENGER SAFETY   |   SEAMLESS TRAVEL   |   DIGITAL INDIA",
            font=("Segoe UI", 8),
            bg="#041125",
            fg=MUTED,
        ).pack(side="left", padx=12, pady=6)
        tk.Label(
            footer,
            text="Manual ticket check required  •  Local prototype QR  ",
            font=("Segoe UI", 8),
            bg="#041125",
            fg=MUTED,
        ).pack(side="right", padx=12, pady=6)

    @staticmethod
    def _passenger_display(record, key, fallback="—"):
        value = record.get(key)
        if value in (None, ""):
            return fallback
        return str(value)

    def _camera_worker(self):
        capture = cv2.VideoCapture(0)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 600)

        candidate_key = None
        candidate_frames = 0
        last_process = 0.0
        gate_until = 0.0
        qr_detector = cv2.QRCodeDetector()
        last_qr_value = None
        qr_passenger = None
        qr_error = ""
        try:
            if not capture.isOpened():
                self._set_state(camera="OFFLINE", face="camera_error", message="Camera is not available")
                return

            self._set_state(camera="ONLINE")
            while not self.stop_event.is_set():
                ok, frame = capture.read()
                if not ok:
                    self._set_state(camera="OFFLINE", face="camera_error", message="Camera stream was interrupted")
                    time.sleep(0.1)
                    continue

                now = time.monotonic()
                boxes = []
                new_state = None
                if now - last_process >= 0.25:
                    last_process = now
                    try:
                        manifest = load_manifest()
                        qr_value, _, _ = qr_detector.detectAndDecode(frame)

                        if qr_value:
                            candidate_key = None
                            candidate_frames = 0
                            if qr_value != last_qr_value:
                                last_qr_value = qr_value
                                qr_passenger, qr_error = redeem_qr_token(qr_value, manifest)
                                if qr_passenger is not None:
                                    save_manifest(manifest)
                                    gate_until = time.monotonic() + 4
                                    qr_error = ""
                                else:
                                    gate_until = 0
                            if qr_passenger is not None:
                                new_state = {
                                    "face": "qr_verified",
                                    "method": "qr",
                                    "message": "One-time kiosk QR ticket verified",
                                    "passenger": qr_passenger,
                                    "progress": 0,
                                    "gate_open": time.monotonic() < gate_until,
                                }
                            else:
                                new_state = {
                                    "face": "qr_invalid",
                                    "method": "qr",
                                    "message": qr_error,
                                    "passenger": None,
                                    "progress": 0,
                                    "gate_open": False,
                                }
                        else:
                            last_qr_value = None
                            qr_passenger = None
                            qr_error = ""
                            scaled = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                            rgb_frame = cv2.cvtColor(scaled, cv2.COLOR_BGR2RGB)
                            locations = face_recognition.face_locations(rgb_frame)
                            encodings = face_recognition.face_encodings(rgb_frame, locations)
                            boxes = [
                                (top * 2, right * 2, bottom * 2, left * 2)
                                for top, right, bottom, left in locations
                            ]

                            if not encodings:
                                candidate_key = None
                                candidate_frames = 0
                                gate_until = 0
                                new_state = {
                                    "face": "no_face",
                                    "message": "Position your face inside the camera frame or scan your QR",
                                    "passenger": None,
                                    "progress": 0,
                                    "gate_open": False,
                                }
                            elif len(encodings) > 1:
                                candidate_key = None
                                candidate_frames = 0
                                gate_until = 0
                                new_state = {
                                    "face": "multiple_faces",
                                    "message": "Please make sure only one passenger is in view",
                                    "passenger": None,
                                    "progress": 0,
                                    "gate_open": False,
                                }
                            else:
                                matches = find_face_matches(encodings[0], manifest)
                                if len(matches) > 1:
                                    candidate_key = None
                                    candidate_frames = 0
                                    gate_until = 0
                                    new_state = {
                                        "face": "duplicate",
                                        "message": "Duplicate face records found; ask staff for help",
                                        "passenger": None,
                                        "progress": 0,
                                        "gate_open": False,
                                    }
                                elif not matches:
                                    candidate_key = None
                                    candidate_frames = 0
                                    gate_until = 0
                                    new_state = {
                                        "face": "not_found",
                                        "message": "No enrolled ticket matched this face; scan your QR or ask staff",
                                        "passenger": None,
                                        "progress": 0,
                                        "gate_open": False,
                                    }
                                else:
                                    passenger = matches[0][0]
                                    key = (
                                        str(passenger.get("pnr", "")),
                                        str(passenger.get("passenger_number", "1")),
                                    )
                                    if key == candidate_key:
                                        candidate_frames += 1
                                    else:
                                        candidate_key = key
                                        candidate_frames = 1
                                        gate_until = 0

                                    if candidate_frames >= 3:
                                        if not passenger.get("boarded", False):
                                            passenger["boarded"] = True
                                            passenger["boarded_time"] = time.strftime(
                                                "%Y-%m-%d %H:%M:%S"
                                            )
                                            passenger["checkin_method"] = "face"
                                            save_manifest(manifest)
                                        if gate_until == 0:
                                            gate_until = time.monotonic() + 4
                                        new_state = {
                                            "face": "verified",
                                            "method": "face",
                                            "message": "Passenger identity and ticket confirmed",
                                            "passenger": passenger,
                                            "progress": 3,
                                            "gate_open": time.monotonic() < gate_until,
                                        }
                                    else:
                                        new_state = {
                                            "face": "verifying",
                                            "method": "face",
                                            "message": "Hold still while we verify your ticket",
                                            "passenger": None,
                                            "progress": candidate_frames,
                                            "gate_open": False,
                                        }
                    except (OSError, RuntimeError, ValueError, KeyError) as error:
                        print(f"[-] Verification error: {error}")
                        new_state = {
                            "face": "error",
                            "message": "Verification problem; please ask staff for help",
                            "passenger": None,
                            "progress": 0,
                            "gate_open": False,
                        }
                        candidate_key = None
                        candidate_frames = 0
                        gate_until = 0
                        last_qr_value = None
                        qr_passenger = None

                with self.state_lock:
                    self.latest_frame = frame
                    if new_state is not None:
                        camera_status = self.state.get("camera", "ONLINE")
                        self.state = {"camera": camera_status, **new_state}
                    if new_state is not None:
                        self.face_boxes = boxes
        finally:
            capture.release()

    def _set_state(self, **updates):
        with self.state_lock:
            self.state.update(updates)

    def _refresh_ui(self):
        if self.stop_event.is_set():
            return

        with self.state_lock:
            frame = None if self.latest_frame is None else self.latest_frame.copy()
            boxes = list(self.face_boxes)
            state = dict(self.state)

        if frame is not None:
            self._draw_face_boxes(frame, boxes, state)
            self._show_frame(frame)
        elif state["camera"] == "OFFLINE":
            self.video_label.configure(
                image="",
                text="CAMERA OFFLINE\n\nCheck your camera connection",
                fg=RED,
            )

        self._update_dashboard(state)
        self.root.after(30, self._refresh_ui)

    @staticmethod
    def _draw_face_boxes(frame, boxes, state):
        color = {
            "verified": (42, 212, 138),
            "verifying": (238, 178, 62),
            "not_found": (54, 133, 255),
            "duplicate": (75, 75, 255),
            "multiple_faces": (75, 75, 255),
        }.get(state["face"], (42, 217, 238))
        for top, right, bottom, left in boxes:
            cv2.rectangle(frame, (left, top), (right, bottom), color, 3)

    def _show_frame(self, frame):
        width = max(self.video_label.winfo_width(), 320)
        height = max(self.video_label.winfo_height(), 240)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(image=image)
        self.video_label.configure(image=self._photo, text="", bg="#020a14")

    def _update_dashboard(self, state):
        camera_value, face_value, ticket_value = (
            self.status_values["camera"][0],
            self.status_values["face"][0],
            self.status_values["ticket"][0],
        )
        camera_value.configure(text=state.get("camera", "OFFLINE"))

        face_state = state.get("face", "waiting")
        labels = {
            "waiting": ("WAITING", AMBER),
            "no_face": ("NO FACE", AMBER),
            "verifying": (f"VERIFYING {state.get('progress', 0)}/3", AMBER),
            "verified": ("MATCHED", GREEN),
            "qr_verified": ("QR VERIFIED", GREEN),
            "qr_invalid": ("INVALID / USED", RED),
            "not_found": ("NO MATCH", RED),
            "duplicate": ("DUPLICATE", RED),
            "multiple_faces": ("MULTIPLE FACES", AMBER),
            "camera_error": ("CAMERA OFFLINE", RED),
            "error": ("CHECK REQUIRED", RED),
        }
        face_text, face_color = labels.get(face_state, ("WAITING", MUTED))
        face_value.configure(text=face_text, fg=face_color)
        self.status_values["face"][1].configure(fg=face_color)

        ticket_text = "VALID" if face_state in {"verified", "qr_verified"} else "WAITING"
        ticket_color = GREEN if face_state in {"verified", "qr_verified"} else MUTED
        if face_state in {"not_found", "qr_invalid", "duplicate", "error"}:
            ticket_text, ticket_color = "CHECK REQUIRED", RED
        ticket_value.configure(text=ticket_text, fg=ticket_color)
        self.status_values["ticket"][1].configure(fg=ticket_color)
        camera_color = GREEN if state.get("camera") == "ONLINE" else RED
        self.status_values["camera"][1].configure(fg=camera_color)
        camera_value.configure(fg=camera_color)

        passenger = state.get("passenger")
        verified = face_state in {"verified", "qr_verified"} and passenger is not None
        method = state.get("method", "face")
        if verified:
            gate_open = state.get("gate_open", False)
            gate_bg = "#103e38" if gate_open else "#15344a"
            gate_color = GREEN if gate_open else CYAN
            gate_text = "GATE STATUS: ACCESS GRANTED" if gate_open else "GATE STATUS: LOCKED"
            gate_message = (
                "•  PASSENGER VERIFIED"
                if gate_open
                else "•  IDENTITY VERIFIED — READY FOR NEXT CHECK"
            )
            self.gate_banner.configure(bg=gate_bg, highlightbackground=gate_color)
            self.gate_icon.configure(bg=gate_bg, fg=gate_color, text="●")
            self.gate_status.configure(bg=gate_bg, fg=gate_color, text=gate_text)
            self.gate_message.configure(bg=gate_bg, fg=WHITE, text=gate_message)
            self.verify_card.configure(bg="#174631")
            verify_title = "✓  QR VERIFIED" if method == "qr" else "✓  FACE VERIFIED"
            self.verify_title.configure(bg="#174631", fg=GREEN, text=verify_title)
            self.verify_subtitle.configure(
                bg="#174631",
                fg="#d1f6df",
                text=state.get("message", "Passenger ticket confirmed"),
            )
            self.instruction_card.configure(bg="#07563e")
            instruction = "QR ACCEPTED — ONE-TIME TICKET" if method == "qr" else "VERIFICATION COMPLETE"
            self.instruction_title.configure(bg="#07563e", text=instruction)
            self.instruction_text.configure(
                bg="#07563e",
                text="Please proceed to the boarding gate" if gate_open else "This ticket has been checked in",
            )
            values = {
                "name": self._passenger_display(passenger, "name"),
                "pnr": self._passenger_display(passenger, "pnr"),
                "train": (
                    f"{self._passenger_display(passenger, 'train_no')} "
                    f"{self._passenger_display(passenger, 'train_name', '')}"
                ).strip(),
                "journey_date": self._passenger_display(passenger, "journey_date"),
                "route": (
                    f"{self._passenger_display(passenger, 'from')} → "
                    f"{self._passenger_display(passenger, 'to')}"
                ),
                "platform": self._passenger_display(passenger, "platform"),
                "seat": (
                    f"{self._passenger_display(passenger, 'coach')} / "
                    f"{self._passenger_display(passenger, 'berth')} "
                    f"({self._passenger_display(passenger, 'berth_type')})"
                ),
            }
        else:
            color = RED if face_state in {"not_found", "duplicate", "error"} else AMBER
            self.gate_banner.configure(bg="#451c2d", highlightbackground="#a6384a")
            self.gate_icon.configure(bg="#451c2d", fg=color, text="●")
            self.gate_status.configure(bg="#451c2d", fg="#ff8a8f", text="GATE STATUS: LOCKED")
            self.gate_message.configure(
                bg="#451c2d",
                fg="#e1c4cb",
                text=f"•  {state.get('message', 'WAITING FOR VERIFICATION').upper()}",
            )
            verify_bg = "#4a2630" if color == RED else "#19334d"
            self.verify_card.configure(bg=verify_bg)
            title = {
                "verifying": f"VERIFYING {state.get('progress', 0)}/3",
                "qr_invalid": "QR REJECTED",
                "not_found": "NOT REGISTERED",
                "duplicate": "STAFF REQUIRED",
                "multiple_faces": "ONE FACE ONLY",
                "camera_error": "CAMERA OFFLINE",
                "error": "CHECK REQUIRED",
            }.get(face_state, "WAITING")
            self.verify_title.configure(bg=verify_bg, fg=color, text=title)
            self.verify_subtitle.configure(
                bg=verify_bg, fg=MUTED, text=state.get("message", "Identity not checked")
            )
            self.instruction_card.configure(bg="#063d78")
            self.instruction_title.configure(
                bg="#063d78",
                text="SCAN YOUR KIOSK QR" if face_state in {"not_found", "qr_invalid"} else "LOOK AT THE CAMERA TO VERIFY",
            )
            self.instruction_text.configure(
                bg="#063d78",
                text=state.get(
                    "message",
                    "Show the one-time QR issued by station staff"
                    if face_state in {"not_found", "qr_invalid"}
                    else "Keep your face clearly visible in the frame",
                ),
            )
            values = {key: "—" for key in self.detail_vars}

        for key, value in values.items():
            self.detail_vars[key].configure(text=value)

    def _open_enrollment(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Manual Passenger Enrollment")
        dialog.geometry("580x760")
        dialog.resizable(False, False)
        dialog.configure(bg=NAVY)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(
            dialog,
            text="ENROLL PASSENGER",
            font=("Segoe UI", 17, "bold"),
            bg=NAVY,
            fg=CYAN,
        ).pack(anchor="w", padx=22, pady=(20, 2))
        tk.Label(
            dialog,
            text="Enter verified ticket details. Face photo is optional for QR-only entry.",
            font=("Segoe UI", 10),
            bg=NAVY,
            fg=MUTED,
        ).pack(anchor="w", padx=22, pady=(0, 14))

        form = tk.Frame(dialog, bg=NAVY)
        form.pack(fill="both", expand=True, padx=22)
        fields = (
            ("PNR (10 digits)", "pnr"),
            ("Passenger number", "passenger_number"),
            ("Passenger name", "name"),
            ("Train number", "train_no"),
            ("Train name", "train_name"),
            ("Journey date", "journey_date"),
            ("From station", "from_station"),
            ("To station", "to_station"),
            ("Platform", "platform"),
            ("Coach", "coach"),
            ("Seat / berth", "berth"),
            ("Berth type", "berth_type"),
        )
        entries = {}
        for row_index, (label, key) in enumerate(fields):
            tk.Label(
                form, text=label, font=("Segoe UI", 9, "bold"),
                bg=NAVY, fg=WHITE, width=18, anchor="w",
            ).grid(row=row_index, column=0, sticky="w", pady=3)
            entry = tk.Entry(
                form, font=("Segoe UI", 10), bg=PANEL_LIGHT,
                fg=WHITE, insertbackground=WHITE, relief="flat",
            )
            entry.grid(row=row_index, column=1, sticky="ew", ipady=5, pady=3)
            entries[key] = entry

        photo_row = len(fields)
        tk.Label(
            form, text="Face photo (optional)", font=("Segoe UI", 9, "bold"),
            bg=NAVY, fg=WHITE, width=18, anchor="w",
        ).grid(row=photo_row, column=0, sticky="w", pady=3)
        photo_path = tk.StringVar()
        photo_entry = tk.Entry(
            form, textvariable=photo_path, font=("Segoe UI", 9),
            bg=PANEL_LIGHT, fg=WHITE, insertbackground=WHITE, relief="flat",
        )
        photo_entry.grid(row=photo_row, column=1, sticky="ew", ipady=5, pady=3)
        form.grid_columnconfigure(1, weight=1)

        def browse_photo():
            selected = filedialog.askopenfilename(
                parent=dialog,
                title="Choose passenger face photo",
                filetypes=(
                    ("Image files", "*.jpg *.jpeg *.png *.bmp"),
                    ("All files", "*.*"),
                ),
            )
            if selected:
                photo_path.set(selected)

        tk.Button(
            form,
            text="Browse",
            command=browse_photo,
            bg="#203750",
            fg=WHITE,
            relief="flat",
            cursor="hand2",
        ).grid(row=photo_row, column=2, padx=(8, 0))

        result = tk.Label(dialog, text="", bg=NAVY, fg=AMBER, font=("Segoe UI", 9))
        result.pack(fill="x", padx=22, pady=(8, 2))

        buttons = tk.Frame(dialog, bg=NAVY)
        buttons.pack(fill="x", padx=22, pady=(4, 18))

        def submit():
            values = {key: entry.get().strip() for key, entry in entries.items()}
            image_path = photo_path.get().strip()
            if any(not value for value in values.values()):
                result.configure(text="Complete all passenger and ticket fields.", fg=AMBER)
                return

            self.enroll_button.configure(state="disabled")
            result.configure(text="Checking face and saving passenger…", fg=CYAN)

            def save_in_background():
                try:
                    qr_path = enroll_passenger(
                        values["pnr"],
                        values["passenger_number"],
                        values["name"],
                        values["train_no"],
                        values["train_name"],
                        values["journey_date"],
                        values["from_station"],
                        values["to_station"],
                        values["platform"],
                        values["coach"],
                        values["berth"],
                        values["berth_type"],
                        image_path,
                    )
                except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
                    self.root.after(0, lambda error=error: on_complete(str(error)))
                else:
                    self.root.after(
                        0, lambda qr_path=qr_path: on_complete(None, qr_path)
                    )

            def on_complete(error, qr_path=None):
                self.enroll_button.configure(state="normal")
                if error:
                    result.configure(text=error, fg=RED)
                else:
                    result.configure(
                        text=f"Enrolled. One-time QR saved at {qr_path}", fg=GREEN
                    )
                    self._show_qr_ticket(qr_path, values["name"])
                    dialog.destroy()

            threading.Thread(target=save_in_background, daemon=True).start()

        tk.Button(
            buttons,
            text="SAVE PASSENGER",
            command=submit,
            bg=BLUE,
            fg=WHITE,
            activebackground="#1489e7",
            activeforeground=WHITE,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            padx=18,
            pady=10,
        ).pack(side="left")
        tk.Button(
            buttons,
            text="CANCEL",
            command=dialog.destroy,
            bg="#203750",
            fg=WHITE,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            padx=18,
            pady=10,
        ).pack(side="right")

    def _show_qr_ticket(self, qr_path, passenger_name):
        image = Image.open(qr_path).convert("RGB")
        image.thumbnail((280, 280), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image=image)

        dialog = tk.Toplevel(self.root)
        dialog.title("One-time kiosk QR ticket")
        dialog.geometry("360x430")
        dialog.configure(bg=NAVY)
        dialog.transient(self.root)
        tk.Label(
            dialog,
            text="ONE-TIME KIOSK QR",
            font=("Segoe UI", 15, "bold"),
            bg=NAVY,
            fg=CYAN,
        ).pack(pady=(18, 4))
        tk.Label(
            dialog,
            text=passenger_name,
            font=("Segoe UI", 10, "bold"),
            bg=NAVY,
            fg=WHITE,
        ).pack()
        qr_label = tk.Label(dialog, image=photo, bg=WHITE, padx=8, pady=8)
        qr_label.image = photo
        qr_label.pack(pady=12)
        tk.Label(
            dialog,
            text="Scans once at this kiosk. Keep the QR private.",
            font=("Segoe UI", 9),
            bg=NAVY,
            fg=MUTED,
        ).pack(pady=(0, 4))
        tk.Label(
            dialog,
            text=str(qr_path),
            wraplength=330,
            font=("Segoe UI", 8),
            bg=NAVY,
            fg=MUTED,
        ).pack(padx=12)
        tk.Button(
            dialog,
            text="DONE",
            command=dialog.destroy,
            bg=BLUE,
            fg=WHITE,
            relief="flat",
            padx=26,
            pady=8,
        ).pack(pady=12)

    def close(self):
        self.stop_event.set()
        self.root.destroy()


def run_railway_kiosk():
    root = tk.Tk()
    RailwayKiosk(root)
    root.mainloop()


if __name__ == "__main__":
    run_railway_kiosk()
