"""Locust load test for the SchemeGPT SSE streaming endpoint.

Run against a local stack (demo mode is fine — it exercises the full SSE
plumbing, rate limiter, and FastAPI layer without spending Groq quota):

    docker compose up -d db
    GROQ_API_KEY= uvicorn app.main:app --port 8000        # demo-mode API
    locust -f loadtest/locustfile.py --host http://localhost:8000 \
           --users 25 --spawn-rate 5 --run-time 60s --headless

The dashboard reports RPS and latency percentiles for the streaming endpoint.
Live-mode numbers are dominated by Groq inference latency and its shared
free-tier limits; this test measures the serving layer.
"""

from locust import HttpUser, between, task


class SchemeUser(HttpUser):
    wait_time = between(0.5, 2.0)

    @task(3)
    def stream_query(self):
        with self.client.post(
            "/query/stream",
            json={"question": "What health insurance cover does PM-JAY provide?"},
            catch_response=True,
            timeout=30,
        ) as response:
            if response.status_code != 200:
                response.failure(f"status {response.status_code}")
                return
            events = 0
            got_done = False
            for line in response.iter_lines():
                if isinstance(line, bytes):
                    line = line.decode("utf-8", "replace")
                if line.startswith("event: "):
                    events += 1
                    if line == "event: done":
                        got_done = True
            if got_done:
                response.success()
            else:
                response.failure(f"stream ended without done event ({events} events)")

    @task(1)
    def health(self):
        self.client.get("/health")
