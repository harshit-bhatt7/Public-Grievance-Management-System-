# Architecture

## 1. Overall System Architecture

The system follows a conventional three-tier architecture:

```
┌────────────┐      HTTP/JSON       ┌──────────────┐      SQL      ┌──────────────┐
│  Frontend  │  ──────────────────▶ │   Backend    │ ─────────────▶│  PostgreSQL  │
│ React/Vite │ ◀──────────────────  │   FastAPI    │ ◀───────────── │   Database   │
└────────────┘                      └──────────────┘                └──────────────┘
```

- The **frontend** is a single-page React application built with Vite. It talks
  to the backend exclusively through a service layer (`src/services`) over HTTP.
- The **backend** is a FastAPI application organized by responsibility
  (core config/db/security, models, schemas, routers, services, utils) rather
  than by feature, so future feature modules slot into the same folders.
- The **database** is PostgreSQL, accessed only through SQLAlchemy models —
  no raw SQL in route handlers.

## 2. Frontend / Backend / Database Relationship

- Frontend never talks to the database directly.
- Backend is the single source of truth for business rules and data access.
- Configuration (API URLs, database URL, CORS origins, secrets) is injected via
  environment variables on both sides, never hardcoded.

## 3. Folder Structure

```
public-grievance-system/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app creation, middleware (incl. Step 8's request-context capture), router wiring
│   │   ├── core/               config, database session, security (hashing/JWT), deps, logging, request_context.py (Step 8)
│   │   ├── models/            SQLAlchemy ORM models (incl. category.py, grievance.py, attachment.py, grievance_status_history.py, privacy_access_log.py, identity_reveal_request.py, grievance_assignment.py, officer_assignment.py, audit_log.py)
│   │   ├── schemas/            Pydantic request/response models (incl. grievance.py, category.py, attachment.py, privacy.py, department.py, officer.py, audit.py)
│   │   ├── routers/            APIRouter modules, one per feature area (incl. grievances.py, categories.py, privacy.py, departments.py, officer.py, audit.py — read-only, no create/update/delete route)
│   │   ├── services/           Business logic, called by routers (incl. grievance_service.py, privacy_service.py, routing_service.py, officer_service.py, audit_service.py — the ONLY module that hashes anything, as of Step 8)
│   │   └── utils/               Small stateless helpers (incl. file_storage.py)
│   ├── migrations/             Alembic environment + versioned migrations
│   ├── scripts/                 One-off verification scripts not part of the app itself (incl. verify_audit_concurrency.py, Step 8's live-PostgreSQL concurrency demonstration)
│   ├── uploads/                 Attachment files on disk (git-ignored), organized by grievance_number
│   └── tests/                   Backend test suite
├── frontend/
│   └── src/
│       ├── components/          Reusable UI building blocks (FormField, Alert, ProtectedRoute, OfficerProtectedRoute, StatusTimeline)
│       ├── pages/                 Route-level views (incl. NewGrievancePage, MyGrievancesPage, GrievanceDetailPage, OfficerDashboardPage, OfficerGrievanceListPage, OfficerGrievanceDetailPage)
│       ├── layouts/              Shared page layout wrappers
│       ├── context/              Global state (AuthContext)
│       ├── services/             API client functions (fetch wrappers)
│       ├── hooks/                 Custom React hooks
│       └── utils/                  Small stateless helpers (validation.js)
└── docs/                          This file and future design docs
```

## 4. Current Database Tables (Step 1 + Step 2 + Step 3 + Step 4 + Step 6 + Step 5 + Step 7 + Step 8)

> **Note on migration numbering and build order:** the project roadmap's
> "Step 5" (Department Auto-Routing) was mistakenly skipped and Step 6
> (Citizen Identity Protection) was built first. This is now corrected —
> Step 5 has been implemented as migration `0006`, genuinely the next
> sequential revision after Step 6's `0005`. The numbers don't match the
> step numbers (Step 5's migration is `0006`; Step 6's is `0005`) because
> they reflect actual build order, not the roadmap's intended order. See
> section 7j for the full routing architecture and how it integrates with
> Step 6's privacy system without duplicating or bypassing it.

| Table                | Purpose                                                          |
|-----------------------|--------------------------------------------------------------------|
| `users`               | Core account record for citizens, officers, and admins             |
| `roles`               | Named permission roles (independent of `user_type`)                 |
| `user_roles`          | Many-to-many join between `users` and `roles`                      |
| `citizen_profiles`    | Citizen-specific data: address, privacy level, identity visibility  |
| `departments`         | Government departments grievances route to (Step 1 table; seeded with 8 real departments as of Step 5) |
| `officer_profiles`    | Officer-specific data: department, designation, access level        |
| `refresh_tokens`      | Server-side metadata for issued refresh tokens (Step 2), enabling revocation/logout. Stores a SHA-256 hash of each token, never the raw token. |
| `categories`          | Complaint categories citizens choose from (Step 3), seeded with 10 starter categories. `department_id` (nullable, added in Step 3 as unused schema prep) is now actively populated by Step 5's category→department mapping. |
| `grievance_sequences`  | Internal-only counter table (Step 3) whose autoincrement PK backs the human-readable `grievance_number`. Never exposed via the API. |
| `grievances`          | The core complaint record (Step 3): title, description, category, status, location, and the citizen who filed it. `status` remains the single authoritative current-status field — never recomputed from history. Carries `privacy_mode` (Step 6) and a denormalized `department_id` (Step 5, see below). |
| `attachments`         | Metadata for evidence files attached to a grievance (Step 3). The actual file bytes live on disk, never in PostgreSQL — see "File Storage Architecture" below. |
| `grievance_status_history` | Append-only record of every status change a grievance goes through (Step 4): old status, new status, who changed it, optional remarks, and when. See "Grievance Tracking Architecture" below. |
| `privacy_access_logs`  | Append-only record of every time a citizen's protected identity/contact info is accessed (Step 6): who accessed it, why, which field *names* (never values), and when. See "Privacy Architecture" below. |
| `identity_reveal_requests` | The controlled workflow for an officer/admin to request access to a protected citizen's identity (Step 6): PENDING → APPROVED/REJECTED, with a reviewer and remarks. See "Privacy Architecture" below. |
| `grievance_assignments` | Append-only routing HISTORY (Step 5): every department-routing decision made for a grievance, with type (AUTOMATIC/MANUAL), optional remarks, and timestamp. `grievances.department_id` is a denormalized mirror of the latest row here, kept in sync — this table remains authoritative. See "Department Routing Architecture" below. |
| `officer_assignments` | Append-only record of which officer has claimed a grievance (Step 7) — a SEPARATE concept from `grievance_assignments` (grievance → department). `is_active` distinguishes the current claim from any historical ones. See "Officer Dashboard Architecture" below. |
| `audit_logs`          | ONE global, SHA-256 hash-chained, append-only sequence of significant system events (Step 8) — who did what, to what, when, and what changed. Tamper-*evident*, not tamper-proof: application code exposes no update/delete path, and any out-of-band modification becomes detectable via chain re-verification. See "Audit Trail Architecture" below. |

`user_type` on `users` distinguishes citizen / officer / admin at the account
level, while `roles`/`user_roles` allow finer-grained permissions later without
altering the `users` table itself.

## 5. Future Database Tables (Not Yet Implemented)

| Table                      | Planned Purpose                                                    | Step |
|------------------------------|------------------------------------------------------------------------|------|
| `grievance_ai_analysis`     | AI-generated classification, priority, and summary for a grievance     | 9    |
| `grievance_duplicates`      | Links grievances identified as duplicates of one another                | 9    |
| `resolutions`               | Officer-submitted resolution details for a grievance                    | 10   |
| `citizen_feedback`          | Citizen's verification/rating of a resolution                          | 10   |
| `notifications`             | Outbound notifications to citizens/officers about status changes        | 12   |

(`grievance_assignments`/`officer_assignments`/`audit_logs` moved from this
table to section 4 now that they're implemented as of Steps 5/7/8. Step 9's
future AI routing will *consult* `grievance_assignments`/`route_grievance()`
rather than replace them — see section 7j — and its events will be recorded
through the same `audit_service.record_audit_event()` used by every other
step, per section 7l.)

## 6. Planned 12-Step Development Architecture

1. **Project Foundation** — structure, base models, health checks *(completed)*
2. **Citizen Registration & Login** — auth endpoints, JWT issuance, password flows *(completed)*
3. **Complaint Submission** — `grievances`, `categories`, `attachments` *(completed)*
4. **Complaint Tracking** — `grievance_status_history`, citizen-facing tracking views *(completed)*
5. **Department Auto-Routing** — `grievance_assignments`, routing rules *(completed — built out of order, after Step 6; see the note at the top of section 4)*
6. **Citizen Identity Protection** — `privacy_mode`, `privacy_access_logs`, `identity_reveal_requests` *(completed — built before Step 5)*
7. **Officer Dashboard** — officer-facing views over assigned grievances *(this step)*
8. **Tamper-Evident Audit Trail** — `audit_logs`, SHA-256 hash-chained, append-only guarantees *(this step)*
9. **AI Complaint Intelligence** — `grievance_ai_analysis`, `grievance_duplicates`
10. **Evidence & Resolution Verification** — `resolutions`, `citizen_feedback`
11. **Admin & Accountability Dashboard** — cross-department reporting and oversight
12. **Security, Testing & Hackathon Polish** — hardening, expanded test coverage, demo prep

## 7. Security Principles

- All configuration (database URL, secret key, JWT settings, CORS origins) comes from
  environment variables via `app/core/config.py`; nothing is hardcoded.
