# Public Grievance Management System

A civic-tech platform for citizens to submit grievances and track their resolution
by the responsible government department and officer — with identity protection,
a tamper-evident audit trail, and AI-assisted triage planned for later stages.

> **Status:** Steps 1–8 of 12 complete — Project Foundation through Tamper-Evident
> Audit Trail. See [docs/architecture.md](docs/architecture.md) for the full 12-step
> roadmap and the authentication/grievance-submission/tracking/privacy/routing/
> officer/audit architecture.
>
> **Note on build order:** Step 6 (Citizen Identity Protection) was mistakenly built before
> Step 5 (Department Auto-Routing). This has been corrected — Step 5 is now implemented and
> integrates with Step 6's privacy system without duplicating or bypassing it — but migration
> numbers reflect actual build order, not step order (Step 6 is migration `0005`, Step 5 is
> migration `0006`, Step 7 is migration `0007`, Step 8 is migration `0008`). See
> docs/architecture.md section 7j for the
> full explanation.

## Technology Stack

| Layer      | Technology                                      |
|------------|--------------------------------------------------|
| Frontend   | React, Vite, JavaScript, modern CSS, react-router-dom |
| Backend    | Python, FastAPI, SQLAlchemy, Alembic, PyJWT, Argon2 (passlib) |
| Database   | PostgreSQL                                        |
| Dev/Infra  | Docker, docker-compose, `.env` configuration       |

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- PostgreSQL 14+ (or Docker, to run it in a container)
- Docker & docker-compose (optional but recommended)

## Project Structure

```
public-grievance-system/
├── backend/        FastAPI application, models, migrations, tests
├── frontend/        React + Vite application
├── docs/               Architecture documentation
├── docker-compose.yml
└── README.md
```

## Environment Setup

Copy the example env files and fill in real values:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

`backend/.env` requires:

```
# --- Application ---
APP_ENV=development
APP_NAME=Public Grievance Management System

# --- Database ---
DATABASE_URL=postgresql://pgms_user:pgms_password@localhost:5432/pgms_db

# --- Security / JWT ---
# Generate a strong random value before use, e.g. `openssl rand -hex 32`
SECRET_KEY=change_this_to_a_long_random_secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# --- CORS ---
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# --- File uploads (Step 3) ---
UPLOAD_DIR=uploads
MAX_ATTACHMENT_SIZE_MB=10
```

`frontend/.env` requires:

```
VITE_API_BASE_URL=http://localhost:8000
```

Never commit `.env` files — only `.env.example` is tracked in git.

## Option A: Run Everything with Docker

```bash
docker-compose up --build
```

This starts PostgreSQL (with a persistent volume) and the backend API on
`http://localhost:8000`. Run the frontend locally with Vite (see below) —
it talks to the backend over HTTP.

## Option B: Run Locally Without Docker

### 1. PostgreSQL Setup

Create the database and user (adjust to match your `backend/.env`):

```sql
CREATE USER pgms_user WITH PASSWORD 'pgms_password';
CREATE DATABASE pgms_db OWNER pgms_user;
```

### 2. Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run Database Migrations

```bash
cd backend
alembic upgrade head
```

This applies the Step 1 foundation tables, the Step 2 `refresh_tokens` table, the
Step 3 `categories` / `grievances` / `attachments` tables (with 10 seed categories),
the Step 4 `grievance_status_history` table (with automatic backfill of an initial
SUBMITTED history record for any grievance that predates Step 4), the Step 6
`privacy_mode` column / `privacy_access_logs` / `identity_reveal_requests` tables
(migration `0005`), the Step 5 `grievance_assignments` table plus department
seed data and category→department mappings (migration `0006`), the Step 7
`officer_assignments` table (migration `0007`), and the Step 8 `audit_logs`
table (migration `0008` — the migration numbers reflect actual build order,
not step order; see docs/architecture.md). Existing grievances are
automatically backfilled with routing based on their category's department
mapping.

Other useful Alembic commands:

```bash
alembic revision --autogenerate -m "description of change"   # generate a new migration
alembic downgrade -1                                          # roll back one migration
alembic current                                                # show current DB revision
```

### 4. Start the Backend

```bash
cd backend
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`, with interactive docs at
`http://localhost:8000/docs`.

### 5. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

The app will be available at `http://localhost:5173`, with `/login`, `/register`,
`/complaints/new` (file a complaint), `/complaints` (your complaints), and
`/complaints/:grievanceNumber` (complaint detail with status timeline) pages.

## Authentication (Step 2)

- `POST /api/auth/register` — create a citizen account (name, email, phone, password).
  Public registration always creates `user_type=citizen`; any `user_type` sent by the
  client is ignored.
- `POST /api/auth/login` — authenticate with email/password. Returns a short-lived
  access token in the response body and sets a refresh token as an HttpOnly cookie.
- `POST /api/auth/refresh` — exchange the refresh-token cookie for a new access token
  (refresh tokens rotate on every use).
- `POST /api/auth/logout` — revoke the current refresh token server-side.
- `GET /api/auth/me` — return the authenticated user's own profile
  (`Authorization: Bearer <access_token>` required).

See [docs/architecture.md](docs/architecture.md) for the full JWT/refresh-token flow,
token storage strategy, and security decisions.

## Grievance Submission (Step 3)

- `GET /api/categories` — list active complaint categories (no auth required; used to
  populate the category dropdown so the frontend never hardcodes categories).
- `POST /api/grievances` — citizen-only. Creates a grievance; `citizen_id` is always
  derived from the authenticated JWT, never accepted from the client. Returns a
  server-generated `grievance_number` (e.g. `GRV-2026-000001`) with `status=SUBMITTED`.
- `GET /api/grievances/my` — citizen-only. Returns only the authenticated citizen's
  own grievances.
- `GET /api/grievances/{grievance_number}` — citizen-only. Returns 404 if the
  grievance doesn't exist *or* belongs to a different citizen (the API never
  distinguishes the two, to avoid leaking which grievance numbers are valid).
