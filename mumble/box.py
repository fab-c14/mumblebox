import json
import re
from datetime import date
from pathlib import Path

from mumble.decide import (
    build_prompt,
    guard,
    parse_decision,
    prefer_written_reply,
    recover_false_hold,
)

LEDGER = "ledger.json"


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
    ready_word = "reply is" if ready == 1 else "replies are"
    note_word = "note is" if waiting == 1 else "notes are"
    return (
        f"{ready} {ready_word} ready. {waiting} {note_word} still in the box.\n"
        "You don't have to write any of them. Read, send, or put them back."
    )


def _load_ledger(root):
    path = root / LEDGER
    if not path.exists():
        return {"runs": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_ledger(root, ledger):
    (root / LEDGER).write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def _ready_path(ready_dir, today, to):
    base = f"{today}-{slug(to)}"
    candidate = ready_dir / f"{base}.txt"
    number = 2
    while candidate.exists():
        candidate = ready_dir / f"{base}-{number}.txt"
        number += 1
    return candidate


def _relative(path, root):
    return path.relative_to(root).as_posix()


def nap(root, model, limit=3, today=None):
    root = Path(root)
    today = today or date.today().isoformat()
    inbox = root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in inbox.glob("*.txt") if path.is_file())
    batch = files[:limit]
    left = [path.name for path in files[limit:]]
    ready_names = []
    asleep_names = []
    skipped = []
    items = []

    for path in batch:
        original = path.read_text(encoding="utf-8")
        to, body = split_note(original)
        prompt = build_prompt(to, body)
        decision = None
        error = "unreadable model output"
        for _ in range(2):
            try:
                decision = parse_decision(model.complete(prompt))
                guard(decision, original)
                decision = recover_false_hold(decision, original)
                decision = prefer_written_reply(decision, original)
                error = ""
                break
            except (ValueError, json.JSONDecodeError) as exc:
                decision = None
                error = str(exc)
        if decision is None:
            skipped.append(path.name)
            items.append({"source": path.name, "action": "skipped", "reason": error})
            continue
        if decision["hold"]:
            asleep_dir = root / "asleep"
            asleep_dir.mkdir(parents=True, exist_ok=True)
            dest = asleep_dir / path.name
            path.replace(dest)
            asleep_names.append(path.name)
            items.append(
                {
                    "source": path.name,
                    "action": "asleep",
                    "asleep": _relative(dest, root),
                    "why": decision["why"],
                }
            )
            continue

        ready_dir = root / "ready"
        kept_dir = root / "kept"
        ready_dir.mkdir(parents=True, exist_ok=True)
        kept_dir.mkdir(parents=True, exist_ok=True)
        ready_file = _ready_path(ready_dir, today, to)
        why = decision["why"] or "rewritten"
        ready_file.write_text(
            f"To: {to}\n\n{decision['sendable']}\n\n---\n{why}\n",
            encoding="utf-8",
        )
        kept = kept_dir / path.name
        path.replace(kept)
        ready_names.append(ready_file.name)
        items.append(
            {
                "source": path.name,
                "action": "ready",
                "kept": _relative(kept, root),
                "ready": _relative(ready_file, root),
                "why": decision["why"],
            }
        )

    if items:
        ledger = _load_ledger(root)
        ledger["runs"].append({"today": today, "items": items})
        _save_ledger(root, ledger)

    return {
        "ready": ready_names,
        "asleep": asleep_names,
        "skipped": skipped,
        "left": left,
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
            ready = root / item["ready"]
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