- `.env` is git-ignored; only `.env.example` (with placeholder values) is committed.
- Passwords are hashed with **Argon2id** (`app/core/security.py`, via passlib) — the
  currently recommended password hashing algorithm. No plaintext passwords are ever
  stored, logged, or returned by any API response.
- JWT access and refresh tokens are signed with `SECRET_KEY`/`JWT_ALGORITHM` from
  environment configuration. Token payloads carry only `sub` (user id), `user_type`,
  `type` (access/refresh), `iat`, `exp`, and a random `jti` — never passwords, phone
  numbers, addresses, or other personal data.
- Refresh tokens are stored server-side (`refresh_tokens` table) as a **SHA-256 hash
  only** — the raw token is never persisted, so a database leak alone cannot be used
  to mint valid sessions. Refresh tokens are rotated on every use and can be revoked
  (logout), unlike access tokens which remain valid until they naturally expire.
- Public registration (`POST /api/auth/register`) always creates `user_type = citizen`
  server-side, regardless of what the client sends — there is no code path that lets a
  public request create an officer or admin account.
- Login failures return one generic `"Invalid email or password."` message for both
  "no such account" and "wrong password", preventing account enumeration.
- A lightweight in-memory rate limiter (`app/utils/rate_limit.py`) caps authentication
  attempts per IP/endpoint as a brute-force guard appropriate for a hackathon-scale
  single-process deployment. It is explicitly **not** sufficient for a real production
  deployment (state is per-process and resets on restart) — Step 12 retains this development behavior and documents shared-store production deployment
  should be replaced with a shared store (e.g. Redis) for real rate limiting.
- A global FastAPI exception handler prevents internal error details (stack traces,
  database errors) from leaking to API clients.
- CORS is restricted to explicitly configured origins (`CORS_ORIGINS`) rather than
  `allow_origins=["*"]`, which is required for a credentialed (cookie-based)
  authentication system to work safely.
- Logging is centralized (`app/core/logging.py`) and deliberately avoids logging
  request bodies, passwords, or tokens.
- Database sessions are request-scoped and always closed via the `get_db`
  dependency, even on error.

## 7a. Authentication Architecture (Step 2)

**Token strategy:**
- **Access token** — short-lived (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 15 minutes),
  returned in the JSON response body, sent by the frontend as an `Authorization: Bearer`
  header on every authenticated request. Kept only in React state (memory), never in
  `localStorage`/`sessionStorage`, so it is not readable by any injected script that
  might run on the page and is automatically cleared on tab close.
- **Refresh token** — longer-lived (`REFRESH_TOKEN_EXPIRE_DAYS`, default 7 days), set by
  the backend as an **HttpOnly, SameSite=Lax cookie** scoped to `/api/auth`. It is never
  exposed to frontend JavaScript. The frontend calls `POST /api/auth/refresh` on app
  load to silently restore a session using this cookie, and again whenever it needs a
  new access token.

**Security tradeoff, documented explicitly:** the refresh cookie's `Secure` flag is
tied to `APP_ENV` (`settings.is_production`) — in local HTTP development it is not set
(browsers require HTTPS for `Secure` cookies), but it will be enforced automatically
once `APP_ENV=production` is set behind HTTPS. This is a standard, deliberate
development/production tradeoff, not an oversight.

**Reusable dependencies** (`app/core/deps.py`):
- `Depends(get_current_user)` — resolves and validates the Bearer access token,
  raising 401 for any missing/invalid/expired token or deactivated account.
- `Depends(require_role("officer"))` / `Depends(require_role("officer", "admin"))` —
  a dependency factory restricting an endpoint to specific `user_type` values. Not
  used by any endpoint yet (only `citizen` accounts exist so far), but the officer
  dashboard (Step 7) and admin dashboard (Step 11) can adopt it without any change
  to how authentication itself works.

## 7b. JWT and Refresh-Token Flow

```
Register  → POST /api/auth/register   → 201, UserOut (no tokens issued)
Login     → POST /api/auth/login      → 200, { access_token, user } + Set-Cookie: refresh_token
Access    → GET  /api/auth/me         → Authorization: Bearer <access_token> → 200, UserOut
Refresh   → POST /api/auth/refresh    → cookie: refresh_token → 200, new { access_token, user }
                                          + Set-Cookie: refresh_token (rotated)
                                          old refresh token is immediately revoked
Logout    → POST /api/auth/logout     → cookie: refresh_token → revokes it server-side, 204
                                          + clears the cookie
```

Refresh tokens are **rotated** on every use: each successful `/api/auth/refresh` call
revokes the token it was given and issues a brand new access/refresh pair. This means
a stolen refresh token can only be replayed once before it stops working, limiting the
damage window if one ever leaks.

## 7c. Role Architecture

`user_type` on `users` (citizen/officer/admin) is the primary account category, set
once at creation time and never trusted from client input. The separate `roles` /
`user_roles` tables (from Step 1) remain available for finer-grained permissions
within a `user_type` in later steps (e.g. multiple department-scoped roles for
officers) without ever needing to change the `users` table itself.

Only citizen self-registration exists in Step 2. Officer and admin accounts will be
created through a separate, controlled process in a later step — `register_citizen()`
in `app/services/auth_service.py` is the only account-creation path, and it hardcodes
`UserType.CITIZEN`.

## 7d. Citizen Registration Flow

1. Client submits `name`, `email`, `phone` (optional), `password` to `POST /api/auth/register`.
2. Pydantic (`RegisterRequest`) validates format: name length, email format, phone
   format, and password strength (≥8 characters, at least one letter and one digit).
3. `auth_service.register_citizen` checks for existing email/phone, hashes the password
   with Argon2id, and inserts the user with `user_type` hardcoded to `citizen`.
4. Response returns `UserOut` (id, name, email, phone, user_type, is_active, created_at)
   — never the password or its hash.
5. Registration does **not** automatically log the user in; the frontend redirects to
   `/login` so the citizen authenticates explicitly with their new credentials.

## 7e. Future Citizen Privacy Considerations

Authentication identity and grievance identity are kept **conceptually separate** by
design, in preparation for Step 6 (Citizen Identity Protection):

- `users`/`citizen_profiles` hold the citizen's real identity and contact details.
- Nothing in the JWT or the current API surface assumes an officer automatically sees
  a citizen's email, phone, address, or other personal information.
- Future grievance endpoints should expose only the minimum citizen information an
  officer needs to act on a complaint — governed by `citizen_profiles.privacy_level`
  and `identity_visibility` (already modeled in Step 1) — rather than joining and
  returning the full `users`/`citizen_profiles` record by default.
- `get_current_user`/`require_role` only ever resolve *who is calling the API*; they
  are not, and must not become, the mechanism by which grievance data decides what
  citizen information to reveal to an officer. That decision belongs to the future
  grievance/privacy modules, which can apply their own filtering on top of an
  already-authenticated request.

## 7f. Grievance Submission Architecture (Step 3)

**Ownership model.** Every write and read in the grievances API derives the
citizen from the authenticated JWT (`Depends(require_role("citizen"))` →
`current_user.id`), never from any client-supplied field. `GrievanceCreate`
has no `citizen_id` field at all, so even a malicious client that adds
`"citizen_id": "<someone else's id>"` to the request body has it silently
ignored by Pydantic — the server always uses `current_user.id`.

**Grievance number generation.** Grievance numbers (`GRV-<year>-<6-digit
sequence>`) are generated server-side only, via a dedicated
`grievance_sequences` table whose sole purpose is to hand out a unique,
monotonically increasing integer through its autoincrement primary key
(`SERIAL` on PostgreSQL, `AUTOINCREMENT` on SQLite). Using a real database
autoincrement column — rather than `COUNT(*) + 1` — means uniqueness is
guaranteed by the database itself under concurrent inserts, with no
race-condition window between "check the next number" and "use it." The
internal UUID primary key (`grievances.id`) is never returned by the API;
`grievance_number` is the only identifier citizens or the frontend ever see
or use.

**Ownership security on read.** `GET /api/grievances/{grievance_number}`
and the attachment-upload endpoint both check `grievance.citizen_id ==
current_user.id` before returning anything. If a grievance doesn't exist
*or* belongs to a different citizen, both cases return the same `404
Grievance not found` — the API never distinguishes "doesn't exist" from
"exists but isn't yours," which would otherwise let a citizen enumerate
valid grievance numbers by observing a 403-vs-404 difference.
`GET /api/grievances/my` filters by `citizen_id` at the query level, so it
is structurally impossible for it to return another citizen's grievances.

**Category → Department preparation.** `categories.department_id` is a
nullable FK to `departments`, added in this step's migration but not read
or written by any Step 3 code path. It exists purely so Step 5 (routing)
can attach a department to a category without a second schema migration —
see the design note in `app/models/category.py` for the full reasoning.

## 7g. File Storage Architecture

Attachment **bytes** are never stored in PostgreSQL — only metadata
(`attachments` table: filename, MIME type, size, relative path, SHA-256
hash). Files live on disk under:

```
backend/uploads/grievances/<grievance_number>/<generated-uuid>.<ext>
```

Security measures (`app/utils/file_storage.py`):
- The on-disk filename is **always** a freshly generated UUID plus a
  validated extension — the client's original filename is never used to
  build a filesystem path, which eliminates path-traversal by construction
  rather than by trying to detect and strip `../` sequences.
- Extension and MIME type are both checked against an allow-list (JPG,
  JPEG, PNG, PDF).
- File size is enforced while streaming to disk in chunks (aborting once
  the configured limit is exceeded), not trusted from a `Content-Length`
  header.
- The SHA-256 hash is always computed server-side from the bytes actually
  written to disk — a client-supplied hash is never accepted.
- The resolved destination path is re-verified to be inside the intended
  grievance directory immediately before writing, as defense in depth.