- `POST /api/grievances/{grievance_number}/attachments` — citizen-only, ownership
  enforced. Uploads one evidence file (JPG/PNG/PDF, ≤10 MB) to a grievance the
  citizen owns. Files are stored on disk under `backend/uploads/`, never in
  PostgreSQL — only metadata (including a server-computed SHA-256 hash) is stored
  in the database.

See [docs/architecture.md](docs/architecture.md) for the grievance-number generation
strategy, ownership-security model, and file-storage security measures.

## Grievance Tracking & Status History (Step 4)

- `GET /api/grievances/{grievance_number}` — now additionally returns `status_history`
  (chronological list of status changes) and `updated_at`.
- `GET /api/grievances/{grievance_number}/history` — citizen-only, same ownership
  enforcement as above. Returns just the status-history timeline for a grievance.

Supported statuses: `SUBMITTED → UNDER_REVIEW → ASSIGNED → IN_PROGRESS → RESOLVED →
CLOSED`, with `UNDER_REVIEW → REJECTED` as the rejection branch. `grievances.status`
is always the authoritative current status; `grievance_status_history` is an
append-only record of how it got there.

**No status-change endpoint is exposed yet** — Step 4 intentionally implements
`update_grievance_status()` as a backend-only service (validated transitions, atomic
status+history write), with no HTTP route reachable by citizens or any other role.
Step 7 (Officer Dashboard) will build a properly role-gated router on top of it.

See [docs/architecture.md](docs/architecture.md) for the full transition-rule table,
the backfill mechanism for grievances created before Step 4, and the timestamp
strategy.

## Citizen Identity Protection & Privacy (Step 6)

> **Note:** the roadmap's Step 5 (Department Auto-Routing) was never actually
> implemented in this codebase. Step 6's officer-facing endpoints below authorize
> *any* authenticated officer/admin (not "officers assigned to this grievance's
> department", since no such assignment data exists) — but PII exposure is always
> fully governed by `privacy_mode` regardless. See docs/architecture.md section 7i.

- `PATCH /api/grievances/{grievance_number}/privacy` — citizen-owner-only. Body
  accepts exactly one field, `privacy_mode` (`NORMAL` / `CONFIDENTIAL` /
  `IDENTITY_PROTECTED`) — no other grievance field can be smuggled through it.
- `GET /api/grievances/{grievance_number}/officer-view` — officer/admin only.
  Returns a privacy-filtered view built field-by-field server-side; PII fields are
  `null` in the JSON itself for `CONFIDENTIAL`/`IDENTITY_PROTECTED`, not merely
  hidden by the frontend.
- `POST /api/grievances/{grievance_number}/identity-reveal-requests` — officer/admin
  only, requires a `reason` (min 10 characters). Creates a `PENDING` request; never
  reveals identity by itself.
- `POST /api/identity-reveal-requests/{id}/review` — **admin only**. Approves or
  rejects a pending request; a request can only be reviewed once.
- `GET /api/identity-reveal-requests/{id}/identity` — the one authorized disclosure
  point. Requires `APPROVED` status *and* that the caller is the original requester.
  Returns exactly `{name, phone, email}`. Every successful call writes a
  `privacy_access_logs` row recording which field *names* were disclosed (never
  their values).

Privacy modes default to `IDENTITY_PROTECTED` (the most protective) for new
grievances and were backfilled onto all pre-existing grievances by migration
`0005`. A citizen always sees their own full submission regardless of
`privacy_mode` — it only governs what an officer can see.

See [docs/architecture.md](docs/architecture.md) for the full privacy-mode table,
the three-actor identity-reveal workflow, and the PII-hygiene guarantees verified
this step.

## Department Auto-Routing (Step 5)

- `GET /api/departments` — lists active departments (name, description, contact
  info). No auth required — non-sensitive reference data, same pattern as
  `GET /api/categories`.
- `GET /api/categories` — now includes each category's mapped `department` (or
  `null` if unmapped).
- Grievance responses (`GET /api/grievances/my`, `GET /api/grievances/{n}`) now
  include `department`, `routing_type` (`AUTOMATIC`), and `routed_at`.

Routing is fully automatic and deterministic (category → department mapping, no
AI/LLM involved) and happens atomically at grievance creation — a citizen can
never select or influence the department through the API. Grievances whose
category has no active department mapping fall back to **General Grievance
Cell**. Department "assignment" here means routing, and is completely separate
from the grievance status value `ASSIGNED` (Step 4) — routing never changes a
grievance's status, which stays `SUBMITTED` until Step 7's officer workflow
acts on it.

Routing information is always visible to an authorized officer regardless of
`privacy_mode` — but citizen PII remains exactly as privacy-gated as Step 6
established. See [docs/architecture.md](docs/architecture.md) for the full
routing algorithm, fallback behavior, seeded departments/mappings, and how
this integrates with Step 6's privacy system without duplicating it.

## Officer Dashboard & Grievance Processing (Step 7)

- `GET /api/officer/dashboard` — department-scoped statistics (total, and a
  count per status) plus the 5 most recent department grievances.
- `GET /api/officer/grievances` — department-scoped grievance list, with
  `status` / `category_id` / `grievance_number` query filters applied entirely
  server-side.
- `GET /api/officer/grievances/{grievance_number}` — full detail, privacy-
  filtered per Step 6's rules (reused, not duplicated), including attachments
  and status history.
- `POST /api/officer/grievances/{grievance_number}/claim` — self-claim; fails
  with 409 if another officer already has an active claim.
- `POST /api/officer/grievances/{grievance_number}/status` — status transition,
  delegating entirely to Step 4's existing `update_grievance_status()`
  (same transition rules, same atomic history write — nothing new here except
  the department-authorization check in front of it).

**Every endpoint above requires `require_role("officer")` and independently
re-resolves the officer's department server-side** from `officer_profiles` —
never from anything the client sends. An officer from one department gets a
404 (not a 403) when trying to view, claim, or update a grievance routed to a
different department — the same "don't reveal existence" pattern used
everywhere else in this project.

### Creating officer accounts for development/testing

