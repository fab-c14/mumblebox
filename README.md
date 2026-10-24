# Mumblebox

You already know what the message should say. You are not sending it because the version in your head sounds angry. Mumblebox takes that version, asks a local Gemma model for a calmer one, and stops after three notes.

It does not send anything. The reply lands in `ready/`. You read it, send it yourself, or put it back.

The notes stay on this machine. The only model call is to `127.0.0.1`.

## Run

Ollama needs to be running, with `gemma2:2b` pulled. Nothing else is installed. The program uses the Python standard library.

```bash
python -m unittest discover -s tests -t .
python -m mumble nap --root .
python -m mumble morning --root .
python -m mumble undo --root .
```

Put one note per file in `inbox/`. The first line is `To: Name`. The rest is the version you would not send.

A nap rewrites at most three files. The rest stay in the inbox for the next nap. `morning` prints two lines: how many replies are ready, and how many notes are still in the box.

## What a nap is allowed to keep

Gemma returns JSON: `sendable`, `why`, and `hold`.

- A reply may not contain a number of two or more digits unless that number is in the note. `45` invented by the model is rejected. The note stays in the inbox.
- `hold` is honored only when the note itself says not to send it yet. Otherwise a false hold is ignored. On the first live run, Gemma marked every note as hold and parked the words in `why`.
- If `sendable` is only a copy of the note, and `why` is a different sentence, the program keeps `why`. Gemma 2 2B did this on the dishes note and the lab note.
- A bad answer is tried once more. If both fail, the file is not moved.

## Sample nap

The four notes in `samples/inbox/` are made up. On 24 October 2026, with `gemma2:2b` already loaded, `python -m mumble nap` finished in 5.1 seconds and left the Saturday party note for later.

| Note | What you would not send | What landed in `ready/` |
| --- | --- | --- |
| Sam | The dishes have been in the sink since Monday, and you are tired of looking at them. | I'd appreciate it if you could wash the dishes tonight. |
| Professor Shah | The lab note is late because you forgot until this morning. You will turn it in by the end of today. | I apologize for the delay in submitting the lab note. |
| Priya | You can't do Friday afternoon, you already have something, and they should stop putting it on your calendar. | I can't make the Friday afternoon meeting. Please stop putting it on my calendar. |
| Alex | You don't want to go to the party. | Still in the inbox. The pace is three. |

The lab reply dropped "by the end of today". I would not send that one without putting the deadline back. The guard catches invented numbers. It does not catch a dropped promise.

The recorded files from that run are in `recorded/`.

## Layout

```text
mumble/decide.py   prompt, JSON parsing, number guard, hold and echo fixes
mumble/box.py      nap, morning, undo
mumble/ollama.py   local generate call
```
