"""Post-deploy smoke test - runs the critical user journey against a live deployment.

Usage:
    python scripts/smoke.py http://<alb-dns-or-domain>

Exits non-zero on the first failure, so it can gate a deploy pipeline.
"""

import sys
import time

import httpx


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        sys.exit(1)


def main(base_url: str) -> None:
    base = base_url.rstrip("/")
    api = f"{base}/api/v1"
    email = f"smoke-{int(time.time())}@example.com"
    password = "smoke-test-pw-123"

    with httpx.Client(timeout=10, follow_redirects=True) as http:
        r = http.get(f"{base}/health")
        check("liveness", r.status_code == 200)

        r = http.get(f"{base}/health/ready")
        check("readiness (database reachable)", r.status_code == 200)

        r = http.post(
            f"{api}/auth/register",
            json={"email": email, "password": password, "display_name": "Smoke"},
        )
        check("register", r.status_code == 201, r.text[:100])
        check("request id header present", bool(r.headers.get("x-request-id")))

        r = http.post(f"{api}/auth/login", json={"email": email, "password": password})
        check("login", r.status_code == 200)
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = http.post(f"{api}/projects", json={"name": "Smoke"}, headers=headers)
        check("create project", r.status_code == 201)
        project_id = r.json()["id"]

        r = http.post(
            f"{api}/projects/{project_id}/tasks", json={"title": "smoke task"}, headers=headers
        )
        check("create task", r.status_code == 201)
        task_id = r.json()["id"]

        r = http.patch(f"{api}/tasks/{task_id}", json={"status": "done"}, headers=headers)
        check("transition todo -> done", r.status_code == 200)

        r = http.patch(f"{api}/tasks/{task_id}", json={"status": "in_progress"}, headers=headers)
        check(
            "done -> in_progress correctly rejected",
            r.status_code == 409 and r.json()["error"]["code"] == "invalid_status_transition",
        )

        r = http.delete(f"{api}/projects/{project_id}", headers=headers)
        check("cleanup (delete project)", r.status_code == 204)

    print("\nAll smoke checks passed.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1])
