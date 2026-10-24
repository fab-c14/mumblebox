import json
import re

SENDABLE_LIMIT = 600
WAIT_PHRASES = (
    "not send",
    "don't send",
    "do not send",
    "shouldn't send",
    "should not send",
)


def note_asks_to_wait(text):
    lowered = text.lower()
    return any(phrase in lowered for phrase in WAIT_PHRASES)


def _flat(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


def echoes_source(candidate, source):
    left = _flat(candidate)
    right = _flat(source)
    return bool(left) and left in right


def prefer_written_reply(decision, source):
    """Gemma 2 2B often copies the note into sendable and hides the real reply in why."""
    if decision["hold"]:
        return decision
    why = decision["why"].strip()
    if len(why) < 20 or echoes_source(why, source):
        return decision
    if not echoes_source(decision["sendable"], source):
        return decision
    swapped = {
        "sendable": why,
        "why": "the model wrote the reply in why; kept that",
        "hold": False,
    }
    guard(swapped, source)
    return swapped


def recover_false_hold(decision, source):
    """Small models park the real reply in `why` and set hold. Honor hold only when the note asks to wait."""
    if not decision["hold"] or note_asks_to_wait(source):
        return decision
    sendable = decision["sendable"] or decision["why"]
    if not sendable.strip():
        raise ValueError("hold was set but the note does not ask to wait")
    recovered = {
        "sendable": sendable.strip(),
        "why": "kept the reply; the note does not ask to wait",
        "hold": False,
    }
    guard(recovered, source)
    return recovered


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def parse_decision(text):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no json object in model output")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("model output was not an object")
    hold = _as_bool(data.get("hold", False))
    sendable = str(data.get("sendable", "")).strip()
    why = str(data.get("why", "")).strip()
    if not hold and not sendable:
        raise ValueError("sendable reply is empty")
    if len(sendable) > SENDABLE_LIMIT:
        raise ValueError("sendable reply is too long")
    return {"sendable": sendable, "why": why, "hold": hold}


def guard(decision, source):
    if decision["hold"]:
        return
    source_numbers = set(re.findall(r"\d{2,}", source))
    for number in re.findall(r"\d{2,}", decision["sendable"]):
        if number not in source_numbers:
            raise ValueError(f"reply invents the number {number}")


TONES = ("soft", "brief", "plain")


def guard_text(text, source):
    source_numbers = set(re.findall(r"\d{2,}", source))
    for number in re.findall(r"\d{2,}", text):
        if number not in source_numbers:
            raise ValueError(f"reply invents the number {number}")


def parse_drafts(text):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no json object in model output")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("model output was not an object")
    found = {}
    for item in data.get("drafts") or []:
        if not isinstance(item, dict):
            continue
        tone = str(item.get("tone", "")).strip().lower()
        piece = str(item.get("text") or item.get("sendable") or "").strip()
        if tone in TONES and piece:
            found[tone] = piece
    for tone in TONES:
        if tone not in found and data.get(tone):
            found[tone] = str(data[tone]).strip()
    hold = _as_bool(data.get("hold", False))
    if hold and not any(found.values()):
        return {"hold": True, "drafts": []}
    missing = [tone for tone in TONES if not found.get(tone)]
    if missing:
        raise ValueError("missing " + ", ".join(missing))
    drafts = []
    for tone in TONES:
        piece = found[tone]
        if len(piece) > SENDABLE_LIMIT:
            raise ValueError(f"{tone} is too long")
        drafts.append({"tone": tone, "text": piece})
    if len({_flat(item["text"]) for item in drafts}) < 3:
        raise ValueError("the three replies are not different")
    return {"hold": False, "drafts": drafts}


def build_draft_prompt(to, body):
    return (
        "Write three different replies the person could send. "
        "They must not share the same sentences.\n"
        "\n"
        "Tones:\n"
        "- soft: warm, no insult, the version that keeps the peace. Three or four sentences.\n"
        "- brief: two sentences only. The request, then stop.\n"
        "- plain: no apology and no softening. The fact and the ask. Two or three sentences.\n"
        "\n"
        "Rules:\n"
        "- Keep the facts that are in the note. Do not add events, dates, amounts, "
        "promises, or names that are not there.\n"
        "- Do not copy the note word for word.\n"
        "- Set hold to true only when the note itself says not to send it yet. "
        "Otherwise hold is false and all three drafts are required.\n"
        "- Reply as JSON only: "
        '{"hold":false,"drafts":[{"tone":"soft","text":"..."},'
        '{"tone":"brief","text":"..."},{"tone":"plain","text":"..."}]}\n'
        "\n"
        f"To: {to}\n"
        "Note:\n"
        f"{body}\n"
    )


def build_prompt(to, body):
    return (
        "Rewrite this private note into a short message the person can send.\n"
        "\n"
        "Rules:\n"
        "- Keep the facts that are in the note. Do not add events, dates, amounts, "
        "promises, or names that are not there.\n"
        "- Take out insults. Keep the request and the facts.\n"
        "- Sound calm. The reader should not be able to tell the writer was annoyed.\n"
        "- Two to five sentences.\n"
        "- Set hold to true only when the note itself says not to send it yet. "
        "Otherwise hold must be false and sendable must be the message.\n"
        "- Reply as JSON only, with keys sendable, why, and hold. "
        "Put the message in sendable, not in why.\n"
        "\n"
        f"To: {to}\n"
        "Note:\n"
        f"{body}\n"
    )