**Size limit:** 10 MB per file (`MAX_ATTACHMENT_SIZE_MB` in `.env`),
chosen as a reasonable default for photo/PDF evidence without allowing
large uploads to exhaust disk space during a hackathon deployment.

**Step 12 file security:** this step now
implement malware/antivirus scanning, content-sniffing beyond MIME-type
header checks, or image re-encoding to strip embedded metadata (EXIF GPS
data, etc.) — these remain documented as deployment extension points beyond the built-in checks
rather than silently skipped.

## 7h. Grievance Tracking Architecture (Step 4)

**Current status vs. history.** `grievances.status` remains the single
authoritative field for a grievance's current status — it is never
recomputed by scanning `grievance_status_history` at read time. The
history table exists purely to explain *how* the grievance arrived at its
current status; every write to `grievances.status` is paired, in the same
transaction, with a new `grievance_status_history` row, so the two can
never drift apart.

**Status transition policy** (`app/services/grievance_service.py`,
`ALLOWED_TRANSITIONS`):

```
SUBMITTED    → UNDER_REVIEW
UNDER_REVIEW → ASSIGNED | REJECTED
ASSIGNED     → IN_PROGRESS
IN_PROGRESS  → RESOLVED
RESOLVED     → CLOSED
REJECTED     → (terminal — no further transition)
CLOSED       → (terminal — no further transition)
```

`update_grievance_status()` is the single, centralized entry point for
changing a grievance's status. It rejects same-status no-ops and any
transition not explicitly listed above, updates `grievances.status` and
`grievances.updated_at`, and inserts the corresponding history row, all
within one transaction — if any part fails, the whole thing rolls back
(verified by a dedicated atomicity test: an invalid-transition attempt
leaves both the status and the history row count completely unchanged).

**No status-change endpoint yet, on purpose.** Step 4 deliberately does
not expose `update_grievance_status()` through any HTTP route — not to
citizens, not to any other role. The function is fully implemented and
tested (including live against PostgreSQL), ready for Step 7's officer
dashboard to build a properly role-gated router on top of it, but citizens
have no way to change their own or anyone else's grievance status through
the API. The only two grievance-reading endpoints Step 4 adds
(`GET /{grievance_number}` and `GET /{grievance_number}/history`) are
read-only and reuse the exact same `require_role("citizen")` + ownership
check (`citizen_id == current_user.id`, 404 either way if not) already
established in Step 3 — no new authentication or authorization logic was
introduced.

**Backfill for pre-Step-4 data.** Grievances created under Step 3 (before
`grievance_status_history` existed) have no history rows. Migration `0004`
calls `backfill_missing_status_history()` — the same function is unit
tested against SQLite and was verified live against PostgreSQL, where it
correctly created exactly one initial-SUBMITTED history record per
pre-existing grievance, using each grievance's own `submitted_at` as the
history row's `changed_at` (not the migration's run time). The function is
idempotent: it only inserts for grievances that currently have zero
history rows, so re-running it (or the migration) never creates
duplicates.

**Timestamp strategy.** All timestamps (`grievances.created_at` /
`updated_at` / `submitted_at`, `grievance_status_history.changed_at`) are
stored as timezone-aware `DateTime(timezone=True)` columns (`TIMESTAMPTZ`
in PostgreSQL), always in UTC. `changed_at` is set explicitly in
application code (`datetime.now(timezone.utc)`) at the moment of a status
transition, rather than relying solely on the database's `server_default
func.now()` — this was a deliberate fix after testing revealed that
SQLite's `CURRENT_TIMESTAMP` only has one-second resolution, which made
rapid successive status changes tie and sort unpredictably. The frontend
receives ISO 8601 UTC strings and converts them to the citizen's local
time only at render time (`Date.prototype.toLocaleString()`), so there is
exactly one place timezone conversion happens — never a manual offset
calculation.

## 7i. Privacy Architecture (Step 6)

**⚠ Step 5 gap, read this first.** The project roadmap lists "Step 5 —
Department Auto-Routing" as completed, but inspection of the actual
codebase at the start of Step 6 found no `grievance_assignments` table, no
routing service, and no migration for it. Step 5 was never actually built.
This materially affects what Step 6 could safely implement: the spec's
"Officer: Can access grievances assigned/authorized to their department"
rule has no data to enforce against — there is no record anywhere of which
officer belongs to which department's queue of grievances. Rather than
fabricate a fake restriction or silently skip the officer-facing pieces
entirely, Step 6 implements them with a clearly-flagged, narrower
authorization: **any authenticated officer/admin** can call the new
officer-facing endpoints for **any** grievance number, but every response
still fully respects `privacy_mode` — PII exposure is never broadened by
this gap, only the "is this the right officer for this grievance"
department-scoping is missing. This is called out in code comments at
`get_grievance_for_actor()` and the `/officer-view` route, and must be
tightened the moment real department/assignment data exists (Step 5 or 7).

**Core principle: three separate identities.**

```
AUTHENTICATION IDENTITY  (users table — who is logged in)
        ≠
GRIEVANCE-FACING IDENTITY (what the owning citizen sees about their own submission)
        ≠
