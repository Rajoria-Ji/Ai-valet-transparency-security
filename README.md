# AI Valet Transparency & Security


A valet management and vehicle security platform. It gives car owners a live view of where their vehicle is, ties every handoff to a specific valet, and uses the lot's CCTV cameras to flag a car that moves when it shouldn't.In normal valet parking, you give your keys to someone, get a paper slip, and then you know nothing. You can't tell if your car is parked, if someone is driving it around, or how long it will take to come back. The parking manager also has no proof of who handled which car, so if there's a scratch or a complaint, it becomes one person's word against another's.

## Contents:

The problem
What it does
How it works
Tech stack
Getting started
Configuration
API reference
Data model
Testing
Security and privacy
Performance targets
Operations
Known limitations
Project status
Team
References

## The problem:

Valet parking runs on paper tags and informal key handoffs. Once the keys are gone, the owner has no information at all: is the car parked, is someone driving it around, how long will retrieval take? Supervisors have the same blind spot. There is no reliable record of who handled which car, so a scratch or a joyride turns into a dispute with nothing to settle it.

Existing products (FlashParking, SpotHero and similar) are good at ticketing, reservations and payments, but they don't watch what happens to the car after the handoff. This project fills that gap with custody tracking, camera-based movement alerts and an audit trail that is hard to alter after the fact.

## What it does:

Digital check-in. Staff register a vehicle with plate, model, colour and the owner's phone number. The system issues a unique token as a QR code and short link. The check-in form is deliberately limited to three core fields, based on feedback from early testers.

Custody assignment. Every parking or retrieval job is assigned to a named valet. At any moment the system can say who is responsible for a given car.

Geofence monitoring. YOLO detects vehicles in camera frames, and OpenCV checks whether each tracked vehicle's centroid is still inside its allowed polygon. If it leaves, an alert is raised and shown on the supervisor console.

Pre-arrival summon. The customer opens their link and taps "Summon My Car", optionally with an ETA. The assigned valet is notified straight away, so the car is waiting at the curb instead of the customer waiting for it.

Masked audit log. Check-ins, assignments, geofence events and retrievals are written to an append-only log. Phone numbers and partial plates are masked before they are stored.

Supervisor console. Lot occupancy, live camera feed with detection overlay, and the alert stream, in one place.

## Vehicle lifecycle:

CHECKED_IN -> IN_TRANSIT -> PARKED -> RETRIEVAL_REQUESTED -> COMPLETED

## How it works:
 Customer portal     Valet dispatch view     Supervisor console
        \                    |                     /
         \                   |                    /
          +------------ FastAPI backend ---------+
                      |        |         |
          Vehicle mgmt   Alert dispatch   Computer vision workers
                      |        |         |   (OpenCV + YOLO)
                      +--- SQLite / PostgreSQL ---+
                           + append-only audit log
                                      ^
                                      |
                              CCTV / recorded feeds

The client is a responsive web app with three views (customer, valet, supervisor). No native app is required. The backend is an async FastAPI service. Vision workers read camera frames, detect and track vehicles, and run the geofence check. Violations go through an alert dispatcher to the supervisor dashboard. Storage is SQLite while prototyping and PostgreSQL for anything beyond that, plus an append-only audit store.


## Tech stack:
Layer	Technology
Backend	Python, FastAPI
Database	SQLite (dev), PostgreSQL (target), Alembic or raw SQL migrations
Computer vision	OpenCV, Ultralytics YOLO
Frontend	HTML5, CSS, JavaScript / React
Auth	JWT, role-based access control
Realtime	WebSocket or polling
Testing	PyTest, Requests, Postman
Tooling	Git, GitHub, linting and unit tests before merge

## Getting started
Prerequisites
Python 3.10 or newer
Git
A GPU is helpful for the vision pipeline but not required for development, since a recorded video loop can stand in for a live camera
Installation
bash
git clone <repository-url>
cd <repository-folder>

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env              # then edit .env
Running
bash
# backend
uvicorn main:app --reload

# vision worker (uses the video source set in .env)
python -m vision.worker

The module paths above are placeholders. Match them to the actual layout of the repo.

By default the app uses SQLite and a looped test video, so you can run the whole flow on a laptop without any camera hardware.

### Configuration:

All settings come from environment variables, loaded from .env. Keep separate files for development and production, and never commit them.

Variable	Purpose
DATABASE_URL	SQLite or PostgreSQL connection string
JWT_SECRET	Signing key for access tokens. Rotate it periodically
JWT_EXPIRE_MINUTES	Lifetime of staff tokens. Keep it short
VIDEO_SOURCE	RTSP URL, camera index, or path to a recorded video
GEOFENCE_CONFIG	Path to the zone polygons / ROI definitions
YOLO_MODEL	Model weights to load (a nano variant is the default choice)

Variable names may differ slightly in the code, so check .env.example.

### API reference

Base path: /api/v1

Endpoint	Method	Auth	Purpose
/vehicles/check-in	POST	Staff JWT	Register an incoming vehicle
/valet/assign	POST	Supervisor JWT	Assign a valet to a vehicle
/customer/request-pickup	POST	Token secret	Request the vehicle ahead of arrival
/security/alerts	GET	Supervisor JWT	Query geofence and movement alerts

### Check-in

