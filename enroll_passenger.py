import re
import sys
from pathlib import Path

import face_recognition

from railway_data import (
    encrypt_embedding,
    find_face_matches,
    issue_qr_token,
    load_manifest,
    save_qr_ticket,
    save_manifest,
)

PNR_PATTERN = re.compile(r"^\d{10}$")


def enroll_passenger(
    pnr,
    passenger_number,
    name,
    train_no,
    train_name,
    journey_date,
    from_station,
    to_station,
    platform,
    coach,
    berth,
    berth_type,
    image_path="",
):
    pnr = str(pnr).strip()
    passenger_number = str(passenger_number).strip()
    if not PNR_PATTERN.fullmatch(pnr):
        raise ValueError("PNR must contain exactly 10 digits.")

    manifest = load_manifest()
    if any(
        str(record.get("pnr", "")).strip() == pnr
        and str(record.get("passenger_number", "1")).strip() == passenger_number
        for record in manifest
    ):
        raise ValueError(
            f"Passenger {passenger_number} for PNR {pnr} is already enrolled."
        )

    face_encoding = None
    if image_path.strip():
        image_file = Path(image_path).expanduser()
        if not image_file.is_file():
            raise FileNotFoundError(f"Image file not found: {image_file}")

        image = face_recognition.load_image_file(str(image_file))
        encodings = face_recognition.face_encodings(image)
        if len(encodings) != 1:
            raise ValueError(
                f"Expected exactly one face in the image; detected {len(encodings)}."
            )

        duplicate_matches = find_face_matches(encodings[0], manifest)
        if duplicate_matches:
            existing_pnr = str(duplicate_matches[0][0].get("pnr", "unknown"))
            raise ValueError(
                "This face is already enrolled "
                f"(existing PNR ending {existing_pnr[-4:]}). "
                "The database was not changed."
            )
        face_encoding = encodings[0]

    qr_token, qr_token_hash = issue_qr_token()
    record = {
        "pnr": pnr,
        "passenger_number": passenger_number,
        "name": name,
        "train_no": train_no,
        "train_name": train_name,
        "journey_date": journey_date,
        "from": from_station,
        "to": to_station,
        "platform": platform,
        "coach": coach,
        "berth": berth,
        "berth_type": berth_type,
        "booking_status": "Manually entered",
        "current_status": "Manually entered",
        "departure_window_valid": True,
        "boarded": False,
        "qr_token_hash": qr_token_hash,
    }
    if face_encoding is not None:
        record["encrypted_biometric"] = encrypt_embedding(face_encoding.tolist())

    manifest.append(record)
    qr_path = save_qr_ticket(qr_token, record)
    try:
        save_manifest(manifest)
    except OSError:
        qr_path.unlink(missing_ok=True)
        raise

    checkin_type = "face + QR" if face_encoding is not None else "QR only"
    print(f"[+] {name} enrolled ({checkin_type}). QR saved to: {qr_path}")
    return qr_path


def required_input(prompt):
    value = input(prompt).strip()
    if not value:
        raise ValueError("All passenger details are required.")
    return value


def main():
    print("--- MANUAL PASSENGER ENROLLMENT ---")
    try:
        pnr = required_input("10-digit PNR: ")
        passenger_number = required_input("Passenger number on this PNR (e.g. 1): ")
        name = required_input("Passenger name: ")
        train_no = required_input("Train number: ")
        train_name = required_input("Train name: ")
        journey_date = required_input("Journey date: ")
        from_station = required_input("From station: ")
        to_station = required_input("To station: ")
        platform = required_input("Platform (or enter TBA): ")
        coach = required_input("Coach: ")
        berth = required_input("Seat/berth number: ")
        berth_type = required_input("Berth type: ")
        image_path = input(
            "Passenger face image path (leave blank for QR-only ticket): "
        ).strip()

        qr_path = enroll_passenger(
            pnr,
            passenger_number,
            name,
            train_no,
            train_name,
            journey_date,
            from_station,
            to_station,
            platform,
            coach,
            berth,
            berth_type,
            image_path,
        )
        print(f"Show this one-time kiosk QR to the scanner: {qr_path}")
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        print(f"[-] Enrollment failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
