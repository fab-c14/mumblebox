import json
import urllib.request
from urllib.parse import urlparse


def is_local_host(host):
    return urlparse(host).hostname in {"127.0.0.1", "localhost"}


class OllamaModel:
    def __init__(self, model="gemma2:2b", host="http://127.0.0.1:11434"):
        if not is_local_host(host):
            raise ValueError("mumblebox only talks to a model on this machine")
        self.model = model
        self.host = host.rstrip("/")

    def complete(self, prompt):
        body = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.2, "num_predict": 400, "num_ctx": 2048},
            }
        ).encode()
        request = urllib.request.Request(
            self.host + "/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode())
        return payload.get("response", "")
