import json
import re
from datetime import date
from pathlib import Path

from mumble.decide import (
    build_draft_prompt,
    guard_text,
    note_asks_to_wait,
    parse_drafts,
)

LEDGER = "ledger.json"
TONE_LABELS = {
    "soft": "Soft",
    "brief": "Brief",
    "plain": "Plain",
}


def split_note(text):
    lines = text.strip().splitlines()
    if lines and lines[0].lower().startswith("to:"):
        to = lines[0].split(":", 1)[1].strip()
        body = "\n".join(lines[1:]).strip()
        return to, body
    return "", text.strip()


def slug(to):
    cleaned = re.sub(r"[^a-z0-9]+", "-", to.lower()).strip("-")
    return cleaned or "note"


def _count(directory):
    if not directory.exists():
        return 0
    return sum(1 for path in directory.glob("*.txt") if path.is_file())


def morning(root):
    root = Path(root)
    ready = _count(root / "ready")
    waiting = _count(root / "inbox") + _count(root / "asleep")
    if ready == 0 and waiting == 0:
        return "The box is empty.\nNothing to write, and nothing waiting."
    draft_word = "draft is" if ready == 1 else "drafts are"
    note_word = "note is" if waiting == 1 else "notes are"
    return (
        f"{ready} {draft_word} ready. {waiting} {note_word} still in the box.\n"
        "You don't have to write any of them. Pick one, send it yourself, or put them back."
    )


def _load_ledger(root):
    path = root / LEDGER
    if not path.exists():
        return {"runs": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_ledger(root, ledger):
    (root / LEDGER).write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def _relative(path, root):
    return path.relative_to(root).as_posix()


def draft_note(model, to, body, source):
    prompt = build_draft_prompt(to, body)
    error = "unreadable model output"
    for _ in range(2):
        try:
            parsed = parse_drafts(model.complete(prompt))
            if parsed["hold"]:
                if note_asks_to_wait(source):
                    return parsed
                raise ValueError("hold was set but the note does not ask to wait")
            for draft in parsed["drafts"]:
                guard_text(draft["text"], source)
            return parsed
        except (ValueError, json.JSONDecodeError) as exc:
            error = str(exc)
    raise ValueError(error)


def nap(root, model, today=None):
    root = Path(root)
    today = today or date.today().isoformat()
    inbox = root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in inbox.glob("*.txt") if path.is_file())
    if not files:
        return {"drafts": [], "ready": [], "asleep": [], "skipped": [], "left": []}
    path = files[0]
    left = [item.name for item in files[1:]]
    original = path.read_text(encoding="utf-8")
    to, body = split_note(original)
    try:
        parsed = draft_note(model, to, body, original)
    except ValueError as exc:
        ledger = _load_ledger(root)
        ledger["runs"].append(
            {
                "today": today,
                "items": [{"source": path.name, "action": "skipped", "reason": str(exc)}],
            }
        )
        _save_ledger(root, ledger)
        return {
            "drafts": [],
            "ready": [],
            "asleep": [],
            "skipped": [path.name],
            "left": left,
            "error": str(exc),
        }

    if parsed["hold"]:
        asleep_dir = root / "asleep"
        asleep_dir.mkdir(parents=True, exist_ok=True)
        dest = asleep_dir / path.name
        path.replace(dest)
        ledger = _load_ledger(root)
        ledger["runs"].append(
            {
                "today": today,
                "items": [
                    {
                        "source": path.name,
                        "action": "asleep",
                        "asleep": _relative(dest, root),
                    }
                ],
            }
        )
        _save_ledger(root, ledger)
        return {
            "drafts": [],
            "ready": [],
            "asleep": [path.name],
            "skipped": [],
            "left": left,
        }

    ready_dir = root / "ready"
    kept_dir = root / "kept"
    ready_dir.mkdir(parents=True, exist_ok=True)
    kept_dir.mkdir(parents=True, exist_ok=True)
    ready_names = []
    ready_paths = []
    base = f"{today}-{slug(to)}"
    for draft in parsed["drafts"]:
        ready_file = ready_dir / f"{base}-{draft['tone']}.txt"
        ready_file.write_text(
            f"To: {to}\nTone: {TONE_LABELS[draft['tone']]}\n\n{draft['text']}\n",
            encoding="utf-8",
        )
        ready_names.append(ready_file.name)
        ready_paths.append(_relative(ready_file, root))
    kept = kept_dir / path.name
    path.replace(kept)
    ledger = _load_ledger(root)
    ledger["runs"].append(
        {
            "today": today,
            "items": [
                {
                    "source": path.name,
                    "action": "ready",
                    "kept": _relative(kept, root),
                    "ready": ready_paths,
                }
            ],
        }
    )
    _save_ledger(root, ledger)
    return {
        "drafts": parsed["drafts"],
        "ready": ready_names,
        "asleep": [],
        "skipped": [],
        "left": left,
        "to": to,
    }


def undo(root):
    root = Path(root)
    ledger = _load_ledger(root)
    if not ledger["runs"]:
        return []
    run = ledger["runs"].pop()
    restored = []
    for item in run["items"]:
        action = item["action"]
        if action == "ready":
            kept = root / item["kept"]
            inbox_file = root / "inbox" / item["source"]
            inbox_file.parent.mkdir(parents=True, exist_ok=True)
            if kept.exists():
                if inbox_file.exists():
                    inbox_file.unlink()
                kept.replace(inbox_file)
            for ready_name in item.get("ready") or []:
                ready = root / ready_name
                if ready.exists():
                    ready.unlink()
            restored.append(item["source"])
        elif action == "asleep":
            asleep = root / item["asleep"]
            inbox_file = root / "inbox" / item["source"]
            inbox_file.parent.mkdir(parents=True, exist_ok=True)
            if asleep.exists():
                if inbox_file.exists():
                    inbox_file.unlink()
                asleep.replace(inbox_file)
            restored.append(item["source"])
    _save_ledger(root, ledger)
    return restored