Public registration (`POST /api/auth/register`) still always creates
`user_type=citizen` — there is no endpoint that can create or promote an
account to `officer`. For local development, promote an existing registered
account directly in the database:

```sql
UPDATE users SET user_type = 'officer' WHERE email = 'officer@example.com';

INSERT INTO officer_profiles (user_id, department_id, designation, employee_id)
SELECT u.id, d.id, 'Field Officer', 'EMP-001'
FROM users u, departments d
WHERE u.email = 'officer@example.com' AND d.name = 'Public Works Department';
```

This is intentional, not a shortcut around missing functionality — controlled
officer/admin account creation is future admin-dashboard work (Step 11), and
the existing test suite (`tests/test_officer.py`) creates officer accounts
the same way, directly via SQLAlchemy, for the same reason.

See [docs/architecture.md](docs/architecture.md) section 7k for the full
department-authorization architecture, the distinction between department
routing (Step 5) and officer assignment (Step 7), and why both the Step 6
`/api/grievances/{n}/officer-view` and the new `/api/officer/grievances/{n}`
endpoints were kept side by side.

## Tamper-Evident Audit Trail (Step 8)

- `GET /api/audit/grievances/{grievance_number}` — admin-only. Returns every
  audit event referencing a grievance, in chronological order.
- `GET /api/audit/verify` — admin-only. Re-walks the entire global SHA-256
  hash chain and returns `{"valid": true, "records_checked": N}`, or on
  detected tampering `{"valid": false, "records_checked": N,
  "first_invalid_record": N, "reason": "..."}`.

**"Tamper-evident," not "tamper-proof"** — a database administrator with
direct SQL access could still edit a row; the hash chain makes that edit
*detectable*, not impossible. There is no update or delete endpoint for
audit records anywhere in the API, and the application code that writes
them (`app/services/audit_service.py`) is the only module in the entire
codebase that constructs a hash.

Ten event types are recorded automatically as part of the existing
workflows (grievance creation, routing, status changes, officer claims,
privacy changes, and the full identity-reveal request/approve/reject/
access cycle) — reusing Step 4's status service, Step 5's routing service,
Step 6's privacy service, and Step 7's officer service exactly as they
already work, never a second parallel mechanism. Every audit write happens
inside the same database transaction as the action it describes, so a
rolled-back action never leaves behind an audit record claiming it
succeeded.

Concurrent writes are serialized via a PostgreSQL advisory lock
(`pg_advisory_xact_lock`), verified with a genuine multi-threaded,
multi-connection test against a live database
(`backend/scripts/verify_audit_concurrency.py`) — see
[docs/architecture.md](docs/architecture.md) section 7l for the full
results and a live tampering demonstration (direct `UPDATE` via `psql`,
followed by `GET /api/audit/verify` correctly detecting it).

## Health Checks

Once the backend is running:

```bash
curl http://localhost:8000/                # basic API status
curl http://localhost:8000/api/health       # liveness check
curl http://localhost:8000/api/health/db    # backend + database connectivity
```

The frontend home page also displays live status for all three.

## Running Tests

```bash
cd backend
pytest
```

Tests use an in-memory SQLite database, so they don't require a running
PostgreSQL instance. The suite covers Step 1 foundation checks, Step 2
authentication (registration, duplicate email/phone, weak-password rejection,
privilege-escalation attempts, login success/failure/inactive-account, protected
endpoint access with missing/invalid/expired tokens, refresh-token rotation, and
logout/revocation), Step 3 grievance submission (category filtering,
authenticated/role-restricted creation, field validation, unique grievance-number
generation, ownership enforcement on read and attachment upload, cross-citizen
access denial, attachment type/size validation, server-side SHA-256 hashing, and
path-traversal-safe filename handling), Step 4 tracking/history (initial
history on creation, backfill for pre-existing grievances with no-duplicate
guarantee, chronological ordering, ownership-secured history retrieval, valid/
invalid/same-status transition handling, atomicity of status+history writes,
and rejected/closed display), Step 6 privacy (privacy-mode defaults and
citizen-driven changes, officer-view PII filtering per mode, the full
identity-reveal request/review/fetch workflow including unauthorized-actor
rejection, privacy-access-log creation and field-name-only content, JWT/response
PII hygiene, and cross-citizen isolation preserved regardless of privacy mode),
and Step 5 department routing (automatic category-based routing, inactive-
department and missing-mapping fallback, AUTOMATIC assignment type with no
fabricated officer identity, atomicity, status-unchanged guarantee, department-
tampering resistance, backfill with no-duplicate guarantee, and — critically —
that Step 6's privacy filtering still fully applies to routed grievances across
all three privacy modes), and Step 7 officer dashboard/processing
(officer authentication, citizen/admin blocked from officer endpoints,
department isolation enforced both for viewing and for status changes,
department-scoped dashboard statistics, reused Step 4 status-transition
validation with correct `changed_by`, the claim workflow including double-
claim prevention and cross-department claim rejection, citizen visibility of
officer-driven status changes and history, all three Step 6 privacy modes
respected in the officer detail view, unauthorized identity-reveal still
correctly refused, attachment metadata visible only for authorized
department grievances, and public registration still unable to create
officer accounts), and Step 8 audit trail (genesis marker on the first
record, correct hash chaining, deterministic hash calculation, valid-chain
verification, detection of modified/deleted/out-of-order records and
broken previous_hash/integrity_hash values, no client-controllable
actor_id/previous_hash/integrity_hash, no update/delete audit endpoints,
every one of the ten tracked event types created at the right point in
each existing workflow, sensitive-data exclusion verified across a full
identity-reveal cycle, admin-only access restriction, and a full
integration workflow producing a verifiably valid chain end to end).

**Total: 166 tests, 166 passing** — 4 from Step 1 (`test_health.py` +
`test_db.py`), 18 from Step 2 (`test_auth.py`), 24 from Step 3
(`test_grievances.py`), 20 from Step 4 (`test_grievance_history.py`), 26 from
Step 6 (`test_privacy.py`), 21 from Step 5 (`test_routing.py`), 27 from
Step 7 (`test_officer.py`), and 26 from Step 8 (`test_audit.py`).

