import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mumble.box import TONE_LABELS, draft_note
from mumble.ollama import OllamaModel

WEB = Path(__file__).resolve().parents[1] / "web"
TONE_BLURB = {
    "soft": "The one you can send without starting a fight.",
    "brief": "Two sentences. The request, then stop.",
    "plain": "No apology. The fact and the ask.",
}


class DeskHandler(BaseHTTPRequestHandler):
    model = None

    def log_message(self, fmt, *args):
        return

    def _send(self, code, body, content_type):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        name = self.path.split("?", 1)[0].lstrip("/") or "index.html"
        if name not in {"index.html", "logo.jpg", "desk.jpg"}:
            self._send(404, "Not found", "text/plain; charset=utf-8")
            return
        path = WEB / name
        kind = "text/html; charset=utf-8" if name.endswith(".html") else "image/jpeg"
        self._send(200, path.read_bytes(), kind)

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/draft":
            self._send(404, "Not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            self._send(400, json.dumps({"error": "That was not a note."}), "application/json")
            return
        to = str(payload.get("to") or "").strip()
        note = str(payload.get("note") or "").strip()
        if not note:
            self._send(400, json.dumps({"error": "Write the version you will not send."}), "application/json")
            return
        source = f"To: {to}\n{note}" if to else note
        try:
            parsed = draft_note(self.model, to, note, source)
        except Exception as exc:
            message = str(exc) or "The model did not answer."
            if "timed out" in message.lower() or "connection" in message.lower() or "refused" in message.lower():
                message = "Ollama is not running on this machine. Open it, with gemma2:2b pulled, and try again."
            self._send(502, json.dumps({"error": message}), "application/json")
            return
        if parsed["hold"]:
            self._send(200, json.dumps({"held": True, "drafts": []}), "application/json")
            return
        drafts = [
            {
                "tone": draft["tone"],
                "label": TONE_LABELS[draft["tone"]],
                "blurb": TONE_BLURB[draft["tone"]],
                "text": draft["text"],
            }
            for draft in parsed["drafts"]
        ]
        self._send(200, json.dumps({"held": False, "to": to, "drafts": drafts}), "application/json")


def serve(host="127.0.0.1", port=8765, model="gemma2:2b"):
    DeskHandler.model = OllamaModel(model=model)
    server = ThreadingHTTPServer((host, port), DeskHandler)
    print(f"Mumblebox desk  http://{host}:{port}")
    print("Nothing on this page is sent. Close the window with Ctrl+C.")
    server.serve_forever()
