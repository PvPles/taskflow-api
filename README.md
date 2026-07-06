# TaskFlow API

A task/project management REST API — projects, members, tasks, comments, deadlines.
The product is deliberately boring; **the engineering is the point**: refresh-token
rotation, Alembic migrations, integration tests against real Postgres in CI,
structured JSON logging, cursor pagination, and per-user rate limiting.

[![CI](https://github.com/YOUR_GITHUB/taskflow-api/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_GITHUB/taskflow-api/actions)

## Architecture

```mermaid
flowchart LR
    C[Client] -- HTTPS --> ALB[Application Load Balancer\nTLS via ACM]
    ALB --> API[FastAPI in Docker\non EC2]
    API --> PG[(PostgreSQL)]
    API -- structured JSON logs --> CW[CloudWatch]
```

Every request:

1. Rate limiter (token bucket, per user) — over the limit means `429` + `Retry-After`.
2. JWT access token validated (15-min expiry). Expired? `POST /auth/refresh` with the
   refresh token (7-day expiry, stored **hashed**, **rotated on every use**, replay
   of a used token revokes the whole session family).
3. Business logic runs against Postgres via SQLAlchemy 2.0.
4. One structured JSON log line per request: request ID, user ID, latency, status.
5. Errors always use the same envelope:

```json
{ "error": { "code": "not_found", "message": "...", "request_id": "abc123" } }
```

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
    REFRESH_TOKENS {
        uuid id PK
        uuid user_id FK
        string token_hash UK
        timestamptz expires_at
        timestamptz revoked_at
        uuid replaced_by_id FK
    }
    PROJECTS {
        uuid id PK
        string name
        text description
        uuid owner_id FK
    }
    PROJECT_MEMBERS {
        uuid project_id PK_FK
        uuid user_id PK_FK
        timestamptz added_at
    }
    TASKS {
        uuid id PK
        uuid project_id FK
        string title
        string status
        uuid assignee_id FK
        timestamptz due_at
        uuid created_by FK
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
a done task must be reopened first. Enforced server-side, covered by tests.

## Run it locally

```bash
docker compose up --build
# API:      http://localhost:8000
# OpenAPI:  http://localhost:8000/docs
```

Migrations run automatically on startup (`alembic upgrade head`).

### Development without Docker

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
pytest                          # fast suite on in-memory SQLite
```

To run the same suite as integration tests against real Postgres (what CI does):

```bash
docker compose up -d db
set TEST_DATABASE_URL=postgresql+psycopg://taskflow:taskflow@localhost:5432/taskflow_test
pytest
```

## API surface (v0.2)

| Method | Path | Notes |
| --- | --- | --- |
| POST | /api/v1/auth/register | 201, email normalized to lowercase |
| POST | /api/v1/auth/login | Returns access + refresh token pair |
| POST | /api/v1/auth/refresh | Rotates the refresh token (single-use) |
| POST | /api/v1/auth/logout | Revokes the given refresh token 🔒 |
| GET | /api/v1/auth/me | Current user 🔒 |
| POST | /api/v1/projects | Create; caller becomes owner 🔒 |
| GET | /api/v1/projects | Projects I own or joined 🔒 |
| GET/PATCH/DELETE | /api/v1/projects/{id} | PATCH/DELETE owner-only 🔒 |
| GET/POST | /api/v1/projects/{id}/members | Add member by email (owner-only) 🔒 |
| DELETE | /api/v1/projects/{id}/members/{user_id} | Owner-only 🔒 |
| POST | /api/v1/projects/{id}/tasks | Any member; starts in `todo` 🔒 |
| GET | /api/v1/projects/{id}/tasks | Cursor-paginated; `?status=`, `?assignee_id=`, `?limit=`, `?cursor=` 🔒 |
| GET/PATCH/DELETE | /api/v1/tasks/{id} | Status transitions validated; DELETE = creator or owner 🔒 |
| POST/GET | /api/v1/tasks/{id}/comments | Any member 🔒 |
| DELETE | /api/v1/comments/{id} | Author or project owner 🔒 |
| GET | /health | Liveness probe (rate-limit exempt) |

Task-list pagination: response is `{ "items": [...], "next_cursor": "..." }`.
Pass `cursor` back to get the next page; `next_cursor: null` means the end.
Cursors are keyset-based `(created_at, id)`, so pages stay consistent while
rows are inserted or deleted — no skipped or duplicated items, and the DB
seeks via an index instead of counting offset rows.

## Decisions

- **Sync SQLAlchemy over async** — simpler code and tests; this API is not
  I/O-bound enough at portfolio scale to justify async complexity.
- **Refresh tokens are opaque random strings, stored as SHA-256 hashes** — a DB
  leak doesn't leak usable tokens. JWTs only for short-lived access tokens.
- **Reuse detection** — a revoked refresh token being replayed revokes every
  active token for that user (assume the token leaked).
- **404, not 403, for non-members** — outsiders can't distinguish "project
  exists but I'm blocked" from "project doesn't exist", so IDs leak nothing.
  403 is reserved for members lacking a specific right (e.g. owner-only actions).
- **Project membership instead of a separate team entity** — same authorization
  signal, half the API surface; teams could wrap projects later without schema
  breakage.
- **Rate limiting: in-process token bucket** (per user, per IP for anonymous) —
  correct for a single-instance deployment, which this is. Scaling out would
  move bucket state to Redis behind the same interface.
- **SQLite for fast local tests, Postgres in CI** — models use portable types
  (`sa.Uuid`, timezone-aware `DateTime`) so the identical suite runs on both.
- **Postgres: RDS vs Docker-on-EC2** — decided in week 4; see `terraform/README.md`.

## Roadmap (5 weeks)

- [x] **Week 1 — Foundation**: auth (register/login/refresh/logout/me) with
  refresh-token rotation + reuse detection, structured JSON logging with request
  IDs, error envelope, Alembic migration 0001, Docker + compose, CI with Postgres
  integration tests and a 70% coverage gate
- [x] **Week 2 — Domain**: projects with membership + ownership checks, tasks
  with assignment and validated status transitions, migrations 0002–0003
- [x] **Week 3 — Production polish**: comments (migration 0004), cursor-based
  pagination for task lists, per-user token-bucket rate limiting, OpenAPI polish
- [x] **Week 4 — Infrastructure**: Terraform — VPC, security groups, EC2, ALB,
  ACM cert (optional, domain-gated), CloudWatch log group, IAM; configuration
  validated against the AWS provider schema; CI publishes the image to GHCR
- [ ] **Week 5 — Ship**: `terraform apply` with real AWS credentials, smoke
  tests against the live ALB, record the live URL + screenshots here

## Deployment

All infrastructure is in [terraform/](terraform/) — VPC, security groups, EC2
(running the GHCR image via Docker), ALB with `/health` checks, optional
ACM/HTTPS, CloudWatch logs. See [terraform/README.md](terraform/README.md) for
the apply/destroy walkthrough and the decision log (why no NAT gateway, why
Dockerized Postgres instead of RDS).

## Cost note

Runs on **~€1–2/month** on a new AWS account (EC2 t3.micro and the ALB are both
free-tier for 12 months; you pay ~€1.30 for the EBS volume), or **~€26/month**
at full price — the ALB is most of that. `terraform destroy` stops all billing;
full breakdown in [terraform/README.md](terraform/README.md).
