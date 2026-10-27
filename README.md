# Face Recognition-Based Biometric Check-In System for Indian Railways

**BCA academic prototype — simulation only**

This repository demonstrates a passenger enrollment screen and a webcam-based kiosk that compares a detected face with enrolled face embeddings. It is **not connected to IRCTC/CRIS**, does not verify real PNRs, does not retrieve live train/platform data, and does not control a physical railway gate.

## Features in this prototype

- Streamlit enrollment form for synthetic passenger/travel details.
- Webcam capture and basic image-quality / face-count checks during enrollment.
- Face embeddings generated with `face_recognition` and `dlib`.
- AES-256-GCM encryption for stored embeddings.
- HMAC-based opaque passenger token.
- SQLite persistence and a simulated local station cache.
- OpenCV webcam kiosk with a configurable face-match threshold.
- Simulated operator decision and boarding status logging.

> **Important:** Basic face detection and image-quality checks are not liveness detection. This project is for classroom demonstration only. Do not use real passenger data or use it to make real-world access-control decisions.

## Project files

| File | Purpose |
|---|---|
| `app_irctc_enroll.py` | Streamlit passenger enrollment UI |
| `station_kiosk_gate.py` | OpenCV webcam kiosk simulation |
| `security_vault.py` | SQLite persistence, AES-GCM encryption, HMAC tokenization and event logging |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Excludes virtual environments, local databases, secrets and cache files from Git |

## Requirements

- Windows 10/11 (commands below use PowerShell)
- Python **3.11, 64-bit** recommended for this dependency set
- Webcam
- Git (only needed for Git command-line upload)
- `face_recognition` requires `dlib`. On Windows, installing `dlib` from source may require Visual Studio C++ Build Tools. If this is difficult, use a compatible prebuilt setup or ask your instructor before changing the recognition library.

## 1. Download or clone the repository

If you downloaded the ZIP, extract it and open PowerShell in the extracted project folder.

If you are cloning from GitHub:

```powershell
git clone https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
cd YOUR-REPOSITORY
```

Replace the URL with your own repository URL.

## 2. Create and activate a virtual environment (recommended)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
```

If PowerShell blocks activation, run this only for the current terminal session, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

You should see `(.venv)` at the beginning of the PowerShell prompt.

## 3. Install dependencies

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

If installation fails at `dlib`, check the final error lines. On Windows it may require **Visual Studio Build Tools → Desktop development with C++**, including MSVC x64/x86 build tools and a Windows SDK. Do not run `pip install cv2`; the package name is `opencv-python`, while the import name is `cv2`.

Check imports:

```powershell
python -c "import cv2, face_recognition, numpy, cryptography, streamlit; print('Imports OK')"
```

## 4. Configure encryption keys

For repeatable testing, create two independent keys and set them in the same PowerShell session before launching either app. Keep the values private; never commit them to GitHub.

Generate the first key:

```powershell
python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Copy the printed value and set it (replace the placeholder):

```powershell
$env:BIOMETRIC_AES_KEY = "PASTE_FIRST_KEY_HERE"
```

Generate a second independent key using the same Python command, then set it:

```powershell
$env:BIOMETRIC_TOKEN_KEY = "PASTE_SECOND_KEY_HERE"
$env:RAILWAY_DB_PATH = "railway_biometric.db"
```

These environment variables apply to the current PowerShell session. If you open a new terminal, set them again. If keys are lost, encrypted records created with those keys may no longer be decryptable. Never publish real keys or use real passenger information.

## 5. Run the enrollment app

Open PowerShell in the project directory, activate `.venv`, set the environment variables above, then run:

```powershell
streamlit run app_irctc_enroll.py
```

Streamlit will show a local URL (usually `http://localhost:8501`). Use synthetic/demo passenger data only. Allow browser access to the webcam if requested.

## 6. Run the kiosk simulation