All Step 3, Step 4, Step 5, Step 6, Step 7, and Step 8 endpoints were
additionally verified manually against a real running PostgreSQL instance
(not just SQLite)
— see
docs/architecture.md for why this matters given the PostgreSQL-specific bugs
Step 2 caught, and Step 6's own live-Postgres migration bug (see "What's
Implemented in Step 6" below).

## What's Implemented in Step 1

- Project structure for backend, frontend, docs
- Foundation database models: `users`, `roles`, `user_roles`,
  `citizen_profiles`, `departments`, `officer_profiles`
- Initial Alembic migration for the tables above
- FastAPI app with centralized config, database session handling,
  logging, global exception handling, and CORS via environment variables
- `GET /` and `GET /api/health` (+ `GET /api/health/db`) endpoints
- Minimal React/Vite frontend showing project name and live backend/DB status
- Basic backend test suite (root, health, db connectivity, one model op)

## What's Implemented in Step 2

- Citizen registration and secure login with Argon2id password hashing
- JWT access tokens (short-lived, kept in memory on the frontend) and refresh
  tokens (longer-lived, HttpOnly cookie, rotated on use, revocable server-side
  via the new `refresh_tokens` table)
- `GET /api/auth/me` and reusable `get_current_user` / `require_role()` FastAPI
  dependencies for future protected endpoints
- Lightweight in-memory rate limiting on authentication endpoints
- `/register` and `/login` pages with client-side validation, loading states,
  and error handling
- Alembic migration for `refresh_tokens`
- 14 new backend tests covering the full authentication surface

## What's Implemented in Step 3

- Complaint submission: `POST /api/grievances` creates a grievance owned by the
  authenticated citizen, with a server-generated unique `grievance_number`
  (`GRV-<year>-<6-digit sequence>`) and `status=SUBMITTED`
- 10 seed complaint categories (`GET /api/categories`), with a nullable
  `department_id` column prepared for Step 5 routing (unused for now)
- Ownership-secured retrieval: `GET /api/grievances/my` and
  `GET /api/grievances/{grievance_number}` — a citizen can never read another
  citizen's grievance (404, not 403, to avoid leaking which numbers exist)
- Evidence attachments: `POST /api/grievances/{grievance_number}/attachments`
  stores files on disk (never in PostgreSQL) with UUID-generated filenames,
  extension/MIME allow-listing, streamed size limits, and server-computed
  SHA-256 hashing
- `/complaints/new` submission form (category dropdown from the API, client-side
  validation, evidence upload, success screen with grievance number) and
  `/complaints` list page
- Alembic migration for `categories`, `grievance_sequences`, `grievances`,
  `attachments`, plus category seed data
- 22 new backend tests covering creation, validation, ownership security, and
  attachment handling — all additionally verified manually against live PostgreSQL

## What's Implemented in Step 4

- Grievance status history: `grievance_status_history` table records every status
  change (old status, new status, who changed it, optional remarks, timestamp) —
  `grievances.status` stays the single authoritative current status, never
  recomputed from history
- Centralized, validated status-transition policy in
  `grievance_service.update_grievance_status()`: rejects same-status no-ops and any
  transition not in the documented allow-list, and writes the status change +
  history record atomically in one transaction
- Automatic initial-SUBMITTED history record on every new grievance (no frontend
  changes required — this is entirely backend logic)
- Migration-driven backfill: existing Step 3 grievances (created before this table
  existed) automatically receive their initial SUBMITTED history record, with a
  duplicate-safe/idempotent backfill function
- `GET /api/grievances/{grievance_number}` enriched with `status_history` and
  `updated_at`; new `GET /api/grievances/{grievance_number}/history` endpoint —
  same ownership enforcement as every other grievance endpoint
- **No status-change HTTP endpoint is exposed** — this is deliberate. The service
  function is fully built and tested, ready for Step 7's officer dashboard, but no
  citizen (or anyone else) can currently change a grievance's status through the API
