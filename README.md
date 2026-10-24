# Mumblebox

One blunt message in. Three different replies out. Nothing is sent.

You already know what you want to say. You are not sending it because that version would start a fight. Mumblebox asks a local Gemma model for three drafts of the same note:

- **Soft.** The one you can send without starting a fight.
- **Brief.** Two sentences. The request, then stop.
- **Plain.** No apology. The fact and the ask.

You pick one and send it yourself. The page never sends mail. The only model call is to Ollama on this machine.

## Desk

Ollama needs to be running, with `gemma2:2b` pulled.

```bash
cd mumblebox
python -m mumble desk
```

Open http://127.0.0.1:8765. The mark and the desk photograph are on the page. Write the version you will not send, then press **Draft three**.

## Tests

```bash
python -m unittest discover -s tests -t .
```

The tests do not call the model. They check that one note becomes three different replies, that a copied reply is rejected, that an invented number is rejected, and that undo puts the note back.

## Files

A nap still works from the command line. It takes the first file in `inbox/` and writes three files in `ready/`. The other notes stay where they are.

```bash
python -m mumble nap --root .
python -m mumble morning --root .
python -m mumble undo --root .
```

```text
mumble/decide.py   three tones, JSON parsing, number guard
mumble/box.py      one note to three files, morning, undo
mumble/desk.py     the local page
mumble/ollama.py   local generate call
web/               logo, desk photograph, page
```