Open a **second** PowerShell window in the same project directory. Activate the same virtual environment and set the **same** `BIOMETRIC_AES_KEY`, `BIOMETRIC_TOKEN_KEY`, and `RAILWAY_DB_PATH` values. Then run:

```powershell
python station_kiosk_gate.py
```

Kiosk keyboard controls shown in the window:

- `R` — refresh simulated station cache
- `Y` — simulate operator-approved grant (not real identity assurance or gate actuation)
- `N` — deny the simulated grant
- `Q` — quit

Both programs must use the same database path and encryption keys for the demo records to be readable by the kiosk.

## Troubleshooting

### `ModuleNotFoundError: No module named 'cv2'`

Activate the correct `.venv`, then run:

```powershell
python -m pip install opencv-python
```

### `ModuleNotFoundError: No module named 'face_recognition'`

Make sure the correct virtual environment is active and install dependencies with `python -m pip install -r requirements.txt`. `face_recognition` depends on `dlib`, which may fail to compile on Windows without C++ build tools.

### `face_recognition_models` warning

Install dependencies in the same environment that runs the app. If needed, try:

```powershell
python -m pip install git+https://github.com/ageitgey/face_recognition_models
```

### `Cache records: 0` / unauthorized screen

The kiosk cache may be empty, no passenger may have been enrolled, or the two processes may be using different database paths or keys. Enroll a synthetic test passenger, ensure both processes share the same environment variables and database file, then press `R` in the kiosk.

### Webcam does not open

Close other apps using the camera. If necessary, set a different camera index before launching:

```powershell
$env:CAMERA_INDEX = "1"
python station_kiosk_gate.py
```

## Security and limitations

- Raw enrollment images are processed in memory by this prototype and are not intentionally saved as image files by the app.
- Embeddings are encrypted using AES-256-GCM with a fresh nonce; keys must be kept outside the repository.
- HMAC tokenization is **not** a formal zero-knowledge proof.
- The project does not implement official railway API integration, TLS/mTLS, a secrets manager, production access controls, validated anti-spoofing, or physical gate control.
- The cache is a local simulation, not a trusted live departure manifest.
- The threshold is a demo setting and must not be treated as a validated biometric security threshold.
- Before any real deployment, the system would require lawful authorization, consent, privacy/security review, robust presentation-attack detection, formal performance evaluation, and integration with approved railway systems.

## Upload this project to GitHub

### Option A — GitHub website (no Git commands required)

1. Sign in at [GitHub](https://github.com/) and click **New repository**.
2. Give it a name, for example `railway-biometric-checkin`.
3. Choose **Public** or **Private**. For a college project, Private is a reasonable default until your guide approves publication.
4. Do not add a README or `.gitignore` on GitHub if you are uploading this folder that already contains them.
5. Create the repository.
6. On the new repository page, choose **Add file → Upload files**.
7. Upload `app_irctc_enroll.py`, `station_kiosk_gate.py`, `security_vault.py`, `requirements.txt`, `README.md`, and `.gitignore`.
8. Check the file list before committing. Do **not** upload `.venv`, database files (`*.db`, `*.sqlite*`), `.env` files, API keys, generated face data, or personal passenger data.
9. Enter a commit message such as `Add railway biometric check-in prototype` and click **Commit changes**.

### Option B — Git command line

Install Git from [git-scm.com](https://git-scm.com/download/win) if needed. Open PowerShell in the project folder and run:

```powershell
git init
git add .
git status
git commit -m "Add railway biometric check-in prototype"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

Replace `YOUR-USERNAME` and `YOUR-REPOSITORY` with your actual GitHub username and repository name. Review `git status` before committing. If Git asks you to configure a name/email, use the identity you want associated with your commits:

```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

If you already added a remote, check it with `git remote -v` instead of adding it again.

## Suggested repository description

`Academic prototype for railway passenger check-in using Python, OpenCV, face embeddings, encrypted local storage, and a simulated station kiosk.`

## License

No license is included. Add a license only after confirming your team/guide permits it and agreeing on the license terms.