INFORMATION REQUIRED BY OFFICER (privacy_mode-filtered subset, built field-by-field)
```

A citizen viewing their own grievance always sees everything they
submitted — `privacy_mode` never restricts a citizen's view of their own
data. It only governs what an *officer* sees.

**Privacy modes** (`grievances.privacy_mode`, chosen by the citizen at
submission and changeable afterward):

| Mode | Officer sees |
|------|----|
| `NORMAL` | Full grievance details + citizen's name + **masked** phone/email (e.g. `******1234`, `o***@example.com`) |
| `CONFIDENTIAL` | Full grievance details, no name/phone/email at all |
| `IDENTITY_PROTECTED` (default) | Same as CONFIDENTIAL, plus identity is only ever obtainable through the approved identity-reveal workflow below |

Regardless of mode, an officer never sees exact address/lat-long — only
coarse `city`/`state` — since precise geolocation is itself PII-adjacent.

**Default is `IDENTITY_PROTECTED`,** applied both to new grievances
(`GrievanceCreate.privacy_mode` default) and backfilled onto every
pre-existing grievance via migration `0005`'s column `server_default`.
This is safe: no code path reads `privacy_mode` to grant *broader* access
than `IDENTITY_PROTECTED` already permits — it only ever narrows what an
officer can see. The migration required an explicit `CREATE TYPE` call
before `ALTER TABLE ... ADD COLUMN`, which was itself a good catch from
live-PostgreSQL testing: unlike `CREATE TABLE`, `ALTER TABLE ADD COLUMN`
does **not** auto-create a new ENUM type, and failed with "type does not
exist" the first time this migration ran against real Postgres.

**Backend decides, never the frontend.** `app/services/privacy_service.py`
builds `OfficerGrievanceOut` field-by-field from the ORM object — it never
serializes `grievance.citizen` wholesale and lets the client hide fields.
For `CONFIDENTIAL`/`IDENTITY_PROTECTED`, `contact_name`/
`contact_phone_masked`/`contact_email_masked` are `None` in the JSON
response body itself, not merely unrendered by the UI — verified by a test
that greps the raw response text for the citizen's actual email/phone and
asserts they never appear.

**Identity-reveal workflow** (three steps, three different actors):

1. `POST /api/grievances/{grievance_number}/identity-reveal-requests` —
   any officer/admin, with a `reason` (min 10 chars). Creates a `PENDING`
   `IdentityRevealRequest`. **Never reveals anything by itself.**
2. `POST /api/identity-reveal-requests/{id}/review` — **admin only**
   (`require_role("admin")`; there is no officer self-approval path, and
   no per-officer permission model to build one on top of yet — that
   belongs to Step 7/11's admin tooling). Sets `APPROVED` or `REJECTED`,
   records `reviewed_by`/`review_remarks`/`reviewed_at`. A request can only
   be reviewed once — re-reviewing an already-decided request is rejected
   (409) rather than silently overwriting the earlier decision.
3. `GET /api/identity-reveal-requests/{id}/identity` — the **one**
   authorized disclosure point. Requires the request to be `APPROVED` *and*
   the caller to be the *original requester* (not any other officer/admin
   who happens to know the request id — approval authorizes a person, not
   a permission). Returns exactly `{name, phone, email}`, nothing else.
   Every successful call creates one `PrivacyAccessLog` row.

**Privacy access logging.** `data_accessed` stores field *names* only
(literally the string `"name,phone,email"`), never values — verified by a
dedicated test asserting the log row never contains the citizen's actual
email or phone substring. This table is intentionally narrow in scope: it
exists specifically for privacy-sensitive PII access, and Step 8's
comprehensive, tamper-proof, system-wide audit trail will eventually
subsume or integrate with it — Step 6 does not attempt to build that
broader system now.

**PII hygiene invariants verified this step:** no PII in JWT payloads
(only `sub`/`user_type`/`type`/`iat`/`exp`/`jti`), `password_hash` never
appears in any response (grievance detail, officer-view, or revealed-
identity), and cross-citizen access (`GET /api/grievances/{number}`)
remains blocked (404) regardless of `privacy_mode` — privacy filtering and
ownership enforcement are separate, independently-tested concerns.

## 7j. Department Routing Architecture (Step 5)

**Build-order note:** Step 5 was implemented after Step 6 in this project
(see section 4's note). Everything below was built to integrate with
Step 6's already-existing privacy system, not the other way around.

**Deterministic, not AI-based.** `app/services/routing_service.py` routes
purely by category→department mapping — no LLM, no external API call, no
non-deterministic behavior. This is intentional per the Step 5 spec: fast,
predictable, explainable, and trivially testable. Step 9's future
AI-assisted routing is expected to *consult or override* this service's
output, not replace its deterministic core.

**Routing algorithm** (`route_grievance(db, grievance, category)`):
1. If the grievance's category has a `department_id` mapping **and** that
   department is currently active, route there.
2. Otherwise, route to **General Grievance Cell** (itself required to be
   active — if even the fallback department is missing/inactive, this
   raises `NoFallbackDepartmentError`, a configuration error rather than
   a silent failure).

An inactive department can never receive a *new* automatic assignment,
even if it's the category's mapped department — enforced by construction
in the query itself (`Department.is_active.is_(True)`), not left to the
caller to check.

**Department assignment ≠ grievance status ASSIGNED.** These are
deliberately unrelated concepts that happen to share the word "assigned."
Routing a grievance to a department creates a `grievance_assignments` row
but **never** touches `grievances.status` — a freshly-submitted,
freshly-routed grievance is still `SUBMITTED`. The `GrievanceStatus.ASSIGNED`
enum value (Step 4) is reserved entirely for Step 7's future officer
workflow (an officer picking up a grievance) and is untouched by this step.
A dedicated test (`test_routing_does_not_change_status`) asserts this
distinction directly.

**Atomicity.** `route_grievance()` does not commit — it's called from
inside `grievance_service.create_grievance()`'s existing transaction,
right after the initial `SUBMITTED` status-history row is added and right
before the single `db.commit()`. Grievance creation, initial history, and
routing either all succeed together or all roll back together.

**Routing history vs. denormalized current department.** `grievance_assignments`
is the authoritative, append-only routing history (Step 5 only ever
creates one row per grievance, but the table is designed for Step 7 to
add more — e.g. manual re-routing). `grievances.department_id` is a
denormalized mirror of the latest assignment's department, added purely
so citizen-facing queries can join directly to `departments` without
also joining through `grievance_assignments` and picking the max
`assigned_at`. `routing_type`/`routed_at` exposed in API responses are
computed from the latest assignment row via `Grievance.current_assignment`
(a Python property), not stored redundantly.

**Fallback is explicit, not silent.** When routing falls back to General
Grievance Cell, the assignment row's `remarks` field records exactly why:
`"Automatic routing fallback: no active category department mapping."` —
distinguishing a deliberate fallback from a category that happens to be
correctly mapped to General Grievance Cell itself (like the seeded "Other"
category, which maps there directly with no remarks).

**Backfill.** Migration `0006` calls the same `backfill_missing_routing()`
function used in tests to route every grievance that predates Step 5
(all of Steps 3, 4, and 6's grievances) — idempotent, only touches
grievances with zero existing assignment rows, verified live against
PostgreSQL to correctly backfill all 3 pre-existing grievances with the
right department based on each one's actual category.

**Seeded departments** (migration `0006`, idempotent via
`ON CONFLICT (name) DO NOTHING`): Public Works, Water Supply, Electricity,
Sanitation, Public Transport, Public Safety, and Municipal Services
Departments, plus General Grievance Cell as the fallback. **Category
mappings**: Roads & Potholes and Drainage & Sewage → Public Works; Garbage
& Waste → Sanitation; Water Supply → Water Supply; Electricity →
Electricity; Street Lights and Government Services → Municipal Services;
Public Transport → Public Transport; Public Safety → Public Safety; Other
→ General Grievance Cell directly (not merely falling back there).

**Step 6 privacy integration — the critical part.** Routing and privacy
are kept as fully separate, non-overlapping responsibilities:

- **Routing decides WHERE** a grievance goes (`routing_service.py`) —
  it never reads or reasons about citizen PII at all. It only ever touches
  `grievance`, `category`, and `department` data.
- **Privacy decides WHAT** the recipient can see
  (`privacy_service.get_grievance_for_actor()`) — this function was
  *extended*, not duplicated, to also include `department`/`routing_type`/
  `routed_at` in its output. Routing information is always visible to an
  authorized officer regardless of `privacy_mode` (a department obviously
  needs to know which grievances were routed to it), but citizen PII
  remains exactly as privacy-gated as it was in Step 6 — `NORMAL` shows
  masked contact info, `CONFIDENTIAL`/`IDENTITY_PROTECTED` show none.
  Verified live against PostgreSQL: an `IDENTITY_PROTECTED` grievance
  correctly shows its department to an officer while `contact_name`/
  `contact_phone_masked`/`contact_email_masked` all remain `null`.
- No second privacy system was created, and no privacy check was
  duplicated inside `routing_service.py` — it has zero knowledge of
  `PrivacyMode` and does not need any, since it never touches identity data.

## 7k. Officer Dashboard Architecture (Step 7)

**Department routing vs. officer assignment — the core distinction.**
These are two independent facts, tracked in two separate tables:

```
grievance_assignments   -->  grievance → DEPARTMENT  (Step 5, automatic, at submission)
officer_assignments      -->  grievance → OFFICER      (Step 7, manual, via claim)
```

A grievance is routed to a department automatically and immediately at
submission (Step 5). An officer *within that department* may later
separately *claim* it (Step 7) — claiming never changes routing, and
routing never implies a claim. Conflating the two into one table would
have made it impossible to answer "which department should this go to"
independently of "who happens to be working it right now" — exactly the
mistake the spec warned against, and `app/models/officer_assignment.py`'s
docstring documents this reasoning directly.

**Department authorization — new in Step 7, deliberately narrow in
scope.** `app/services/officer_service.py` owns exactly one new
responsibility: resolving `current_user → officer_profile →
department_id → is the department active` server-side, and using that to
gate every officer-facing endpoint. It never re-implements privacy
filtering or status-transition rules — see below.

```python
def get_officer_department(db, officer) -> Department:
    profile = db.query(OfficerProfile).filter_by(user_id=officer.id).first()
    if profile is None or profile.department_id is None:
        raise OfficerNotAuthorizedError(...)
    department = db.query(Department).filter_by(id=profile.department_id).first()
    if department is None or not department.is_active:
        raise OfficerNotAuthorizedError(...)
    return department