POST /api/v1/vehicles/check-in
{ "plate": "...", "model": "...", "color": "...", "owner_phone": "..." }

201 -> { "token_id": "...", "qr_url": "...", "status": "CHECKED_IN" }
400 invalid input, 401 unauthenticated

### Assign valet

POST /api/v1/valet/assign
{ "vehicle_id": "...", "worker_id": "VALET-0001", "target_slot": "..." }

200 -> { "assignment_id": "...", "assigned_at": "..." }
404 vehicle or worker not found

### Request pickup

POST /api/v1/customer/request-pickup
{ "token_id": "...", "eta_minutes": 10 }

200 -> { "retrieval_status": "...", "queue_pos": 2 }
400 invalid token or state

### Alerts

GET /api/v1/security/alerts?severity=...&time_from=...&limit=...

200 -> { "alerts": [ ... ], "total": 0 }
403 insufficient role

## Data model
Entity	Notable fields
Vehicle	id (UUID), plate_number (indexed), status
ValetWorker	worker_id (format VALET-XXXX)
SecurityAlert	alert_type: ZONE_BREACH, JOYRIDE_SPEED, EXTENDED_IDLE
AuditLog	masked_payload (PII-sanitised, immutable)

Foreign keys enforce the links between tickets, vehicles and valets. Schema changes go through version-controlled migrations.

## Testing
bash
pytest
Area	Approach	Target
Backend services	Unit and integration (PyTest, Requests)	75% or higher coverage, zero P1/P2 failures
Vision pipeline	Functional and benchmark runs on recorded feeds	Over 90% recall on boundary breaches
Audit and security	Sanitisation and load tests (PyTest, Postman)	Zero plaintext sensitive data in logs

The vision pipeline is evaluated on recorded footage of typical valet activity: drop-off, entering authorised bays, and staged movements outside the geofence. We look at bounding-box precision, centroid tracking stability and alert speed.

## Security and privacy
Roles. Customers get read-only access through their token. Valets can update status. Supervisors have full access to configuration and logs.
Tokens. Customer tokens are cryptographically random, and the valet still checks the customer visually at handover, so a leaked link alone can't take a car.
Staff auth. Short-lived JWTs with a rotating signing key.
Audit log. Append-only database roles and hash chaining, so edits after the fact are detectable.
PII. Owner phone numbers and partial plates are masked or hashed before they are written to persistent or public-facing logs. Example: +91-XXXXX-12345.
Video. Frames are discarded right after centroid analysis. Telemetry logs are kept for 90 days.
Secrets. Loaded from environment variables and git-ignored.
Camera outage. A local heartbeat watchdog sends an offline alert to the manager immediately if a stream goes dark.
Backups. Daily database snapshots, RTO of 2 hours or less, RPO of 12 hours or less.

## Performance targets
Metric	Target
Median check-in and token issue	Under 30 s end to end
Token generation	Under 1 s
Geofence alert latency (p95)	Under 5 s
API latency (p95)	Under 500 ms
Vision inference	15 FPS or higher
Availability	99.0% or higher
HTTP 5xx rate	1.0% or lower
Curbside wait for summoned cars	At least 70% lower than the walk-up case

## Operations

Alerts

Condition	Threshold	Goes to
Dropped video frames	Over 20%	Team lead
Unauthorised zone breach	1 or more events	Supervisor dashboard, with sound
API latency (p95)	Over 1200 ms	Backend lead

Perimeter breach. The console shows a blinking red indicator with the plate. The supervisor confirms on the camera feed, then dispatches on-duty valet security by radio.

Stream throttling. If inference drops below 10 FPS, reduce the processing resolution and skip alternate background frames while keeping centroid bounding boxes.

Releases. Merges to main require passing lint and unit tests. Rollbacks use Git tags and pinned environment lockfiles.

## Known limitations
Poor lighting and heavy shadows can cause false positives. Zone alarms need confirmation across several frames before firing.
Running YOLO on high-resolution streams is slow. Frames are downscaled to 640x640 and a nano-size model is preferred.
Occluded cameras and low light affect tracking accuracy.
Some customers won't open links on their phones, so QR cards and short URLs are provided and no app install is needed.

Out of scope for v1: autonomous driving or CAN-bus access, OBD-II sensor hardware, native iOS/Android apps, payment and toll integration, and municipal traffic enforcement integration.

## Project status

v1.0 prototype, in active development on an 8-week plan.

Week	Focus	Status
1	Requirements and scope	Done
2	Architecture and database	Planned
3	Worker and ticket module	Planned
4	Vision engine and geofence v1	Planned
5	Customer UI and retrieval	Planned
6	Admin monitoring UI	Planned
7	Hardening and masking	Planned
8	Release and defense	Planned
Team
Name	Role
Sumit Rajoria	Team lead, AI architect, vision pipeline
Dhairya Goyal	Backend and full-stack lead
Satyarth Dahiya	Security, QA and documentation

## Mentor:
Shivanshu Upadhyay Department of Computer Science Engineering & Applications (AI & ML), GLA University, Mathura.

References
Ultralytics YOLO documentation
OpenCV documentation
FastAPI documentation
IEEE, "Computer Vision Systems for Smart Parking Management and Automated Surveillance"
License

Academic project. Add a license here if you plan to open-source
