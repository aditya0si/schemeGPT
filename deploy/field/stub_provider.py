#!/usr/bin/env python3
"""Stand-in LLM provider for incident drills and gateway testing.

Stands up an OpenAI-compatible ``/chat/completions`` endpoint on localhost that
can be told to misbehave, so a *provider outage* can be rehearsed on purpose
instead of waited for. Used by ``deploy/field/drill.py``.

    python3 stub_provider.py --port 9099 --state ok
    curl -s -X POST localhost:9099/control -d '{"mode": "rate_limit"}'
    curl -s localhost:9099/stats

Modes
    ok           normal answer (streaming and non-streaming)
    rate_limit   429 with a Retry-After header            (quota exhausted)
    server_error 500 with a provider-style error body      (provider incident)
    timeout      hold the connection open, then reply late (hung provider)
    unreachable  refuse the connection outright            (network/egress block)

The point is not to emulate Groq faithfully — it is to produce the failure
*signatures* the application has to survive, deterministically, so the
recovery path is tested rather than trusted. ``/stats`` reports how many
requests arrived in each mode, which is what turns "it degraded" into "it
degraded after N failed calls".
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ANSWER_TEXT = (
    "Stub provider answer: PM-KISAN provides income support to eligible "
    "landholding farmer families."
)

MODE_INSTRUCTIONS = {
    "ok": "answer normally",
    "rate_limit": "429 + Retry-After (free-tier quota exhausted)",
    "server_error": "500 (provider-side incident)",
    "timeout": "sleep before answering (hung upstream)",
    "unreachable": "refuse the connection (egress blocked / host down)",
}


class State:
    def __init__(self, mode: str, timeout_seconds: float) -> None:
        self.lock = threading.Lock()
        self.mode = mode
        self.timeout_seconds = timeout_seconds
        self.counts: dict[str, int] = {}
        self.started_at = time.time()
        self.events: list[dict] = []

    def set_mode(self, mode: str) -> None:
        if mode not in MODE_INSTRUCTIONS:
            raise ValueError(f"unknown mode: {mode}")
        with self.lock:
            self.mode = mode
            self.events.append({"at": time.time(), "event": "mode_set", "mode": mode})

    def current_mode(self) -> str:
        with self.lock:
            return self.mode

    def record(self, mode: str, path: str) -> None:
        with self.lock:
            self.counts[mode] = self.counts.get(mode, 0) + 1
            self.events.append(
                {"at": time.time(), "event": "request", "mode": mode, "path": path}
            )

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "mode": self.mode,
                "counts": dict(self.counts),
                "uptime_s": round(time.time() - self.started_at, 2),
                "timeout_seconds": self.timeout_seconds,
                "modes": MODE_INSTRUCTIONS,
            }


class Handler(BaseHTTPRequestHandler):
    state: State  # set on the server class below
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep the drill output readable
        return

    def _json(self, status: int, payload: dict, extra_headers: dict | None = None) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/stats"):
            self._json(200, self.state.snapshot())
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        if self.path.startswith("/control"):
            try:
                payload = json.loads(raw or b"{}")
                self.state.set_mode(str(payload.get("mode", "")))
            except Exception as exc:
                self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
                return
            self._json(200, self.state.snapshot())
            return

        mode = self.state.current_mode()
        self.state.record(mode, self.path)

        if mode == "rate_limit":
            self._json(
                429,
                {"error": {"message": "rate limit exceeded", "type": "rate_limit_error"}},
                {"Retry-After": "20"},
            )
            return
        if mode == "server_error":
            self._json(
                500,
                {"error": {"message": "internal provider error", "type": "server_error"}},
            )
            return
        if mode == "timeout":
            time.sleep(self.state.timeout_seconds)
        if mode == "unreachable":
            # No response at all: close the socket the way a blocked egress
            # policy or a dead host does.
            try:
                self.connection.close()
            except Exception:
                pass
            return

        try:
            request = json.loads(raw or b"{}")
        except Exception:
            request = {}
        streaming = bool(request.get("stream"))
        model = request.get("model", "stub-model")

        if streaming:
            self._stream(model)
        else:
            self._json(
                200,
                {
                    "id": "chatcmpl-stub",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": ANSWER_TEXT},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 42,
                        "completion_tokens": 21,
                        "total_tokens": 63,
                    },
                },
            )

    def _stream(self, model: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for word in ANSWER_TEXT.split(" "):
            chunk = {
                "id": "chatcmpl-stub",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {"content": word + " "}}],
            }
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def serve(port: int, mode: str, timeout_seconds: float) -> ThreadingHTTPServer:
    state = State(mode=mode, timeout_seconds=timeout_seconds)

    class BoundHandler(Handler):
        pass

    BoundHandler.state = state
    server = ThreadingHTTPServer(("0.0.0.0", port), BoundHandler)
    server.daemon_threads = True
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=9099)
    parser.add_argument("--state", default="ok", choices=sorted(MODE_INSTRUCTIONS))
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="How long 'timeout' mode holds a request before answering.",
    )
    args = parser.parse_args()
    server = serve(args.port, args.state, args.timeout_seconds)
    print(
        f"stub provider listening on http://0.0.0.0:{args.port} "
        f"(mode={args.state}); POST /control {{\"mode\": \"...\"}}, GET /stats",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
