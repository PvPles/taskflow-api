# TaskFlow API

A task/project management REST API (teams, projects, tasks, comments) built to
show **production discipline in a small, honest codebase** — the product is
deliberately boring so the engineering can be the point.

[![CI](https://github.com/PvPles/taskflow-api/actions/workflows/ci.yml/badge.svg)](https://github.com/PvPles/taskflow-api/actions)

## Highlights

- **Real auth, not a toy** — Argon2 password hashing, short-lived JWT access
  tokens (15 min), and opaque refresh tokens stored **SHA-256 hashed**,
  **rotated on every use**, with **reuse detection**: replaying a used refresh
  token revokes the whole token family.
- **Keyset (cursor) pagination** on task lists with a stable `(created_at, id)`
  tiebreaker and a backing composite index — pages stay correct while rows are
  inserted or deleted, and the DB seeks instead of counting offsets.
- **Per-user rate limiting** via an in-process token bucket (`429` + `Retry-After`).
- **Structured JSON logging** — one line per request with a request ID, echoed
  in every response header and every error body for end-to-end tracing.
- **Liveness vs readiness split** — `/health` (process up) vs `/health/ready`
  (database reachable), the distinction load balancers actually need.
- **Infrastructure as code** — the entire AWS deployment (VPC, ALB, EC2,
  CloudWatch, optional ACM/HTTPS) is Terraform; no console clicking.
- **Tested for real** — 42 tests at ~97% coverage, run on in-memory SQLite
  locally and against a **real Postgres container in CI**.

## Architecture

```mermaid
flowchart LR
    Client -- HTTPS --> ALB[Application Load Balancer]
    ALB -- HTTP --> EC2[EC2 instance]
    subgraph EC2 [EC2 · Docker]
        API[FastAPI container]
        DB[(PostgreSQL container)]
        API --> DB
    end
    API -- structured JSON logs --> CW[(CloudWatch Logs)]
```

Single-instance by design: the API and Postgres run as Docker containers on one
EC2 instance behind an ALB. That's the right size for this project — scaling
notes live in [Design decisions](#design-decisions).

## Tech stack

| Layer | Choice |
| --- | --- |
| Language | Python 3.12 |
| Web framework | FastAPI (auto-generated OpenAPI docs) |
| Data | SQLAlchemy 2.0 (sync) · PostgreSQL 16 · Alembic migrations |
| Auth | PyJWT (HS256) · argon2-cffi |
| Tests | pytest (SQLite fast path locally, Postgres in CI) |
| Quality | ruff (lint + format), 70% coverage gate |
| Packaging | Docker · docker compose |
| Infra | Terraform (AWS: VPC, ALB, EC2, ACM, CloudWatch, IAM) |
| CI/CD | GitHub Actions: lint → test → terraform validate → publish image to GHCR |

## Run it locally

One command brings up Postgres and the API, runs migrations, and serves the app:

```bash
docker compose up --build
```

Then:

- API: <http://localhost:8000>
- Interactive docs (Swagger UI): <http://localhost:8000/docs>
- Readiness check: <http://localhost:8000/health/ready> → `{"status":"ready"}`

Migrations (`alembic upgrade head`) run automatically on startup, and the API
waits for Postgres to be healthy first. Stop with `docker compose down` (add
`-v` to also wipe the database volume).

## API overview

Four endpoint groups, all under `/api/v1` and documented interactively at
`/docs`:

- **auth** — `register`, `login`, `refresh`, `logout`, `me`
- **projects** — CRUD, plus members (add/remove by email; owner-gated)
- **tasks** — CRUD, assignment, validated status transitions, cursor-paginated lists
- **comments** — add / list / delete on a task

### Example: register → login → create a project

```bash
BASE=http://localhost:8000/api/v1

# 1. Register
curl -s -X POST $BASE/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"ada@example.com","password":"correct-horse-battery","display_name":"Ada"}'

# 2. Login — capture the access token
TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ada@example.com","password":"correct-horse-battery"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 3. Create a project (authenticated)
curl -s -X POST $BASE/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Website relaunch","description":"Q3 marketing site"}'
```

Errors always use one envelope, and the `request_id` matches the `X-Request-ID`
response header so any failure is traceable to a single log line:

```json
{ "error": { "code": "not_found", "message": "...", "request_id": "abc123" } }
```

## Live demo

The AWS stack is designed to be brought up on demand and torn down after (see
[Deploy to AWS](#deploy-to-aws)) rather than left running, to keep costs at ~€0.

<!-- screenshots go here after a deploy run:
     - Swagger UI on the live ALB URL
     - CloudWatch dashboard with real traffic
     - a structured JSON log line showing a request_id
-->

## Deploy to AWS

Everything is in [terraform/](terraform/) — `terraform apply` goes from an empty
account to a running, load-balanced API. Full walkthrough, cost breakdown, and
the decision log (why no NAT gateway, why Dockerized Postgres over RDS) are in
[terraform/README.md](terraform/README.md).

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # set at least app_image
terraform init
terraform apply                                # outputs the live api_url
# ... capture screenshots for the Live demo section ...
terraform destroy                              # stops all billing
```

Key variables: `app_image` (the GHCR image CI publishes), optional `domain_name`
+ `route53_zone_id` (enables ACM/HTTPS), optional `alert_email` (CloudWatch
alarms + a $10/month budget guard). Designed for on-demand use, **not** a
permanent always-on deployment — cost control is part of the exercise.

## Testing

```bash
# Fast path — in-memory SQLite, no services needed
pip install -e ".[dev]"
pytest

# Integration path — the same suite against real Postgres (what CI runs)
docker compose up -d db
TEST_DATABASE_URL=postgresql+psycopg://taskflow:taskflow@localhost:5432/taskflow_test pytest
```

The suite includes unit-level tests per module and one end-to-end journey test
(`tests/test_e2e_journey.py`) that exercises register → project → members →
tasks → transitions → comments → pagination → delete in a single flow. CI runs
lint, the full suite against Postgres with a 70% coverage gate, `terraform
validate`, and publishes the Docker image to GHCR on `main`.

## Data model

```mermaid
erDiagram
    USERS ||--o{ REFRESH_TOKENS : has
    USERS ||--o{ PROJECTS : owns
    USERS ||--o{ PROJECT_MEMBERS : joins
    PROJECTS ||--o{ PROJECT_MEMBERS : has
    PROJECTS ||--o{ TASKS : contains
    USERS ||--o{ TASKS : "assigned to"
    TASKS ||--o{ COMMENTS : has
    USERS ||--o{ COMMENTS : writes
    USERS {
        uuid id PK
        string email UK
        string password_hash
        string display_name
        bool is_active
    }
    PROJECTS {
        uuid id PK
        string name
        uuid owner_id FK
    }
    PROJECT_MEMBERS {
        uuid project_id PK_FK
        uuid user_id PK_FK
    }
    TASKS {
        uuid id PK
        uuid project_id FK
        string title
        string status
        uuid assignee_id FK
        timestamptz due_at
    }
    COMMENTS {
        uuid id PK
        uuid task_id FK
        uuid author_id FK
        text body
    }
```

### Task lifecycle

```mermaid
stateDiagram-v2
    [*] --> todo
    todo --> in_progress
    todo --> done
    in_progress --> todo
    in_progress --> done
    done --> todo : reopen
```

`done → in_progress` directly is rejected with `409 invalid_status_transition` —
a done task must be reopened first. Enforced server-side and covered by tests.

## Design decisions

- **Sync SQLAlchemy over async** — simpler code and tests; this API is not
  I/O-bound enough at portfolio scale to justify async complexity.
- **Refresh tokens are opaque random strings, stored as SHA-256 hashes** — a DB
  leak doesn't expose usable tokens. JWTs are used only for short-lived access.
- **Reuse detection** — a revoked refresh token being replayed revokes every
  active token for that user (assume the token leaked).
- **404, not 403, for non-members** — outsiders can't distinguish "exists but
  blocked" from "doesn't exist", so IDs leak nothing. 403 is reserved for
  members lacking a specific right (e.g. owner-only actions).
- **Project membership instead of a separate team entity** — same authorization
  signal, half the API surface; teams could wrap projects later without a schema
  break.
- **In-process token-bucket rate limiting** (per user, per IP when anonymous) —
  correct for a single-instance deployment. Scaling out would move bucket state
  behind the same interface; deliberately not done here.
- **SQLite locally, Postgres in CI** — portable column types (`sa.Uuid`,
  timezone-aware `DateTime` with Python-side defaults) let the identical suite
  run on both.

## Cost note

Runs on **~€1–2/month** on a new AWS account (EC2 t3.micro and the ALB are both
free-tier for 12 months; ~€1.30 is the EBS volume), or **~€26/month** at full
price — the ALB dominates. `terraform destroy` stops all billing; full breakdown
in [terraform/README.md](terraform/README.md).

## License

MIT — see [LICENSE](LICENSE).
