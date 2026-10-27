import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import time

import numpy as np
import qrcode
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AES_KEY = b'12345678901234567890123456789012'
DB_FILE = Path(__file__).resolve().with_name("railway_manifest.json")
FACE_MATCH_THRESHOLD = 0.55
QR_PREFIX = "RAILWAY-KIOSK-QR:1:"


def encrypt_embedding(vector):
    data = json.dumps(vector).encode("utf-8")
    nonce = os.urandom(12)
    ciphertext = AESGCM(AES_KEY).encrypt(nonce, data, None)
    return {
        "nonce": base64.b64encode(nonce).decode("utf-8"),
        "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
    }


def decrypt_embedding(payload):
    try:
        nonce = base64.b64decode(payload["nonce"], validate=True)
        ciphertext = base64.b64decode(payload["ciphertext"], validate=True)
        decrypted = AESGCM(AES_KEY).decrypt(nonce, ciphertext, None)
        vector = np.asarray(json.loads(decrypted.decode("utf-8")), dtype=float)
        if vector.shape != (128,):
            raise ValueError("Expected a 128-value face embedding")
        return vector
    except (InvalidTag, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"[-] Invalid encrypted face record: {error}")
        return None


def find_face_matches(embedding, manifest, threshold=FACE_MATCH_THRESHOLD):
    matches = []
    for record in manifest:
        payload = record.get("encrypted_biometric")
        if not isinstance(payload, dict):
            continue

        saved_embedding = decrypt_embedding(payload)
        if saved_embedding is None:
            continue

        distance = float(np.linalg.norm(saved_embedding - embedding))
        if distance < threshold:
            matches.append((record, distance))

    return sorted(matches, key=lambda match: match[1])


def issue_qr_token():
    token = QR_PREFIX + secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return token, token_hash


def save_qr_ticket(token, record):
    pnr_suffix = re.sub(r"\D", "", str(record.get("pnr", "")))[-4:] or "ticket"
    passenger = re.sub(
        r"[^A-Za-z0-9_-]", "_", str(record.get("passenger_number", "1"))
    )
    token_id = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
    output_dir = DB_FILE.parent / "qr_tickets"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"ticket_{pnr_suffix}_{passenger}_{token_id}.png"
    qrcode.make(token).save(output_path)
    return output_path


def redeem_qr_token(token, manifest):
    if not isinstance(token, str) or not token.startswith(QR_PREFIX):
        return None, "This is not a kiosk-issued QR ticket."

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    for record in manifest:
        stored_hash = record.get("qr_token_hash")
        if not isinstance(stored_hash, str) or not hmac.compare_digest(
            stored_hash, token_hash
        ):
            continue

        if record.get("boarded", False):
            return None, "This QR ticket has already been used."

        record["boarded"] = True
        record["boarded_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        record["checkin_method"] = "qr"
        return record, ""

    return None, "QR ticket is not registered at this kiosk."


def load_manifest():
    if not DB_FILE.exists():
        return []

    try:
        manifest = json.loads(DB_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Manifest is not valid JSON: {DB_FILE}") from error

    if not isinstance(manifest, list):
        raise ValueError(f"Manifest must contain a JSON list: {DB_FILE}")
    return manifest


def save_manifest(manifest):
    DB_FILE.write_text(
        json.dumps(manifest, indent=4),
        encoding="utf-8",
    )
