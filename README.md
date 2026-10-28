# AI Valet Transparency & Security

A local prototype for tracking valet vehicle handoffs. The current app runs on one Mac and uses Python's standard library with SQLite.

## What works now

- Staff sign in as a supervisor or valet.
- Staff check in vehicles with a plate, model, color, and optional parking slot.
- A valet can be assigned to each vehicle.
- Status moves through `CHECKED_IN`, `IN_TRANSIT`, `PARKED`, `RETRIEVAL_REQUESTED`, and `COMPLETED`.
- Every check-in, assignment, pickup request, photo, and status change appears in the activity history.
- A customer can use a pickup link to request the car and optionally enter an ETA.
- PNG or JPEG inspection photos can be added at check-in and handover. Each photo must be 4 MB or smaller.
- The supervisor dashboard has search, status filters, daily counts, staff account creation, and open pickup alerts.

## Run the app

Python 3.10 or newer is required. The local app does not need any packages from `requirements.txt`; that file lists packages for planned project work.

Open Terminal and run:

```bash
cd ~/Desktop/Ai-valet-transparency-security
python3 app.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser. Keep the Terminal window open while using the app. Press **Control+C** in Terminal to stop it.

If port 8000 is already in use, start the app on port 8001 instead:

```bash
python3 app.py --port 8001
```

Then open [http://127.0.0.1:8001](http://127.0.0.1:8001).

## Team code split

The app is split into three files so each teammate can take one area:

1. `valet_data.py` — database, sign-in, vehicle records, photos, and audit events.
2. `valet_pages.py` — the HTML screens and dashboard display.
3. `app.py` — web routes and the command used to start the app.

These files work together, so all three must be in the same project folder in the shared repository. Keep the existing `audit_logger.py` beside them too; it is a shared helper used by `valet_data.py`. `README.md` and `.gitignore` should stay in the repository as shared project files. Once the files are together, start the app with `python3 app.py`.

## Demo sign-in

The first time the app creates a database, it adds these accounts:

| Role | Username | Password |
|---|---|---|
| Supervisor | `supervisor` | `supervisor-demo` |
| Valet | `valet` | `valet-demo` |

Change the password after signing in. If a password has already been changed, use the new one. Do not delete the database to recover access; that would remove saved vehicles and history.

Supervisors can see and manage all vehicles, assign valets and parking slots, add staff accounts, and view daily counts and pickup alerts. Valets see vehicles assigned to them and can move those vehicles through the workflow. A valet who checks in a vehicle is assigned to it automatically.

## Customer pickup links

Each checked-in vehicle gets a random pickup link. The supervisor can create a replacement link from the vehicle details. A customer can request pickup once the vehicle is marked `PARKED`.

The app listens only on this Mac at `127.0.0.1`. The pickup link therefore works only in a browser on this Mac; it will not open on a customer's phone. A phone-accessible link needs a deployed HTTPS site. QR codes, SMS, and WhatsApp messages are not connected.

## Local files and privacy

- Vehicle records and staff accounts: `instance/valet_demo.sqlite3`
- Sign-in secret: `instance/session_secret`
- Inspection photos: `instance/uploads/`
- Audit events: `logs/audit_log.jsonl`

The app creates these files automatically. Keep them on this Mac and use sample data. Vehicle plates and photos are stored locally in the database and uploads folder. Audit events omit plates and pickup-link tokens. Staff passwords are stored as salted hashes.

## Planned work

The following are project goals, not working features in this local prototype:

- GPS tracking and geofence alerts
- CCTV monitoring and YOLO vehicle detection
- QR-code generation
- Text or WhatsApp notifications
- A customer site that can be reached from a phone
- A FastAPI service, PostgreSQL deployment, and production hosting

The architecture and feature descriptions elsewhere in the project documents may describe these planned features. They should not be treated as implemented code.
