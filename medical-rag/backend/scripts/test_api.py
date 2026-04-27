# -*- coding: utf-8 -*-
"""
Test nhanh các API endpoints bằng httpx.

Chạy (server phải đang chạy ở port 8000):
  cd medical-rag/backend
  python scripts/test_api.py
"""
import asyncio
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE_URL = "http://localhost:8000"
PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
INFO = "\033[94m[INFO]\033[0m"

# Tài khoản test — thay đổi nếu cần
TEST_EMAIL = f"test_{int(time.time())}@example.com"
TEST_PASSWORD = "TestPass123!"
TEST_NAME = "Test User"


def ok(msg: str) -> None:
    print(f"  {PASS} {msg}")


def fail(msg: str, detail: str = "") -> None:
    print(f"  {FAIL} {msg}" + (f" — {detail}" if detail else ""))


async def run_tests() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:

        # ----------------------------------------------------------------
        print("\n\033[93m{'='*55}\033[0m")
        print("\033[93m  HEALTH CHECK\033[0m")
        print("\033[93m{'='*55}\033[0m")
        # ----------------------------------------------------------------
        r = await client.get("/api/health")
        data = r.json()
        if data.get("status") in ("healthy", "degraded"):
            ok(f"Health: {data['status']} — checks: {data['checks']}")
        else:
            fail("Health check", str(data))

        # ----------------------------------------------------------------
        print("\n\033[93m{'='*55}\033[0m")
        print("\033[93m  AUTH\033[0m")
        print("\033[93m{'='*55}\033[0m")
        # ----------------------------------------------------------------

        # Register
        r = await client.post("/api/auth/register", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "full_name": TEST_NAME,
        })
        if r.status_code == 201:
            ok(f"Register OK — {TEST_EMAIL}")
        else:
            fail("Register", r.text)
            return

        # Login
        r = await client.post("/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        })
        if r.status_code == 200:
            token_data = r.json()
            access_token = token_data["access_token"]
            ok("Login OK — token nhận được")
        else:
            fail("Login", r.text)
            return

        headers = {"Authorization": f"Bearer {access_token}"}

        # GET /me
        r = await client.get("/api/auth/me", headers=headers)
        if r.status_code == 200:
            ok(f"GET /me OK — {r.json()['email']}")
        else:
            fail("GET /me", r.text)

        # ----------------------------------------------------------------
        print("\n\033[93m{'='*55}\033[0m")
        print("\033[93m  CHAT\033[0m")
        print("\033[93m{'='*55}\033[0m")
        # ----------------------------------------------------------------

        # GET /sessions/new
        r = await client.get("/api/chat/sessions/new", headers=headers)
        if r.status_code == 200:
            session_id = r.json()["session_id"]
            ok(f"New session OK — {session_id}")
        else:
            fail("GET /sessions/new", r.text)
            session_id = None

        # POST /stream (SSE)
        print(f"  {INFO} Gửi tin nhắn SSE (có thể mất 10-30 giây)...")
        tokens: list[str] = []
        done_event: dict = {}

        async with client.stream(
            "POST",
            "/api/chat/stream",
            headers={**headers, "Accept": "text/event-stream"},
            json={
                "session_id": session_id,
                "message": "Tôi bị đau đầu và sốt nhẹ, phải làm gì?",
            },
        ) as resp:
            if resp.status_code != 200:
                fail("POST /stream", await resp.aread())
            else:
                import json
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = json.loads(line[5:].strip())
                    evt_type = payload.get("type")
                    if evt_type == "start":
                        ok(f"SSE start — session={payload.get('session_id')}")
                    elif evt_type == "token":
                        tokens.append(payload.get("content", ""))
                    elif evt_type == "done":
                        done_event = payload
                        ok(f"SSE done — confidence={payload.get('confidence')}, "
                           f"urgency={payload.get('urgency')}, "
                           f"sources={len(payload.get('sources', []))}")
                    elif evt_type == "error":
                        fail("SSE error event", payload.get("content", ""))

                full_response = "".join(tokens)
                if full_response:
                    preview = full_response[:100].replace("\n", " ")
                    ok(f"Response ({len(full_response)} chars): {preview}...")

        # ----------------------------------------------------------------
        print("\n\033[93m{'='*55}\033[0m")
        print("\033[93m  HISTORY\033[0m")
        print("\033[93m{'='*55}\033[0m")
        # ----------------------------------------------------------------

        # GET /history/sessions
        r = await client.get("/api/history/sessions", headers=headers)
        if r.status_code == 200:
            data = r.json()
            ok(f"List sessions OK — total={data['total']}, items={len(data['items'])}")
        else:
            fail("GET /history/sessions", r.text)

        # GET /history/sessions/{id}
        if session_id:
            real_session_id = done_event.get("session_id", session_id)
            r = await client.get(f"/api/history/sessions/{real_session_id}", headers=headers)
            if r.status_code == 200:
                detail = r.json()
                ok(f"Session detail OK — {len(detail['messages'])} messages")
            else:
                fail(f"GET /history/sessions/{real_session_id}", r.text)

        # GET /history/search
        r = await client.get("/api/history/search?q=đau đầu", headers=headers)
        if r.status_code == 200:
            ok(f"Search OK — {len(r.json())} results")
        else:
            fail("GET /history/search", r.text)

        # ----------------------------------------------------------------
        print("\n\033[93m{'='*55}\033[0m")
        print("\033[93m  ANALYSIS\033[0m")
        print("\033[93m{'='*55}\033[0m")
        # ----------------------------------------------------------------

        # GET /analysis/summary
        r = await client.get("/api/analysis/summary?period_days=30", headers=headers)
        if r.status_code == 200:
            ok(f"Analysis summary OK — severity={r.json().get('severity')}")
        elif r.status_code == 404:
            ok("Analysis summary — 404 (chưa có treatment record, bình thường)")
        else:
            fail("GET /analysis/summary", r.text)

        # GET /analysis/timeline
        r = await client.get("/api/analysis/timeline", headers=headers)
        if r.status_code == 200:
            ok(f"Timeline OK — {len(r.json())} data points")
        else:
            fail("GET /analysis/timeline", r.text)

        # GET /analysis/statistics
        r = await client.get("/api/analysis/statistics", headers=headers)
        if r.status_code == 200:
            stats = r.json()
            ok(f"Statistics OK — sessions={stats['total_sessions']}, "
               f"messages={stats['total_messages']}")
        else:
            fail("GET /analysis/statistics", r.text)

        print()


if __name__ == "__main__":
    asyncio.run(run_tests())