```

Every officer endpoint calls this (directly or via `get_authorized_grievance`,
which additionally checks `grievance.department_id == department.id`)
before doing anything else. A department_id is **never** accepted from
the client in any officer request — there is no such field anywhere in
`schemas/officer.py`.

**Reused, not duplicated — the three pillars this step deliberately did
not reinvent:**

1. **Privacy filtering.** `privacy_service.get_grievance_for_actor()`
   (Step 6, unchanged in behavior) is called directly from the officer
   router for both the existing `/api/grievances/{n}/officer-view`
   endpoint and the new `/api/officer/grievances/{n}` endpoint. It was
   only *extended* — adding `attachments`/`status_history` fields to
   `OfficerGrievanceOut` — never rewritten. The same `NORMAL` /
   `CONFIDENTIAL` / `IDENTITY_PROTECTED` rules apply identically whether
   the officer arrived via the old Step 6 endpoint or the new Step 7 one.
2. **Status transitions.** `grievance_service.update_grievance_status()`
   (Step 4, byte-for-byte unchanged) is called from
   `officer_service.update_status_as_officer()` after the department check
   passes. All transition-rule validation (`SUBMITTED → UNDER_REVIEW`,
   etc.), the atomic status+history write, and history creation are 100%
   Step 4's existing code — Step 7 adds zero new transition logic, only
   the department-authorization gate in front of it.
3. **Department routing.** `routing_service.py` (Step 5) is not called
   from anywhere in Step 7 — officer endpoints only ever *read*
   `grievance.department_id`, never write it. Routing remains exclusively
   a Step 5/create-time concern.

**A note on `/api/grievances/{n}/officer-view` (Step 6) vs.
`/api/officer/grievances/{n}` (Step 7).** These look similar but serve
different purposes and were deliberately both kept:

- The Step 6 endpoint has no department restriction (a known, documented
  gap from when Step 6 was built before Step 5/7 existed). It was **not**
  retrofitted with department checking in this step, because doing so
  would have broken passing Step 6 tests that exercise officers with no
  `officer_profile` at all — and this project's hard constraint is to
  never regress existing tests. It remains available exactly as Step 6
  left it.
- The Step 7 endpoint (`/api/officer/grievances/{n}`) is the properly
  authorized surface real officer UI actually uses — department-checked,
  reachable only through `/officer/*` dashboard routes. This is the one
  application code should treat as canonical going forward.

**Claim workflow.** `POST /api/officer/grievances/{n}/claim` creates an
`OfficerAssignment` row (`assignment_type=MANUAL`, `assigned_by == officer_id`
for a self-claim) after the same department check. A grievance already
actively claimed by another officer cannot be claimed again (409) — "who
can assign officers" per the spec is answered here as "only the claiming
officer themselves, and only within their own department." Claiming does
**not** itself change `grievance.status` — that remains a fully separate
action via the status-update endpoint, exactly mirroring the manual test
script's sequence (review → claim → assign → in-progress → resolved as
four/five independent officer actions, not one combined operation).

**Officer account creation.** Public registration (`POST /api/auth/register`)
continues to force `user_type=citizen` unconditionally (Step 2 behavior,
unchanged) — there is still no endpoint anywhere that can create or
promote an account to `officer`. For development/testing, officer accounts
are created via direct SQL against `users`/`officer_profiles` (see README
for the exact commands) — this is intentional, documented, and matches
"officer creation/management belongs to future controlled admin
functionality" from the Step 7 spec.

**Dashboard statistics.** Computed via a single `GROUP BY grievances.status`
query filtered to the officer's department — never by fetching all
department grievances and counting in Python or in the frontend. Verified
live: two officers in different departments (Public Works vs. Water
Supply) see entirely different, correctly department-scoped counts against
the same PostgreSQL database.

**List filtering.** `GET /api/officer/grievances` applies `status`,
`category_id`, and `grievance_number` filters as SQL `WHERE` clauses
alongside the mandatory department filter — the frontend never fetches an
unfiltered department list and filters client-side.

## 7l. Audit Trail Architecture (Step 8)

**"Tamper-evident," not "tamper-proof."** A database administrator with
direct SQL access can still edit a row in `audit_logs` — nothing in
PostgreSQL itself prevents that. What this step guarantees is that such
an edit, or a deleted record, or a record inserted out of sequence,
becomes *detectable* by re-walking the chain
(`audit_service.verify_audit_chain()`). This distinction is intentional
and stated explicitly rather than overclaiming.

**One global chain, not one per grievance.** Every audit event —
regardless of which grievance, or none, it relates to — belongs to a
single chronological sequence, ordered by `sequence_number` (a
strictly-increasing integer, deliberately independent of `timestamp`,
which can theoretically tie under rapid writes). This makes whole-system
verification a single linear walk with nothing to accidentally leave out
of scope; `GET /api/audit/grievances/{n}` merely *filters* which already-
verified records get displayed, it never uses a separate, weaker
per-grievance chain.

**Hash chain mechanics.** Record N's `integrity_hash` is
`SHA256(canonical_json({sequence_number, previous_hash, actor_id, action,
entity_type, entity_id, grievance_id, old_value, new_value, metadata,
ip_address, user_agent, timestamp}))`, and record N+1's `previous_hash`
must equal record N's `integrity_hash`. The very first record's
`previous_hash` is an explicit genesis marker — 64 hex zero characters
(`audit_service.GENESIS_HASH`) — never an implicit or unpredictable
value. "Canonical JSON" means `json.dumps(..., sort_keys=True,
separators=(",", ":"), ensure_ascii=False)`, with UUIDs/datetimes/enums
converted to a fixed string form via a shared `_json_default()` function
used identically whether the value was just built at write time or
re-read from the database at verify time.

**A real bug this caught, worth documenting.** The first implementation
failed its own verification test with zero tampering involved: SQLite's
`DateTime(timezone=True)` column does not reliably round-trip `tzinfo` on
SELECT — a timestamp hashed as UTC-aware (`...+00:00`) at write time came
back *naive* (no offset) when re-read for verification, producing a
different `isoformat()` string and therefore a different hash purely from
storage round-tripping, not tampering. Fixed by normalizing any naive
timestamp back to UTC before hashing, in `_compute_integrity_hash()` —
a no-op for PostgreSQL (which round-trips `TIMESTAMPTZ` correctly) and
the correct fix for SQLite's behavior. This is the same category of
lesson Step 4 already ran into once (SQLite's `CURRENT_TIMESTAMP`
resolution) — timestamps that participate in ordering or hashing are
consistently the sharp edge across dialects in this project.

**Concurrency.** `record_audit_event()` acquires a PostgreSQL advisory
transaction lock (`pg_advisory_xact_lock`, released automatically at
commit/rollback) around the read-last-record-then-append sequence, so two
concurrent transactions can never both read the same "last record" and
each compute a conflicting `previous_hash`/`sequence_number`. This was
verified with a **genuine concurrency test against live PostgreSQL**
(`backend/scripts/verify_audit_concurrency.py`) — 20 real OS threads, each
with its own independent database connection, all racing to append a
record simultaneously. Result: all 20 writes present, zero duplicate
sequence numbers, zero errors, and `verify_audit_chain()` returned
`valid: true` afterward. (The SQLite pytest suite's own concurrency test
is intentionally lighter — rapid sequential appends, not real threads —
since the test harness's single shared `StaticPool` connection can't
represent genuine concurrent writers; the live-PostgreSQL script above is
where the actual concurrency guarantee was exercised.)

**Centralization — nothing hashes anything except this one module.**
`app/services/audit_service.py` is the *only* place that constructs an
`AuditLog` row or touches hash computation. `grievance_service.py`,
`officer_service.py`, and `privacy_service.py` each call
`record_audit_event()` as a plain function call — none of them import
`hashlib`, none of them know what canonical JSON looks like, and none of
them could accidentally drift from a shared convention because there is
only one convention, in one file.

**Transactional consistency.** Every audit call site was placed *before*
the enclosing function's `db.commit()`, using the same `db` session — so
if `create_grievance()`'s transaction rolls back for any reason, its
`GRIEVANCE_CREATED`/`GRIEVANCE_ROUTED` audit rows roll back with it. An
audit record can never describe an action that didn't actually happen.

**Where events are recorded** (all ten from the Step 8 minimum list):

| Action | Triggered from | Actor |
|---|---|---|
| `GRIEVANCE_CREATED` | `grievance_service.create_grievance()` | citizen |
| `GRIEVANCE_ROUTED` | same call, immediately after | `None` (system) |
| `GRIEVANCE_STATUS_CHANGED` | `grievance_service.update_grievance_status()` (Step 4, unmodified logic) | whoever calls it (currently only officers, via Step 7) |
| `OFFICER_CLAIMED` + `OFFICER_ASSIGNED` | `officer_service.claim_grievance()` — see note below | officer |
| `PRIVACY_MODE_CHANGED` | `privacy_service.update_privacy_mode()` | citizen (owner) |
| `IDENTITY_REVEAL_REQUESTED` | `privacy_service.create_identity_reveal_request()` | officer/admin |
| `IDENTITY_REVEAL_APPROVED` / `IDENTITY_REVEAL_REJECTED` | `privacy_service.review_identity_reveal_request()` | admin |
| `IDENTITY_ACCESSED` | `privacy_service.reveal_identity()` | officer/admin (the original requester) |

`GRIEVANCE_VIEWED` exists in the `AuditAction` enum for future use but is
**not** emitted anywhere yet — logging every read would be exactly the
"excessive audit noise" the spec warned against.

**Why claiming emits two events.** A self-claim (Step 7's only claim
mechanism today) is simultaneously two audit-worthy facts: the officer's
own action (`OFFICER_CLAIMED`) and the resulting assignment record
(`OFFICER_ASSIGNED`). Both are recorded from the same call. A future
supervisor-driven reassignment (not built yet) would emit only
`OFFICER_ASSIGNED`, with a different actor than the assigned officer.

**Sensitive-data discipline.** `old_value`/`new_value`/`metadata` never
contain raw phone numbers, email addresses, passwords, or tokens —
`IDENTITY_ACCESSED`'s `new_value` is literally `{"data_accessed":
"name,phone,email"}`, matching the exact field-names-only discipline
Step 6's `privacy_access_logs` already established, applied here to the
general-purpose chain too. Verified by a dedicated test that runs a full
identity-reveal workflow and then greps every `audit_logs` row's JSON
columns for the citizen's actual email/phone substrings, asserting they
never appear.

**Access restriction.** Both audit endpoints
(`GET /api/audit/grievances/{n}`, `GET /api/audit/verify`) require
`Depends(require_role("admin"))` — the same Step 2 dependency reused, no
new authorization mechanism. Citizens and officers both receive 403.
`GET /api/audit/verify` returns only `{valid, records_checked,
first_invalid_record?, reason?}` — never any record's actual content —
so it stays safe to expose even to a slightly broader admin audience than
the per-grievance trail endpoint.

**Append-only by construction.** There is no `PATCH`/`PUT`/`DELETE` route
anywhere in `app/routers/audit.py`, and no other router touches
`audit_logs` at all. This was verified directly: sending `PATCH`/`PUT`/
`DELETE` to `/api/audit/{id}` returns 404/405 — there is no route
matching that shape to even reject with 403; it simply does not exist.

**Tampering demonstration (performed live against PostgreSQL).** A
grievance was submitted, producing `GRIEVANCE_CREATED`/`GRIEVANCE_ROUTED`
audit rows; `GET /api/audit/verify` returned `valid: true`. A direct
`UPDATE audit_logs SET new_value = '{"status": "TAMPERED"}' WHERE
sequence_number = 21` was then run via `psql` — bypassing the application
entirely, exactly simulating an administrator or attacker with raw
database access. Re-running `GET /api/audit/verify` returned:

```json
{"valid": false, "records_checked": 21, "first_invalid_record": 21, "reason": "Integrity hash mismatch."}
```

The tampered record was then restored and verification confirmed
`valid: true` again — demonstrating both that the guarantee works and
that it isn't a permanent one-way trip (verification is a read-only
operation, run any time).

## 8. How Future Modules Will Connect

The intended grievance lifecycle:

```
Citizen → Complaint → Department → Officer → Resolution → Citizen Verification
```

Concretely:

- `User` (citizen) → `Grievance` (via `citizen_id` FK) — implemented in Step 3
- `Category` → `Grievance` (via `category_id` FK) — implemented in Step 3
- `Grievance` → `Attachment` (via `grievance_id` FK) — implemented in Step 3
- `Grievance` → `GrievanceStatusHistory` (via `grievance_id` FK) — implemented in Step 4
- `Grievance` → `PrivacyAccessLog` (via `grievance_id` FK) — implemented in Step 6
- `Grievance` → `IdentityRevealRequest` (via `grievance_id` FK) — implemented in Step 6
- `Grievance` → `GrievanceAssignment` (via `grievance_id` FK) — implemented in Step 5
- `Grievance` → `OfficerAssignment` (via `grievance_id` FK) — implemented in Step 7
- `Department` → `OfficerProfile` (already linked, Step 1) — Step 7 reads this to resolve an officer's department; no schema change was needed
- `Category` → `Department` (`department_id`, now actively populated — implemented in Step 5)
- `GrievanceAssignment` → `Department` (via `department_id` FK) — implemented in Step 5
- `OfficerAssignment` → `User` (via `officer_id` FK) — implemented in Step 7
- `Grievance` → `AuditLog` (via `grievance_id` FK, nullable/`SET NULL`) — implemented in Step 8
- `User` → `AuditLog` (via `actor_id` FK, nullable/`SET NULL`) — implemented in Step 8
- Future `grievances` → Step 10 `resolutions`, `resolution_evidence`,
  `resolution_disputes`, and `resolution_feedback`, each as a table with a foreign key back to `grievances.id`.
  Step 9's AI events will be recorded through the same
  `audit_service.record_audit_event()` every other step already uses,
  rather than a second logging mechanism.

Because every future table hangs off `users`, `departments`, `categories`, or
`grievances` via foreign keys, none of the Step 1–8 tables need to
change shape as later steps are added — only new tables and relationships are
introduced.

## 9. API Architecture

- Router-based: each feature area gets its own `APIRouter` in `app/routers/`,
  included in `app/main.py`. Step 1 added `health.py`; Step 2 added `auth.py`
  (`/api/auth/register`, `/login`, `/refresh`, `/logout`, `/me`); Step 3 added
  `categories.py` (`GET /api/categories`) and `grievances.py`
  (`POST /api/grievances`, `GET /api/grievances/my`,
  `GET /api/grievances/{grievance_number}`,
  `POST /api/grievances/{grievance_number}/attachments`); Step 4 added one more
  route to `grievances.py` (`GET /api/grievances/{grievance_number}/history`)
  and enriched the existing detail response with `status_history` and
  `updated_at`; Step 6 added three more routes to `grievances.py`
  (`PATCH /{grievance_number}/privacy`, `GET /{grievance_number}/officer-view`,
  `POST /{grievance_number}/identity-reveal-requests`) plus a new
  `privacy.py` router (`POST /api/identity-reveal-requests/{id}/review`,
  `GET /api/identity-reveal-requests/{id}/identity`); Step 5 adds a new
  `departments.py` router (`GET /api/departments`) and enriches
  `categories.py`'s and `grievances.py`'s existing responses with department/
  routing information — no new grievance-scoped route was needed for citizens,
  since "citizen sees their department" is just more fields on the existing
  detail/list responses; Step 7 adds a new `officer.py` router
  (`GET /api/officer/dashboard`, `GET /api/officer/grievances`,
  `GET /api/officer/grievances/{grievance_number}`,
  `POST /api/officer/grievances/{grievance_number}/claim`,
  `POST /api/officer/grievances/{grievance_number}/status`) — the Step 6
  `/api/grievances/{n}/officer-view` and Step 7's
  `/api/officer/grievances/{n}` both remain, serving different purposes
  (see section 7k for exactly why both were kept rather than merged);
  Step 8 adds a new `audit.py` router (`GET /api/audit/grievances/{n}`,
  `GET /api/audit/verify`) — deliberately read-only, with no
  create/update/delete route anywhere in it (see section 7l).
- Routers stay thin — they validate input via Pydantic schemas and delegate
  business logic to `app/services/` (`auth_service.py` from Step 2,
  `grievance_service.py` from Step 3, extended in Step 4 with
  `update_grievance_status()`/`backfill_missing_status_history()`, in Step 6
  with `get_grievance_by_number()`, and in Step 5 with department-aware
  eager-loading; `privacy_service.py` from Step 6 centralizes every privacy/
  identity-reveal decision; `routing_service.py` from Step 5 centralizes
  every routing decision; new `officer_service.py` from Step 7 centralizes
  department authorization and composes calls into the three services above
  — it never reimplements what they already do; new `audit_service.py` from
  Step 8 is the ONLY module that constructs an `AuditLog` row or computes a
  hash — `grievance_service.py`, `officer_service.py`, and
  `privacy_service.py` each call `record_audit_event()` as a plain function,
  never touching hashing directly).
- Response shapes are defined as Pydantic schemas in `app/schemas/`, keeping
  API contracts explicit and decoupled from ORM models. `UserOut` is the only
  shape of a `User` ever returned by the API — it has no `password_hash` field.
  `GrievanceOut`/`GrievanceListItem` never expose the internal `grievances.id`
  UUID, `AttachmentOut` never exposes `file_path`,
  `GrievanceStatusHistoryOut` never exposes `changed_by`, `OfficerGrievanceOut`/
  `RevealedIdentityOut` (`schemas/privacy.py`) are built explicitly rather than
  derived from any citizen-facing schema, Step 5's `DepartmentOut`/routing
  fields expose only what citizens/officers need (department name/contact
  info, routing type, timestamp) — never `grievance_assignments.assigned_by`
  or the full assignment history array — and Step 7's
  `OfficerGrievanceListItem`/`OfficerDashboardOut` (`schemas/officer.py`)
  never include any citizen PII at all, only grievance/category/status/claim
  metadata. Step 8's `AuditLogOut`/`AuditVerificationResult`
  (`schemas/audit.py`) never expose more than sequence/action/entity/
  old-new-value/timestamp — never the underlying hash-chain internals a
  malicious caller could use to reverse-engineer anything, and
  `AuditVerificationResult` on failure returns only a sequence number and
  a short category string, never record content.
- Protected endpoints declare their requirement explicitly via
  `Depends(get_current_user)` (or `Depends(require_role(...))`), defined once in
  `app/core/deps.py` and reusable by every router. Citizen-facing grievance
  endpoints use `Depends(require_role("citizen"))`; Step 6's/Step 7's
  officer-facing endpoints use `Depends(require_role("officer", "admin"))` or
  `Depends(require_role("officer"))` alone (Step 7's new `/api/officer/*`
  routes are officer-only — not admin — since department authorization only
  makes sense for an account with an `officer_profile`); the reveal-review
  endpoint and both of Step 8's new `/api/audit/*` endpoints use
  `Depends(require_role("admin"))` alone. `GET /api/departments`
  and `GET /api/categories` remain unauthenticated, same as before Step 5 —
  department/category names are non-sensitive reference data. No new
  authentication *mechanism* was introduced for Steps 5, 6, 7, or 8 — only
  new role combinations of the same Step 2 dependency, Step 7's department-
  authorization layer (section 7k), and Step 8's request-context middleware
  (`app/core/request_context.py`, section 7l) for capturing IP/user-agent
  without changing any existing service function's signature.

## 10. Local Development Architecture

- **Backend**: run directly with `uvicorn app.main:app --reload`, or via
  Docker (`docker-compose up`), against a local or containerized PostgreSQL.
- **Frontend**: run with `npm run dev` (Vite dev server on port 5173),
  configured via `VITE_API_BASE_URL` to point at the backend.
- **Database migrations**: managed exclusively through Alembic
  (`alembic upgrade head`); the app never calls `Base.metadata.create_all()`
  outside of the test suite, which uses in-memory SQLite for speed and
  isolation.

## Step 9 — AI Intelligence Architecture

Step 9 is an additive decision-support layer. The authoritative grievance fields and Step 1–8 services remain unchanged in responsibility. AI data is persisted in separate tables: `ai_analyses`, `ai_recommendations`, `ai_processing_logs`, `ai_complaint_clusters`, `ai_cluster_members`, `ai_sla_predictions`, `ai_alerts`, and `ai_response_drafts`.

### Provider boundary

`app.ai.providers` exposes an AI provider abstraction. `OllamaProvider` is the optional local development provider. `MockProvider` is the deterministic fallback. No OpenAI SDK or API key is required. Provider failure returns a controlled unavailable result and does not participate in registration, authentication, grievance submission, routing, officer claims, status changes, privacy operations, or audit-chain writes for those operations.

### Grounding and privacy

`app.ai.privacy.sanitize_grievance()` creates minimum-necessary provider context. It intentionally excludes citizen name, email, phone, authentication data and unnecessary identifiers. Complaint text is explicitly treated as untrusted data. Identity-protected grievances never send direct identity data to the provider. AI responses are requested as structured JSON where the provider supports it, and outputs are validated before persistence.

### Human-in-the-loop

AI recommendations are stored as `PENDING`. Authorized officers can move a recommendation to `ACCEPTED`, `REJECTED`, or `OVERRIDDEN`. The review state is the only authoritative outcome. AI never writes `grievances.category_id`, `department_id`, `status`, `citizen_id`, `privacy_mode`, or a final resolution.

### Features

The Step 9 layer provides multilingual analysis, reviewed voice transcription support, structured complaint extraction, priority/risk suggestions, duplicate detection without automatic merging, geographical hotspot analytics, emerging-issue analytics, officer copilot, grounded response drafts, resolution-evidence relevance analysis, explainability/confidence, hallucination protection, privacy sanitization, spam/abuse risk, SLA-risk prediction, citizen assistant, missing-information suggestions, and admin analytics.

Geographic and emerging-issue calculations use SQL/statistical logic rather than delegating arithmetic or clustering calculations to an LLM. Duplicate detection is deliberately advisory and never merges citizen records.

### Audit integration

Important AI actions use the existing Step 8 `audit_service.record_audit_event()` and are represented by additive Step 9 audit action values. Audit metadata contains safe task/provider/confidence references rather than raw prompts or sensitive model output.

### Failure behavior

If Ollama is unavailable, the provider boundary returns `available: false` or uses the deterministic fallback depending on configuration. Core grievance processing remains independent of AI. This makes AI optional in development and deployment.

### Frontend

Citizens receive a voice-input option that requires reviewing the transcription before submission and a citizen AI assistant scoped to their authenticated grievances. Officers receive a dedicated AI tools view for priority, duplicates, copilot, response drafting, resolution evidence analysis and SLA risk. Administrators receive aggregate AI analytics, hotspots, emerging issues and alerts without citizen PII.

All AI UI is labeled as AI-generated and human-review-required where applicable.

## Step 10 — Resolution & Citizen Verification

Step 10 introduces a separate resolution domain rather than adding mutable resolution fields to `grievances`. Migration `0010_add_resolution_workflow.py` is the only new migration; `0001`–`0009` remain historically unchanged.

### Resolution data model

`Resolution` records each officer resolution attempt. It contains the submitting officer, summary, actions taken, resolution date, remarks, optional completion percentage and external reference. The application exposes no update/delete route for resolution attempts, so previous attempts remain available as history.

`ResolutionEvidence` stores metadata only. Binary files remain under the existing upload root and are never stored in PostgreSQL. `ResolutionDispute` stores a citizen's dispute separately from both the original complaint and the resolution attempt. `ResolutionFeedback` stores optional citizen feedback and the acceptance record used to close a grievance.

### Status authority

The existing Step 4 `update_grievance_status()` remains the only status-writing service. Step 10 extends its transition policy with:

- `IN_PROGRESS → RESOLVED`
- `RESOLVED → CLOSED`
- `RESOLVED → IN_PROGRESS` for a citizen dispute

The officer status endpoint explicitly refuses direct `RESOLVED` and `CLOSED` transitions. Officers must submit a resolution to reach `RESOLVED`; citizens cannot submit status values. Only the authenticated citizen's acceptance service can perform `RESOLVED → CLOSED`.

### Citizen verification

The citizen-facing resolution page obtains the ordinary citizen-owned grievance view plus the resolution review view. Ownership is enforced server-side by the same Step 6/Step 3 ownership pattern. A citizen can never retrieve another citizen's resolution or evidence by grievance number.

Acceptance creates an append-only verification/feedback record and a Step 8 audit event before the centralized status transition commits `CLOSED`. Dispute creation records the reason, emits dispute/reopen audit events, and uses the centralized status transition to return the grievance to `IN_PROGRESS`.

### Evidence security

Resolution evidence reuses the existing attachment validation functions for extension and MIME allow-lists, streaming size enforcement and UUID filenames. Resolution paths are additionally scoped by validated grievance number and resolution UUID. Download endpoints resolve the target path and verify it remains below the configured upload root before returning a file.

### Privacy

No second privacy mechanism is introduced. Officer access starts with `officer_service.get_authorized_grievance()`, which resolves the officer's department from the authenticated officer profile. Citizen access starts with `grievance_service.get_owned_grievance()`. The existing privacy service remains responsible for officer-facing identity filtering.

### Audit

Step 10 adds these Step 8 audit actions:

- `RESOLUTION_SUBMITTED`
- `RESOLUTION_EVIDENCE_ADDED`
- `RESOLUTION_VIEWED`
- `RESOLUTION_ACCEPTED`
- `RESOLUTION_DISPUTED`
- `RESOLUTION_REOPENED`
- `CITIZEN_FEEDBACK_SUBMITTED`

All are written through `audit_service.record_audit_event()` and therefore remain inside the existing global SHA-256 hash chain.

### AI

Step 9's `POST /api/ai/grievances/{grievance_number}/resolution-analysis` remains the AI assistance boundary for resolution evidence. No Step 10 operation trusts AI output as an authoritative decision. In particular, AI cannot close a grievance or reject a citizen dispute.

### Internal notification hooks

`app/services/resolution_event_service.py` provides an in-process hook boundary for `RESOLUTION_READY_FOR_CITIZEN_REVIEW`, `RESOLUTION_ACCEPTED`, and `RESOLUTION_DISPUTED`. It has no external transport and is intentionally ready for a later notification step.

### Step 10 verification status

Python source, migrations and tests compile successfully, and Alembic reports `0010` as the migration head. Full pytest execution and frontend production build could not be executed in this isolated environment because required third-party dependencies were unavailable and outbound package installation is blocked. The project therefore must be run in the user's normal Docker/Python/Node environment for final live verification.

## Step 11 — Admin Dashboard & Governance

Step 11 is an additive governance layer. It does not introduce another authentication system or duplicate privacy, routing, officer authorization, AI, or audit services. Every `/api/admin/*` route uses `Depends(require_role("admin"))` from the existing authentication dependency.

### Authorization boundary

The authenticated `User.user_type` is the authoritative admin role. No request body or query parameter can elevate a citizen/officer to admin or select an arbitrary department. The frontend `AdminProtectedRoute` is only a UX guard; API authorization is always server-side.

### Admin data model

The existing schema already contains the fields required for the governance workflow: `users.is_active`, `officer_profiles.department_id/designation/employee_id`, `departments.is_active`, `categories.is_active/department_id`, grievance routing/assignment history, Step 6 privacy requests, Step 9 AI records, Step 10 resolution records and Step 8 audit records. Consequently migration `0011_add_admin_governance.py` does not create a redundant governance table. It only extends the PostgreSQL audit enums with the Step 11 administrative actions and a `CATEGORY` entity type. Migrations `0001`–`0010` remain untouched.

### Officer management

Admins can create officer accounts only through the admin API. Public registration remains hardcoded to `CITIZEN`. Officer creation hashes passwords using the existing Argon2 password utility, requires an active department, and enforces unique employee IDs. Department changes update the current officer profile only; existing officer assignment rows are retained as historical records. Deactivation is soft and retires active claims rather than deleting them.

### Department governance

Department deactivation is blocked for the `General Grievance Cell` fallback and for departments that still have active category mappings or non-terminal grievances. Category mappings can only target active departments. This preserves the Step 5 routing invariant that automatic routing never targets an inactive department. Historical grievance routing rows are not rewritten when a mapping changes.

### Category governance

Categories can be created, updated, mapped to active departments and deactivated. Existing grievances keep their original category and routing history. Mapping changes are recorded as `ADMIN_ROUTING_MAPPING_CHANGED` through the existing audit service.

### Privacy governance

The admin dashboard lists identity-reveal requests and provides approve/reject controls by calling the existing Step 6 `privacy_service.review_identity_reveal_request()`. The admin layer never reads citizen identity fields as a shortcut. The existing approval/reveal workflow and Step 8 audit events remain authoritative.

### Audit governance

`GET /api/admin/audit` exposes searchable, metadata-safe audit records. `GET /api/admin/audit/verify` invokes the existing `audit_service.verify_audit_chain()` and returns chain validity, records checked, first/last sequence and failure reason. There is deliberately no admin update/delete endpoint for `audit_logs`.

### AI governance

The admin AI view aggregates Step 9 `ai_analyses`, `ai_recommendations`, `ai_processing_logs` and SLA prediction data. It reports recommendation states, low-confidence counts, failures, providers and models without allowing administrators to rewrite historical AI records.

### Resolution governance

Step 10 data is aggregated for pending resolution work, grievances awaiting citizen verification, accepted feedback, disputes and repeated resolution attempts. The admin layer observes the resolution workflow; it does not bypass officer authorization or citizen acceptance.

### Analytics and privacy

Analytics are computed server-side from aggregate counts. No endpoint exposes citizen name, phone, email, authentication tokens or protected identity as part of aggregate analytics. Admin grievance oversight exposes operational fields and privacy mode but does not provide a new identity-reveal mechanism.

### Administrative audit actions

Step 11 adds the following actions to the existing global SHA-256 audit chain:

- `ADMIN_OFFICER_CREATED`
- `ADMIN_OFFICER_UPDATED`
- `ADMIN_OFFICER_DEACTIVATED`
- `ADMIN_DEPARTMENT_CREATED`
- `ADMIN_DEPARTMENT_UPDATED`
- `ADMIN_DEPARTMENT_DEACTIVATED`
- `ADMIN_CATEGORY_CREATED`
- `ADMIN_CATEGORY_UPDATED`
- `ADMIN_CATEGORY_DEACTIVATED`
- `ADMIN_ROUTING_MAPPING_CHANGED`
- `ADMIN_PRIVACY_REQUEST_REVIEWED`

These are appended through `audit_service.record_audit_event()` and therefore inherit the same chain ordering and integrity verification used by Steps 8–10.

### Step 11 frontend

The frontend adds `AdminProtectedRoute`, `AdminDashboardPage` and `AdminManagementPage`, with routes for `/admin/dashboard`, `/admin/grievances`, `/admin/officers`, `/admin/departments`, `/admin/categories`, `/admin/privacy`, `/admin/audit`, `/admin/ai` and `/admin/analytics`. The dashboard is aggregate-first; management forms call only the protected admin APIs.

### Step 11 verification status

The Step 11 source and migration compile successfully in the available environment. The actual full pytest suite, live PostgreSQL migration and production frontend build require the project's installed Python/Node dependencies and a running PostgreSQL environment; those runtime checks are not claimed as passed when unavailable. Static checks do confirm that migrations `0001`–`0010` were preserved and the new migration revision is `0011`.

## Step 12 — Notifications & Production Hardening

Step 12 introduces a centralized notification layer without changing the authoritative grievance workflow. `notification_event_service.py` is a small in-process lifecycle boundary; `notification_service.py` is the single notification creation/delivery coordinator. Grievance, officer and resolution services emit events after successful transactions instead of embedding SMTP/Web Push code in business logic.

### Notification data model

Migration `0012_add_notifications.py` creates:

- `notifications` — durable in-app notification history with ownership, event idempotency key and optional grievance reference.
- `notification_preferences` — one row per user for email/browser channel preferences.
- `push_subscriptions` — multiple browser/device subscriptions per user.

There are deliberately **no SMS fields or tables**.

### Delivery reliability

Notification rows are committed independently after the originating business transaction succeeds. A small worker pool performs SMTP/Web Push delivery. Provider failures are caught and logged; they do not roll back grievance status, resolution submission, citizen verification or audit writes. The event key prevents duplicate notification creation for the same recipient/event combination.

### Email

`email_service.py` uses Python's standard SMTP library and environment configuration. No credentials are hard-coded. Templates contain grievance number, status/update, timestamp and application URL without unnecessary identity or complaint detail. Disabled/unconfigured SMTP is treated as an expected no-delivery state.

### Browser push

`push_notification_service.py` uses Web Push with VAPID when the optional `pywebpush` dependency and VAPID settings are present. The frontend service worker is `public/sw.js`. The frontend never receives the VAPID private key. Permission is requested explicitly before subscription registration.

### Notification ownership

All notification endpoints require the existing authenticated-user dependency. Queries are filtered by `Notification.user_id == current_user.id`, so a user cannot enumerate or mark another user's notifications. Push subscriptions are similarly scoped to the authenticated user.

### Privacy

Notification messages deliberately avoid protected citizen identity and sensitive complaint detail. Identity-protected grievances use the same citizen/department authorization rules as the underlying workflow. Browser previews are generic enough not to disclose confidential complaint content.

### SLA notifications

Step 9 SLA prediction data remains authoritative for risk calculation. Step 12 does not create a second SLA model. The notification layer provides the `SLA_WARNING` notification type and delivery boundary for an existing SLA-warning producer/scheduler; a deployment may invoke that producer periodically without duplicating SLA calculation logic.

### Security hardening

The FastAPI application adds `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and `Permissions-Policy`, with CSP/HSTS in production. Production startup rejects the development secret and wildcard CORS. Request content length is bounded above the configured attachment limit. Existing authentication rate limiting remains in-memory for development; shared Redis-backed state is the recommended production deployment for multiple backend instances.

Attachment handling now performs basic file-signature checks for PDF, PNG and JPEG in addition to the existing extension/MIME/size/path protections. The application does not claim antivirus scanning; an external scanner remains an explicit deployment extension point.

### Health and readiness

- `/api/health` — process liveness.
- `/api/health/db` — database connectivity.
- `/api/health/ready` — readiness with database connectivity.

Health responses do not expose credentials or internal connection details.

### Audit integration

Notification actions use the existing Step 8 audit service. No second audit store exists. Notification delivery results are auditable while raw credentials, tokens and protected citizen data remain excluded.

### Step 12 frontend

The React frontend adds `NotificationBell`, `NotificationCenterPage`, `NotificationPreferencesPage` and a service worker. Notification links route to the relevant grievance page. Browser permission is explicit and browser-off users continue to use email/in-app notifications.

### Step 12 verification status

The implementation is designed to preserve migrations `0001`–`0011` and uses `0012` as the sole new migration. Runtime verification of PostgreSQL, full tests, frontend build, SMTP and VAPID delivery must be performed in the project's working environment; external provider delivery is never claimed unless actually observed.

## Step 13: Public Statistics and Civic Ranking Architecture

### Public aggregation boundary
All Step 13 public routes live under `/api/public/statistics` and have no authentication dependency. They return only aggregate fields. The service never serializes a `Grievance`, `User`, attachment, address, description, email, phone number, or protected-identity record. A default minimum aggregation threshold of 5 suppresses detailed output for small geographic/filter cohorts.

### Geographic hierarchy
The hierarchy is `state -> district -> taluka -> village`. Step 13 reuses the existing `state` field and adds only the missing nullable `district`, `taluka`, and `village` fields in migration 0013. Existing `city`, coordinates, pincode, and grievance submission behavior are preserved. Selector choices are derived from distinct values stored in the database rather than hard-coded lists.

### Metrics
Resolution rate = grievances currently `RESOLVED` or `CLOSED` / total grievances in the eligible aggregate. Average resolution time = mean duration from `submitted_at` to the stored Step 10 `resolution_date`. Response time = mean duration from submission to the first non-initial Step 4 status-history event. Pending count includes `SUBMITTED`, `UNDER_REVIEW`, and `ASSIGNED`. Dispute rate used by ranking = Step 10 disputes / resolved-or-closed volume.

### Civic Performance Score
The default official formula is `0.40 * resolution_rate + 0.25 * timeliness_score + 0.20 * satisfaction_score + 0.15 * low_dispute_score`. `timeliness_score = max(0, 100 - average_resolution_days / target_days * 100)`, with a default target of 30 days. Satisfaction maps the Step 10 1–5 rating to 0–100. `low_dispute_score = max(0, 100 - dispute_rate)`. Missing satisfaction/timeliness evidence contributes zero rather than being fabricated. SLA is not an official component in Step 13 because the existing Steps 1–12 schema has no authoritative department/category SLA target.

Rankings are deterministic, reproducible, ordered by score then grievance volume then location name, and exclude cohorts below the minimum sample size. Grievance volume is not a score component. The same method is used when a category filter is supplied.

### Governance and audit
`civic_ranking_config` stores the public methodology weights, minimum sample threshold, and timeliness target. Admins can inspect governance and update configuration, but cannot directly set a location's score. Weights must sum to 1.0. Configuration changes call the existing Step 8 `record_audit_event` and use the new `CIVIC_RANKING_CONFIG_CHANGED` action; no second audit mechanism exists.

### Performance
Counts, status distributions, trend buckets, category/department grouping, ranking timing, satisfaction, and dispute metrics are server-side SQL aggregations. Ranking metrics are batched by geographic location rather than queried once per location, avoiding the previous N+1 pattern. The frontend receives pre-aggregated data only. No duplicated statistics counters are stored in Step 13.

### Most improved and category leaderboards
Most-improved rankings compare the current period with the immediately preceding period at the selected geographic level. A location must meet the minimum sample threshold in both periods before it can appear. Category leaderboards reuse the exact same Civic Performance Score after scoping the eligible grievances to the selected existing Step 3 category; no second category system exists.

### Public API and frontend
Endpoints: `/api/public/statistics[/summary]`, `/trends`, `/categories`, `/departments`, `/rankings`, `/rankings/{level}`, `/rankings/{level}/category/{category_id}`, `/most-improved`, `/location`, and `/methodology`. The React `/statistics` page is public and provides cascading geographic selectors, KPI cards including pending/dispute rates and response time, trends with per-bucket privacy suppression, breakdowns, a Civic Performance League, most-improved areas, category leaderboards, privacy suppression messaging, and score-component explanations.

### Migration and verification
Migration `0013_add_public_statistics.py` is the only new migration; migrations 0001–0012 are unchanged. In the provided execution environment, Python compilation succeeded, but the complete pytest suite could not start because `passlib` is not installed and package installation has no network access. The frontend build could not start because `vite`/`node_modules` is not installed. Live PostgreSQL migration verification therefore remains to be run in the project's Docker/development environment; no success is claimed for those blocked checks.

## Step 14 — Government Project Transparency

### Project lifecycle
Government projects are UUID-backed records with a public project number (`PRJ-YYYY-NNNNNN`), department, shared geographic fields (`state`, `district`, `taluka`, `village`), dates, financial fields, responsible organizational information, and deterministic progress/schedule state.

### Status and schedule state
Authoritative status transitions are validated server-side. Public schedule state is derived from dates and progress: `COMPLETED`, `DELAYED`, `AT_RISK`, or `ON_SCHEDULE`. A missed expected completion date deterministically yields `DELAYED` until completion.

### Milestones and history
Milestones retain planned and actual dates, completion percentage, status, and evidence. Project updates preserve historical change records instead of silently replacing important project history.

### Public transparency and privacy
Public endpoints expose only public projects and public documents/photos. Citizen identity, protected grievance details, private officer contact information, authentication information, and private project evidence are not exposed. Project–grievance links are explicit administrator-controlled relationships; geographic proximity alone never creates a link.

### Project following and notifications
Authenticated citizens can follow/unfollow public projects. Followers are not publicly enumerated. Followed-project updates use the existing Step 12 email/browser notification delivery path; SMS is not implemented.

### Audit integration
Step 14 extends the existing Step 8 audit enums and calls the central audit service for project creation, updates, status/progress changes, milestones, public evidence, department changes, completion, and grievance linking. No second audit chain is introduced.

### APIs
Public APIs include project listing/detail, categories, departments, statistics, performance, timeline, and public-safe grievance summaries. Authenticated APIs support follow/unfollow and followed-project listing. Admin APIs support project CRUD, milestones, evidence, photos, and controlled grievance linking.

### Migration 0014
Migration `0014_add_government_projects.py` adds project sequences, government projects, milestones, project updates, documents, photos, grievance links, followers, and Step 14 audit entity/action enum values. Migrations 0001–0013 are unchanged.


## Step 15 — Existing-Work Intelligence

Step 15 adds a citizen-controlled pre-submission check that looks for existing grievances and public government projects that may already address the reported problem. Candidate retrieval is narrowed by category, geography, status and recency before similarity scoring. If an Ollama Step 9 provider is configured, it may refine the top candidate scores; otherwise the deterministic similarity fallback remains authoritative for the recommendation.

The result is `NO_MATCH`, `POSSIBLE_MATCH`, or `STRONG_MATCH`. The warning is advisory only: citizens can always submit a new grievance. When they submit anyway, the system records the relationship and the citizen's reason/action without merging or deleting grievances.

Existing grievance results expose only public-safe fields. Government project matches reuse Step 14 project data and project following. Officer users can review possible matches and mark them confirmed or rejected. Existing Step 8 audit logging, Step 12 notifications, Step 9 AI provider infrastructure, and Step 14 project following are reused rather than duplicated.

Migration `0015_add_existing_work_intelligence.py` creates `existing_work_matches` with mutually exclusive grievance/project targets, confidence, explanation, citizen action, and human-review state.

The complete Civic Twin, Project Reality Check, and later Civic Intelligence features remain intentionally outside Step 15.
