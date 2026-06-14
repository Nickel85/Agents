"""Validate local LLM cold-start setup and timeout behavior."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MONGOOSE_CLI = REPO_ROOT / "mongoose" / "mongoose.py"
TEST_LOCAL_APP_DATA = REPO_ROOT / ".test-localappdata-mongoose-llm-cold-start"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FixtureState:
    tags_calls = 0
    chat_calls = 0


class LocalLlmHandler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/api/tags":
            FixtureState.tags_calls += 1
            self._write_json(
                200,
                {
                    "models": [
                        {
                            "name": "fixture-model:latest",
                            "model": "fixture-model:latest",
                        }
                    ]
                },
            )
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/api/chat":
            FixtureState.chat_calls += 1
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length:
                self.rfile.read(length)
            self._write_json(
                200,
                {
                    "message": {
                        "role": "assistant",
                        "content": "ready",
                    }
                },
            )
            return
        self._write_json(404, {"error": "not found"})


def run_mongoose(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "LOCALAPPDATA": str(TEST_LOCAL_APP_DATA)}
    return subprocess.run(
        [sys.executable, str(MONGOOSE_CLI), *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


if TEST_LOCAL_APP_DATA.exists():
    shutil.rmtree(TEST_LOCAL_APP_DATA)

spec = importlib.util.spec_from_file_location("mongoose_cli", MONGOOSE_CLI)
assert_true(spec is not None and spec.loader is not None, "Could not load mongoose module spec.")
mongoose_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mongoose_cli)

local_profile = {"provider": "local-http", "model": "fixture-model", "endpoint": "http://127.0.0.1/api/tags"}
remote_profile = {"provider": "openai", "model": "fixture-model", "endpoint": ""}
assert_true(
    mongoose_cli.effective_llm_invoke_timeout(local_profile, None)
    == mongoose_cli.DEFAULT_LOCAL_LLM_INVOKE_TIMEOUT_SECONDS,
    "Local LLM default invoke timeout was not cold-start tolerant.",
)
assert_true(
    mongoose_cli.effective_llm_invoke_timeout(remote_profile, None)
    == mongoose_cli.DEFAULT_REMOTE_LLM_INVOKE_TIMEOUT_SECONDS,
    "Remote LLM default invoke timeout changed unexpectedly.",
)
assert_true(
    mongoose_cli.effective_llm_invoke_timeout(local_profile, 3.0) == 3.0,
    "Explicit local LLM timeout override was not respected.",
)

server = ThreadingHTTPServer(("127.0.0.1", 0), LocalLlmHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    endpoint = f"http://127.0.0.1:{server.server_port}/api/tags"
    setup = run_mongoose(
        "llm",
        "setup",
        "--provider",
        "ollama",
        "--endpoint",
        endpoint,
        "--model",
        "fixture-model:latest",
        "--yes",
    )
    assert_true(setup.returncode == 0, f"Local Ollama setup failed: {setup.stdout}{setup.stderr}")
    assert_true("Warmup" in setup.stdout, "Local Ollama setup did not run warmup.")
    assert_true("LLM provider invocation verified" in setup.stdout, "Local Ollama warmup did not verify invocation.")
    assert_true(FixtureState.tags_calls >= 1, "Local Ollama setup did not inspect installed models.")
    assert_true(FixtureState.chat_calls >= 1, "Local Ollama setup did not warm the model through /api/chat.")
finally:
    server.shutdown()
    server.server_close()
    if TEST_LOCAL_APP_DATA.exists():
        shutil.rmtree(TEST_LOCAL_APP_DATA)

print("Mongoose LLM cold-start validation passed.")