- `/complaints/:grievanceNumber` detail page with a reusable `StatusTimeline`
  component (distinguishes completed/current/future/rejected steps, never implies
  progress that hasn't happened); `/complaints` list now shows last-updated and
  links to the detail page
- 20 new backend tests covering history creation, backfill, ownership, chronological
  ordering, valid/invalid/same-status transitions, atomicity, and rejected/closed
  display — all additionally verified manually against live PostgreSQL, including a
  full backfill of real pre-existing Step 3 grievance data

## What's Implemented in Step 6

> **Note on build order:** this step was built before Step 5 (Department
> Auto-Routing), which has since been implemented — see "What's Implemented
> in Step 5" below and docs/architecture.md section 7j for how the two were
> integrated without duplicating or bypassing either one.

- Three privacy modes on every grievance (`NORMAL` / `CONFIDENTIAL` /
  `IDENTITY_PROTECTED`), citizen-selectable at submission and changeable
  afterward via `PATCH .../privacy` (owner-only)
- Backend-decided, field-by-field privacy-filtered officer view
  (`privacy_service.get_grievance_for_actor`) — PII fields are absent from the
  JSON response itself when not authorized, never just hidden by the frontend
- Controlled three-actor identity-reveal workflow: request (officer/admin,
  reason required) → review (admin-only, one-time) → reveal-fetch (original
  requester only, approval required) — verified live end-to-end against
  PostgreSQL exactly per the spec's manual test script
- `privacy_access_logs`: every identity disclosure is logged with field
  *names* only (`"name,phone,email"`), never actual values — verified by both
  an automated test and a live-database inspection after a real reveal
- Migration `0005` (see the migration-numbering note near the top of this
  README) backfills `IDENTITY_PROTECTED` onto every pre-existing grievance;
  caught a real PostgreSQL-specific bug along the way (`ALTER TABLE ADD
  COLUMN` with an ENUM type does not auto-create the type the way `CREATE
  TABLE` does — needed an explicit `CREATE TYPE` first)
- Frontend: privacy-mode selector with plain-language explanations on the
  submission form (defaults to Identity Protected), privacy indicator +
  change control on the complaint detail page
- 26 backend tests covering every item in the Step 6 test list — all
  additionally verified manually against live PostgreSQL, including the full
  citizen/officer/admin/second-citizen security walkthrough from the spec

## What's Implemented in Step 5

- Deterministic, rule-based category→department routing (`routing_service.py`)
  — no AI/LLM, fully predictable and testable; happens atomically inside the
  same transaction as grievance creation and the initial SUBMITTED history row
- `grievance_assignments`: the authoritative, append-only routing history
  (one row per routing decision — designed for Step 7 to add re-routing later
  without a schema change). `grievances.department_id` is a denormalized
  mirror of the latest assignment, kept in sync, never the source of truth
- Fallback to **General Grievance Cell** whenever a category has no active
  department mapping — never silently drops a grievance, and never routes to
  an inactive department under any circumstance
- Automatic routing always uses `assignment_type=AUTOMATIC` with
  `assigned_by=None` — the system never fabricates a fake officer identity
  for a decision it made deterministically
- **Department assignment ≠ grievance status `ASSIGNED`** — routing never
  touches `grievances.status`, which stays `SUBMITTED` until Step 7's officer
  workflow acts on it. Directly tested and manually verified.
- 8 departments seeded (idempotently) and all 10 existing categories mapped
  by name — migration `0006` also backfills routing for every grievance that
  predates Step 5 (all of Steps 3/4/6's grievances), verified against live
  PostgreSQL with correct departments assigned based on each grievance's
  actual category, and confirmed idempotent on re-run
- **Full integration with Step 6's privacy system, not a second one**:
  `privacy_service.get_grievance_for_actor()` was extended (not duplicated)
  to include department/routing info, which is always visible to an
  authorized officer regardless of `privacy_mode` — while citizen PII remains
  exactly as privacy-gated as Step 6 established. Verified live: an
  `IDENTITY_PROTECTED` grievance shows its department to an officer while
  name/phone/email all remain `null`.
- `GET /api/departments` (new), `GET /api/categories` and grievance responses
  enriched with department/routing fields — no department-changing endpoint
  exists for citizens, and a smuggled `department_id` in the creation request
  is silently ignored (verified live)
- Frontend: department + routing type shown on the complaint detail page and
  in the complaints list — no manual department selection anywhere
- 21 backend tests covering every item in the Step 5 test list, including
  three dedicated to confirming Step 6 privacy rules hold across all three
  privacy modes for routed grievances — all additionally verified manually
  against live PostgreSQL via the full 12-step manual test script from the
  spec (Roads & Potholes → Public Works, Water Supply → Water Supply Dept,
  Other → General Grievance Cell fallback, identity-protected routing +
  privacy check, department-tampering resistance, cross-citizen isolation)

## What's Implemented in Step 7

- Department authorization (`officer_service.py`) — resolves
  `current_user → officer_profile → department_id → active department`
  entirely server-side; never trusts a department_id or officer_id from the
  client in any form
- `officer_assignments`: a table deliberately separate from Step 5's
  `grievance_assignments` — department **routing** (grievance → department,
  Step 5, automatic) and officer **assignment** (grievance → officer, Step 7,
  manual claim) are different facts, tracked independently, so one can change
  without the other
- Claim workflow: an officer can self-claim any grievance in their own
  department; claiming a grievance already actively claimed by another
  officer is rejected (409); claiming never itself changes grievance status
  — that remains a fully separate action
- Status transitions **fully reuse** Step 4's `update_grievance_status()` —
  same transition rules, same atomic status+history write, same
  `grievance_status_history` table. Step 7 adds zero new transition logic,
  only the department-authorization check in front of it
- Officer detail/list views **fully reuse** Step 6's
  `get_grievance_for_actor()` for privacy filtering — extended (attachments +
  status history added to the response shape) but never rewritten. The same
  `NORMAL`/`CONFIDENTIAL`/`IDENTITY_PROTECTED` rules apply identically
- Department-scoped dashboard: total + per-status counts computed via a
  single `GROUP BY` query filtered to the officer's own department — verified
  live that two officers in different departments see entirely different,
  correctly isolated numbers against the same database
- `GET /api/officer/grievances` supports `status`/`category_id`/
  `grievance_number` filters, applied as SQL `WHERE` clauses — never fetched
  in full and filtered in React
- Public registration still cannot create officer accounts (unchanged from
  Step 2); officer accounts for development/testing are created via direct
  SQL, documented above, matching the spec's explicit instruction
- Frontend: `/officer/dashboard`, `/officer/grievances`, and
  `/officer/grievances/:grievanceNumber` pages, gated by a new
  `OfficerProtectedRoute` (a UX convenience only — the backend independently
  re-authorizes every single request regardless of any frontend route guard)
- 27 backend tests covering every item in the Step 7 test list — all
  additionally verified manually against live PostgreSQL via the **exact**
  manual scenario from the spec: Citizen A submits a pothole complaint →
  routed to Public Works → Officer A reviews, claims, and progresses it
  through all five statuses (SUBMITTED → UNDER_REVIEW → ASSIGNED →
  IN_PROGRESS → RESOLVED) with remarks at each step → Citizen A sees the
  complete updated history → Officer B (Water Supply) is denied access to
  the same grievance at every endpoint (view, claim, and status-change all
  correctly return 404) → identity-protected grievance confirmed to hide
  citizen identity from Officer A throughout the entire workflow

## What's Implemented in Step 8

- SHA-256 hash-chained, append-only `audit_logs` table: ONE global
  chronological sequence (not one chain per grievance), ordered by an
  explicit `sequence_number`, with a deterministic genesis marker (64 hex
  zeros) for the first record — never an implicit or unpredictable value
- `app/services/audit_service.py` is the ONLY module in the codebase that
  constructs an `AuditLog` row or computes a hash — `grievance_service.py`,
  `officer_service.py`, and `privacy_service.py` each call
  `record_audit_event()` as a plain function call, never touching hashing
  themselves
- All ten required event types wired into the existing workflows exactly
  where they happen: grievance creation and automatic routing, status
  changes (reusing Step 4's `update_grievance_status()` unmodified), officer
  claim (which emits both `OFFICER_CLAIMED` and `OFFICER_ASSIGNED`, since a
  self-claim is simultaneously both facts), privacy mode changes, and the
  complete identity-reveal request → approve/reject → access cycle
- Every audit write happens inside the same database transaction as the
  action it describes — a rolled-back action never leaves a false audit
  record behind
- **A real bug caught during testing**: SQLite's `DateTime(timezone=True)`
  doesn't reliably round-trip `tzinfo`, which made a freshly-created,
  completely untampered chain fail its own verification. Fixed by
  normalizing timestamps to UTC before hashing — see
  docs/architecture.md section 7l for the full story
- Concurrency safety via PostgreSQL's `pg_advisory_xact_lock`, verified with
  a **genuine 20-thread, 20-independent-connection test against live
  PostgreSQL** (`backend/scripts/verify_audit_concurrency.py`): zero errors,
  zero duplicate sequence numbers, chain remained fully valid afterward
- A live tampering demonstration performed end-to-end: valid chain → direct
  `UPDATE audit_logs ...` via `psql` (bypassing the application entirely) →
  `GET /api/audit/verify` correctly returned `valid: false` with the exact
  affected record number and reason → record restored → chain valid again
- No update or delete endpoint exists for audit records anywhere — verified
  live that `PATCH`/`PUT`/`DELETE` against any audit path returns 404/405
- Sensitive-data discipline enforced and tested: `old_value`/`new_value`/
  `metadata` never contain raw phone numbers, emails, or passwords — verified
  by running a full identity-reveal workflow and grepping every resulting
  audit row for the citizen's actual contact details, asserting they never
  appear
- Both audit endpoints are admin-only (`require_role("admin")`, the same
  Step 2 dependency reused) — citizens and officers both get 403
- 26 backend tests covering every item in the Step 8 test list, plus the
  live-PostgreSQL migration, concurrency, and tampering-demonstration
  verification described above

## What's Intentionally NOT Implemented Yet

Officer-driven manual re-routing between departments, AI analysis
(categorization, duplicate detection, urgency scoring, AI-assisted routing —
though the audit system is ready to record AI-related events when Step 9
adds them, via the same `record_audit_event()` every other step already
uses), admin dashboard (including
controlled officer/admin account creation — Steps 7/8 still rely on direct
SQL for this, documented above as intentional), and notifications all
belong to Steps 11–12. See [docs/architecture.md](docs/architecture.md) for the
full roadmap.

## Step 9 — Advanced AI Grievance Intelligence

Step 9 adds an **optional decision-support AI layer**. Steps 1–8 remain authoritative and are not rewritten. Migration `0009_add_ai_intelligence.py` is additive; migrations `0001`–`0008` are unchanged.

### Provider architecture

- `AI_PROVIDER=fallback` uses a deterministic local fallback and requires no external API key.
- `AI_PROVIDER=ollama` uses an Ollama instance at `OLLAMA_BASE_URL` and `OLLAMA_MODEL`.
- The core grievance workflow does not depend on AI availability.
- Speech-to-text uses a browser-first approach with a server-side provider abstraction; no paid speech API is required.

Optional Ollama setup:

```bash
ollama pull llama3.2:3b
```

Then set:

```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
```

### AI safeguards

AI output is stored separately from authoritative grievance data. AI cannot directly change citizen identity, category, department, status, privacy mode, or final resolution. Recommendations are `PENDING` until an authorized officer reviews them as `ACCEPTED`, `REJECTED`, or `OVERRIDDEN`.

The AI privacy firewall removes names, phone numbers, email addresses, authentication tokens and unnecessary identifiers before provider calls. Identity-protected grievances receive especially strict sanitization. Citizen questions are treated as untrusted input and are never allowed to override system instructions.

Confidence thresholds are configurable:

- `>= 0.80`: normal recommendation
- `0.50–0.79`: review recommended
- `< 0.50`: needs human review

### Step 9 endpoints

- `POST /api/ai/grievances/{grievance_number}/analyze`
- `POST /api/ai/grievances/{grievance_number}/summary`
- `POST /api/ai/grievances/{grievance_number}/category-suggestion`
- `POST /api/ai/grievances/{grievance_number}/priority`
- `POST /api/ai/grievances/{grievance_number}/duplicates`
- `POST /api/ai/grievances/{grievance_number}/copilot`
- `POST /api/ai/grievances/{grievance_number}/response-draft`
- `POST /api/ai/grievances/{grievance_number}/response-draft/{draft_id}/review`
- `POST /api/ai/grievances/{grievance_number}/resolution-analysis`
- `POST /api/ai/grievances/{grievance_number}/sla-risk`
- `POST /api/ai/grievances/{grievance_number}/spam`
- `POST /api/ai/recommendations/{recommendation_id}/review`
- `POST /api/ai/assistant`
- `POST /api/ai/transcribe`
- `GET /api/ai/analytics`
- `GET /api/ai/hotspots`
- `GET /api/ai/emerging-issues`
- `GET /api/ai/alerts`

### AI data retention

AI records are stored separately to support traceability and human review. `AI_RETENTION_DAYS` documents the intended retention policy (default 90 days); deployment-specific scheduled deletion should be applied by the operator rather than silently deleting records inside request handlers. Raw provider prompts/responses are not stored in the audit hash chain.

### Roadmap

- Steps 1–8: complete and authoritative.
- **Step 9: complete in this release.**
- Step 11: complete in this release.
- Step 12: complete in this release.

## Step 10 — Resolution & Citizen Verification

Step 10 adds a secure, auditable resolution lifecycle without rewriting Steps 1–9. Migration `0010_add_resolution_workflow.py` is additive; migrations `0001`–`0009` remain unchanged.

### Resolution lifecycle

`IN_PROGRESS → RESOLVED → CLOSED`

- An authorized officer submits a resolution through the Step 10 resolution endpoint.
- Resolution submission uses the existing centralized `update_grievance_status()` service to move the grievance to `RESOLVED`.
- `RESOLVED` means the officer has submitted a resolution and the citizen must be given an opportunity to review it.
- The citizen can accept the resolution; only the server can then transition `RESOLVED → CLOSED`.
- The citizen can dispute the resolution with a mandatory reason; the server transitions `RESOLVED → IN_PROGRESS` so the officer can investigate and submit another resolution.
- Previous resolution attempts are append-only records and are never deleted.

### Resolution evidence

Officer evidence uses the same Step 3 file-storage security controls: allow-listed extensions/MIME types, streaming size limits, UUID-generated filenames, sanitized display names, path validation, server-side SHA-256 hashes, and filesystem storage outside PostgreSQL.

### Citizen verification

Citizens can view their own resolution, permitted evidence, department, original complaint and status history. They can accept or dispute a resolution. Acceptance is recorded with the authenticated citizen and timestamp through the feedback/verification record. Disputes are stored separately from the original complaint and preserve the original resolution.

Optional 1–5 feedback is available after resolution. Feedback is never required for closure.

### Step 10 endpoints

- `POST /api/officer/grievances/{grievance_number}/resolution`
- `GET /api/officer/grievances/{grievance_number}/resolutions`
- `GET /api/officer/grievances/{grievance_number}/resolutions/evidence/{evidence_id}`
- `GET /api/grievances/{grievance_number}/resolutions`
- `GET /api/grievances/{grievance_number}/resolution`
- `GET /api/grievances/{grievance_number}/resolutions/evidence/{evidence_id}`
- `POST /api/grievances/{grievance_number}/resolution/accept`
- `POST /api/grievances/{grievance_number}/resolution/dispute`
- `POST /api/grievances/{grievance_number}/feedback`

### Step 10 database tables

- `resolutions`
- `resolution_evidence`
- `resolution_disputes`
- `resolution_feedback`

Resolution lifecycle actions reuse the Step 8 tamper-evident audit chain. Step 10 adds audit actions for resolution submission, evidence, viewing, acceptance, dispute/reopen and citizen feedback.

### AI integration

Step 10 reuses the Step 9 AI resolution-evidence analysis capability. AI remains advisory: it cannot approve a resolution, reject a dispute, change grievance status, or close a grievance.

### Notification preparation

Step 10 emits internal resolution lifecycle hooks for future notification consumers. No SMS/email provider is added until the notification step.

### Roadmap

- Steps 1–8: complete and authoritative.
- Step 9: complete.
- **Step 10: complete in this release.**
- Step 11: complete in this release.
- Step 12: complete in this release.

## Step 11 — Admin Dashboard & Governance

Step 11 adds an admin-only governance layer on top of Steps 1–10. Migration `0011_add_admin_governance.py` is additive; migrations `0001`–`0010` are not modified. The implementation reuses the existing authentication, privacy, routing, officer authorization, AI and audit services.

### Admin authorization

All `/api/admin/*` endpoints use the existing `require_role("admin")` dependency. The client cannot select a role or department to obtain authorization. Citizens and officers are denied access server-side.

### Governance areas

The admin API covers:

- system dashboard and aggregate grievance statistics
- grievance search/filtering without unnecessary citizen PII
- officer creation, update, department assignment and soft deactivation
- department creation/update/deactivation with routing safety checks
- category creation/update/deactivation and department mapping
- privacy identity-reveal request review through the existing Step 6 workflow
- audit search and full-chain integrity verification through Step 8
- AI governance metrics from Step 9 data
- Step 10 resolution oversight
- server-side analytics and privacy-mode distributions

Historical grievances, assignments, resolution attempts and audit records are not destructively deleted by admin endpoints.

### Safe operations

The admin layer prevents deactivation of the General Grievance Cell, prevents deactivation of departments with active routing dependencies or active grievances, requires active departments for new officer/category assignments, prevents duplicate employee IDs, and soft-deactivates officers while preserving assignment history.

### Step 11 API endpoints

- `GET /api/admin/dashboard`
- `GET /api/admin/grievances`
- `GET /api/admin/grievances/{grievance_number}`
- `GET/POST/PATCH /api/admin/officers...`
- `GET/POST/PATCH /api/admin/departments...`
- `GET/POST/PATCH /api/admin/categories...`
- `GET /api/admin/privacy/requests`
- `POST /api/admin/privacy/requests/{id}/approve`
- `POST /api/admin/privacy/requests/{id}/reject`
- `GET /api/admin/audit`
- `GET /api/admin/audit/verify`
- `GET /api/admin/ai`
- `GET /api/admin/analytics`
- `GET /api/admin/resolutions`

### Step 11 database

No new business tables were required. Migration `0011_add_admin_governance.py` adds the Step 11 audit action values and the `CATEGORY` audit entity type to the existing audit enums. Existing users, officer profiles, departments, categories, grievances, AI tables and privacy tables are reused.

### Step 11 frontend

Admin routes are protected by `AdminProtectedRoute` while reusing the existing authentication context. The dashboard exposes system-wide metrics and navigation to grievance oversight, officer/department/category management, privacy governance, audit verification, AI governance and analytics. Management pages provide protected create/review actions without exposing raw citizen identity data.

### Step 11 audit integration

Meaningful administrative mutations are recorded using the existing Step 8 hash-chain service with actions including officer creation/update/deactivation, department creation/update/deactivation, category creation/update/deactivation, routing mapping changes and privacy-request review.

### Roadmap

- Steps 1–8: complete and authoritative.
- Step 9: complete.
- Step 10: complete.
- **Step 11: complete in this release.**
- Step 12: complete in this release. Steps 13–16: intentionally not implemented.

## Step 12 — Notifications & Production Hardening

Step 12 adds centralized **email and browser push notifications only**. SMS is deliberately not implemented and has no provider, database fields or configuration.

### Notification architecture

Business services emit internal lifecycle events. `notification_service.py` creates durable in-app notifications and schedules best-effort external delivery through `email_service.py` and `push_notification_service.py`. External delivery failures never roll back grievance, resolution or audit transactions. Notification creation is idempotent using an event key.

### Email configuration

Set these environment variables when SMTP delivery is required:

```env
EMAIL_NOTIFICATIONS_ENABLED=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=notifications@example.com
SMTP_FROM_NAME=Public Grievance Management System
SMTP_USE_TLS=true
SMTP_TIMEOUT_SECONDS=10
APP_PUBLIC_URL=http://localhost:5173
```

If SMTP is missing or disabled, the application continues to operate and no delivery claim is made.

### Browser push

Browser push uses the Web Push API, a service worker and VAPID. Configure:

```env
PUSH_NOTIFICATIONS_ENABLED=true
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=mailto:admin@example.com
```

The private key is backend-only. The browser asks for permission before subscribing, and the subscription is stored only after permission is granted.

### Notification center and preferences

Authenticated users have a notification bell, unread count, notification history, mark-read/mark-all-read controls and settings for email/browser channels. Browser notifications default to off until permission is granted. **There is no SMS option.**

### Notification API

- `GET /api/notifications`
- `GET /api/notifications/unread-count`
- `POST /api/notifications/{id}/read`
- `POST /api/notifications/read-all`
- `GET /api/notifications/preferences`
- `PATCH /api/notifications/preferences`
- `POST /api/notifications/push/subscribe`
- `DELETE /api/notifications/push/subscribe`
- `GET /api/notifications/config`

### Production hardening

The backend adds security headers, production CSP/HSTS, request-size protection, production secret/CORS validation, separate database readiness checking and stronger file-content signature validation for JPG/PNG/PDF uploads. Existing in-memory authentication rate limiting remains suitable for development/single-process use; multi-instance production should place rate-limit state in a shared store such as Redis.

No antivirus scanner is claimed. The file layer now validates allowed signatures in addition to extension/MIME checks; an external AV/content-scanning service can be added at the documented extension point for higher-assurance deployments.

### Migration

Step 12 adds `0012_add_notifications.py` only. Migrations `0001`–`0011` are not modified.

### Audit events

Notification creation, successful/failed email delivery, successful/failed push delivery and preference changes use the existing Step 8 audit chain:

- `NOTIFICATION_CREATED`
- `EMAIL_NOTIFICATION_SENT`
- `EMAIL_NOTIFICATION_FAILED`
- `PUSH_NOTIFICATION_SENT`
- `PUSH_NOTIFICATION_FAILED`
- `NOTIFICATION_PREFERENCES_CHANGED`

### Roadmap

- Steps 1–11: complete.
- **Step 12: complete in this release.**
- Steps 13–16: intentionally not implemented.

### Step 12 verification note

Static source/migration verification is performed during packaging. Full pytest, PostgreSQL migration execution, SMTP delivery and browser push delivery require the project's runtime dependencies, PostgreSQL, and—where applicable—valid SMTP/VAPID configuration. Those external delivery paths must be reported based on actual runtime results rather than inferred from code compilation.

## Step 13 — Public Grievance Statistics & Civic Ranking

`/statistics` is a public, no-login civic intelligence dashboard. The backend exposes aggregate-only endpoints under `/api/public/statistics` for summary metrics, geography, trends, category/department breakdowns, rankings, category leaderboards, most-improved comparisons, and methodology. Village/taluka/district are nullable Step 13 location fields; existing `state` and `city` behavior remains unchanged.

Public responses enforce a configurable minimum sample size (default 5). Below the threshold, detailed statistics are replaced by `insufficient_data`; no citizen identity, contact data, complaint text, protected identity fields, or attachments are returned.

The official Civic Performance Score is deterministic and explainable: **40% resolution performance + 25% timeliness + 20% citizen satisfaction + 15% low dispute rate**. Timeliness is normalized against a documented 30-day target. SLA is deliberately excluded because Steps 1–12 do not store an authoritative SLA target. Locations below the sample threshold are excluded. Raw grievance volume is displayed but is never itself a ranking score component.

Admins can inspect ranking governance at `/api/admin/public-statistics/governance`. Ranking configuration can only be changed by an admin, weights must sum to 1.0, and every change is written through the existing Step 8 hash-chained audit service. Individual scores cannot be manually edited.

Migration: `0013_add_public_statistics.py`. Roadmap status: Steps 1–13 implemented in source; Steps 14–21 intentionally not implemented here. Runtime verification still requires the project's normal Python/Node dependencies and live PostgreSQL environment.

## Step 14 — Government Project Transparency

Step 14 adds a public, privacy-preserving Government Project Management and Monitoring layer at `/projects` and `/projects/{id}`. Authorized administrators manage projects through `/admin/projects`, including lifecycle status, progress, milestones, public evidence, project–grievance relationships, and project analytics. Citizens can follow public projects and receive updates through the existing email/browser notification system.

The implementation uses migration `0014_add_government_projects.py`, UUID-backed project entities, deterministic schedule-state calculation, controlled project–grievance links, public/private evidence flags, and the existing Step 8 audit service. It does not alter migrations 0001–0013.


## Step 15 — Existing-Work Intelligence

Step 15 adds a citizen-controlled pre-submission check that looks for existing grievances and public government projects that may already address the reported problem. Candidate retrieval is narrowed by category, geography, status and recency before similarity scoring. If an Ollama Step 9 provider is configured, it may refine the top candidate scores; otherwise the deterministic similarity fallback remains authoritative for the recommendation.

The result is `NO_MATCH`, `POSSIBLE_MATCH`, or `STRONG_MATCH`. The warning is advisory only: citizens can always submit a new grievance. When they submit anyway, the system records the relationship and the citizen's reason/action without merging or deleting grievances.

Existing grievance results expose only public-safe fields. Government project matches reuse Step 14 project data and project following. Officer users can review possible matches and mark them confirmed or rejected. Existing Step 8 audit logging, Step 12 notifications, Step 9 AI provider infrastructure, and Step 14 project following are reused rather than duplicated.

Migration `0015_add_existing_work_intelligence.py` creates `existing_work_matches` with mutually exclusive grievance/project targets, confidence, explanation, citizen action, and human-review state.

The complete Civic Twin, Project Reality Check, and later Civic Intelligence features remain intentionally outside Step 15.
