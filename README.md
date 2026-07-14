# TaskFlow API

A REST API for managing projects, tasks, and comments across a team. The domain
is intentionally ordinary; the focus is on building it the way a real service
gets built — proper auth, database migrations, tests against a real database in
CI, and a deployment defined entirely in code.

[![CI](https://github.com/PvPles/taskflow-api/actions/workflows/ci.yml/badge.svg)](https://github.com/PvPles/taskflow-api/actions)

## What's interesting here

A task manager is a task manager. The parts worth a look:

- Access tokens are short-lived JWTs (15 min). Refresh tokens are opaque random
  strings, stored only as SHA-256 hashes and rotated on every use. If an
  already-used refresh token shows up again, the whole token family is revoked,
  which is how you catch a stolen token being replayed.
- Task lists use keyset (cursor) pagination with a `(created_at, id)` tiebreaker
  and a matching index, so pages stay stable as rows are added or removed and the
  database seeks instead of counting offsets.
- Per-user rate limiting with a token bucket, returning `429` and `Retry-After`.
- One JSON log line per request with a request ID, which is also returned in the
  response header and every error body, so any failure traces back to one line.
- Separate liveness (`/health`) and readiness (`/health/ready`, checks the DB)
  endpoints — the distinction a load balancer actually needs.
- The whole AWS deployment is Terraform. No clicking around a console.

## Stack

| Layer | Choice |
| --- | --- |
| Language | Python 3.12 |
| Web | FastAPI (OpenAPI docs generated at `/docs`) |
| Data | SQLAlchemy 2.0 (sync), PostgreSQL 16, Alembic migrations |
| Auth | PyJWT (HS256), argon2 password hashing |
| Tests | pytest — SQLite locally, PostgreSQL in CI |
| Lint | ruff, plus a 70% coverage gate |
| Packaging | Docker, docker compose |
| Infra | Terraform (VPC, ALB, EC2, ACM, CloudWatch, IAM) |
| CI | GitHub Actions: lint, test, terraform validate, publish image to GHCR |

## Running it

```bash
docker compose up --build
```

That starts PostgreSQL and the API, waits for the database to be healthy, runs
migrations, and serves on <http://localhost:8000>. Interactive docs are at
<http://localhost:8000/docs>. Stop with `docker compose down` (`-v` also drops
the database volume).

## The API

Everything lives under `/api/v1` and is documented at `/docs`. Four groups:

- **auth** — register, login, refresh, logout, me
- **projects** — CRUD plus members (add/remove by email, owner only)
- **tasks** — CRUD, assignment, status transitions, paginated lists
- **comments** — add, list, and delete on a task

A quick run through the auth flow:

```bash
BASE=http://localhost:8000/api/v1

curl -s -X POST $BASE/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"ada@example.com","password":"correct-horse-battery","display_name":"Ada"}'

TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ada@example.com","password":"correct-horse-battery"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s -X POST $BASE/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Website relaunch"}'
```

Errors use one shape, and the `request_id` matches the `X-Request-ID` header so
you can find the exact log line:

```json
{ "error": { "code": "not_found", "message": "...", "request_id": "abc123" } }
```

Task status follows a small state machine. You can't jump a finished task
straight back to in-progress; it has to be reopened first, and the API returns
`409 invalid_status_transition` if you try.

```mermaid
stateDiagram-v2
    [*] --> todo
    todo --> in_progress
    todo --> done
    in_progress --> todo
    in_progress --> done
    done --> todo : reopen
```

## Tests

```bash
# Fast: in-memory SQLite, no services required
pip install -e ".[dev]"
pytest

# Same suite against real Postgres (this is what CI runs)
docker compose up -d db
TEST_DATABASE_URL=postgresql+psycopg://taskflow:taskflow@localhost:5432/taskflow_test pytest
```

43 tests, ~97% coverage. There's a full end-to-end test in
`tests/test_e2e_journey.py` that runs register → project → members → tasks →
transitions → comments → pagination → delete in one flow; the rest are focused
unit tests. Because the models use portable column types, the identical suite
passes on both SQLite and Postgres.

## Architecture

```mermaid
flowchart LR
    Client -- HTTPS --> ALB[Load Balancer]
    ALB -- HTTP --> EC2[EC2 instance]
    subgraph EC2 [EC2 with Docker]
        API[FastAPI]
        DB[(PostgreSQL)]
        API --> DB
    end
    API -- JSON logs --> CW[(CloudWatch)]
```

The API and Postgres run as Docker containers on a single EC2 instance behind an
Application Load Balancer. It's single-instance on purpose — the right size for
this project. Notes on what would change to scale it are in the decisions below.

### Data model

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
```

## Deploying

The Terraform in [terraform/](terraform/) brings up the full stack from an empty
AWS account. The walkthrough, cost breakdown, and reasoning (why no NAT gateway,
why Postgres in Docker instead of RDS) are in
[terraform/README.md](terraform/README.md).

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # set app_image at minimum
terraform init
terraform apply        # prints the live URL
terraform destroy      # tears everything down
```

It's built to be stood up when needed and torn down after, not left running.
On a new AWS account it costs roughly €1–2/month (t3.micro and the ALB are
free-tier for a year); at full price it's about €26/month, mostly the ALB.

## Some decisions worth explaining

- **Sync SQLAlchemy, not async.** The code and tests are simpler, and this
  service isn't I/O-bound enough to earn the complexity.
- **Refresh tokens stored hashed.** A database leak doesn't hand out usable
  tokens. JWTs are only ever used for the short-lived access token.
- **404, not 403, for non-members.** An outsider can't tell "exists but I'm
  blocked" from "doesn't exist," so IDs don't leak. 403 is kept for a member
  who lacks a specific right, like an owner-only action.
- **Membership instead of a separate teams table.** Same authorization outcome,
  less surface area. Teams could wrap projects later without a schema break.
- **In-process rate limiting.** Correct for one instance. Running several would
  mean moving the bucket state to something shared, behind the same interface.

## License

MIT — see [LICENSE](LICENSE).
