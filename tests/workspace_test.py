"""HTTP-level acceptance checks for anonymous browser workspaces."""

from __future__ import annotations

import http.client
import importlib.util
import json
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_app():
    spec = importlib.util.spec_from_file_location("field_notes_workspace", ROOT / "app.py")
    app = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(app)
    return app


def call(port: int, method: str, path: str, body: dict | None = None, cookie: str = "") -> tuple[int, dict, str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    response = connection.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    set_cookie = response.getheader("Set-Cookie") or ""
    connection.close()
    return response.status, payload, set_cookie


def main() -> None:
    app = load_app()
    with tempfile.TemporaryDirectory(prefix="field-notes-workspace-") as temporary:
        app.DATA_ROOT = Path(temporary) / "local_data"
        app.WORKSPACES_ROOT = app.DATA_ROOT / "workspaces"
        app.ensure_data_directories()
        extracted = app.profile_from_text("Name Candidate A\ncandidate@example.com\nAddress: Lagos, Nigeria", "sample.txt", "test-workspace-token-012345678901234567890123456")
        assert extracted["email"] == "candidate@example.com"
        assert extracted["location"] == "Lagos, Nigeria"
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.FieldNotesHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            status, profile, cookie = call(port, "GET", "/api/profile")
            assert status == 200 and profile["email"] == "" and "HttpOnly" in cookie
            cookie = cookie.split(";", 1)[0]

            status, saved, _ = call(port, "POST", "/api/profile", {"name": "Candidate A", "email": "candidate@example.com"}, cookie=cookie)
            assert status == 200 and saved["profile"]["email"] == "candidate@example.com"
            status, profile, _ = call(port, "GET", "/api/profile", cookie=cookie)
            assert status == 200 and profile["name"] == "Candidate A"

            status, second_profile, second_cookie = call(port, "GET", "/api/profile")
            assert status == 200 and second_profile["name"] == "" and second_profile["email"] == ""
            assert cookie != second_cookie.split(";", 1)[0]
        finally:
            server.shutdown()
            server.server_close()
    print("Field Notes workspace test passed: each browser cookie receives an isolated workspace.")


if __name__ == "__main__":
    main()
