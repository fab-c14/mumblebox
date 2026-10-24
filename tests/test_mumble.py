import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mumble.box import morning, nap, undo
from mumble.decide import build_prompt, guard, parse_decision
from mumble.ollama import OllamaModel, is_local_host


class FakeModel:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        if not self.replies:
            raise AssertionError("model called more times than replies provided")
        return self.replies.pop(0)


def note(to, body):
    return f"To: {to}\n{body}\n"


def reply(sendable, why="asks plainly", hold=False):
    return json.dumps({"sendable": sendable, "why": why, "hold": hold})


class ParseAndGuardTests(unittest.TestCase):
    def test_parses_raw_json(self):
        decision = parse_decision(reply("Please wash the dishes tonight."))
        self.assertEqual(decision["sendable"], "Please wash the dishes tonight.")
        self.assertFalse(decision["hold"])

    def test_parses_json_wrapped_in_prose(self):
        raw = "Here you go:\n```json\n" + reply("I will turn the lab note in today.") + "\n```"
        decision = parse_decision(raw)
        self.assertIn("lab note", decision["sendable"])

    def test_rejects_a_reply_that_invents_a_number(self):
        decision = parse_decision(reply("I can meet for 45 minutes on Friday."))
        with self.assertRaises(ValueError) as caught:
            guard(decision, "I can't do the Friday meeting.")
        self.assertIn("45", str(caught.exception))

    def test_allows_a_number_copied_from_the_note(self):
        decision = parse_decision(reply("The invoice was 45 dollars. Please resend it."))
        guard(decision, "The invoice was 45 dollars and I lost it.")

    def test_hold_does_not_need_a_sendable_reply(self):
        decision = parse_decision(reply("", why="still too angry", hold=True))
        guard(decision, "I am furious and I should not send this yet.")

    def test_prompt_carries_the_note_and_forbids_new_facts(self):
        prompt = build_prompt("Sam", "The dishes have been in the sink since Monday.")
        self.assertIn("Sam", prompt)
        self.assertIn("since Monday", prompt)
        self.assertIn("Do not add", prompt)


class NapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "inbox").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write_inbox(self, name, to, body):
        (self.root / "inbox" / name).write_text(note(to, body), encoding="utf-8")

    def test_nap_rewrites_only_three_notes(self):
        self.write_inbox("dishes.txt", "Sam", "The dishes have been in the sink since Monday.")
        self.write_inbox("meeting.txt", "Priya", "I can't do the Friday meeting.")
        self.write_inbox("lab.txt", "Professor Shah", "The lab note is late. I will turn it in today.")
        self.write_inbox("party.txt", "Alex", "I don't want to go to the party.")
        model = FakeModel([
            reply("The dishes have been in the sink since Monday. Could you wash them?"),
            reply("I can't do the Friday meeting. Could we pick another time?"),
            reply("The lab note is late. I will turn it in today."),
        ])

        result = nap(self.root, model, limit=3, today="2026-10-24")

        self.assertEqual(len(result["ready"]), 3)
        self.assertEqual(result["left"], ["party.txt"])
        self.assertEqual(len(model.prompts), 3)
        self.assertTrue((self.root / "inbox" / "party.txt").exists())
        self.assertFalse((self.root / "inbox" / "dishes.txt").exists())
        self.assertTrue((self.root / "kept" / "dishes.txt").exists())
        ready = (self.root / "ready" / "2026-10-24-sam.txt").read_text(encoding="utf-8")
        self.assertIn("To: Sam", ready)
        self.assertIn("since Monday", ready)

    def test_retries_once_then_keeps_a_bad_answer_in_the_inbox(self):
        self.write_inbox("dishes.txt", "Sam", "Wash the dishes tonight.")
        model = FakeModel([
            "Sure, I can help with that.",
            reply("Could you wash the dishes tonight?"),
        ])

        result = nap(self.root, model, today="2026-10-24")

        self.assertEqual(len(result["ready"]), 1)
        self.assertEqual(len(model.prompts), 2)

    def test_leaves_the_note_when_both_answers_fail(self):
        self.write_inbox("dishes.txt", "Sam", "Wash the dishes tonight.")
        model = FakeModel(["nope", "still nope"])

        result = nap(self.root, model, today="2026-10-24")

        self.assertEqual(result["ready"], [])
        self.assertEqual(result["skipped"], ["dishes.txt"])
        self.assertTrue((self.root / "inbox" / "dishes.txt").exists())

    def test_rejects_an_invented_number_and_leaves_the_note(self):
        self.write_inbox("meeting.txt", "Priya", "I can't do the Friday meeting.")
        model = FakeModel([
            reply("I can do 15 minutes on Friday."),
            reply("I can do 15 minutes on Friday."),
        ])

        result = nap(self.root, model, today="2026-10-24")

        self.assertEqual(result["skipped"], ["meeting.txt"])
        self.assertTrue((self.root / "inbox" / "meeting.txt").exists())
        self.assertEqual(list((self.root / "ready").glob("*.txt")), [])

    def test_uses_the_calm_line_when_sendable_only_echoes_the_note(self):
        self.write_inbox(
            "dishes.txt",
            "Sam",
            "The dishes have been in the sink since Monday. Wash them tonight.",
        )
        model = FakeModel([
            json.dumps(
                {
                    "sendable": "The dishes have been in the sink since Monday. Wash them tonight.",
                    "why": "Could you wash the dishes tonight?",
                    "hold": False,
                }
            )
        ])

        nap(self.root, model, today="2026-10-24")

        ready = (self.root / "ready" / "2026-10-24-sam.txt").read_text(encoding="utf-8")
        message = ready.split("---", 1)[0]
        self.assertIn("Could you wash the dishes tonight?", message)
        self.assertNotIn("since Monday", message)

    def test_a_false_hold_still_produces_a_reply(self):
        self.write_inbox("dishes.txt", "Sam", "Wash the dishes tonight.")
        model = FakeModel([
            json.dumps(
                {
                    "sendable": "",
                    "why": "Could you wash the dishes tonight?",
                    "hold": True,
                }
            )
        ])

        result = nap(self.root, model, today="2026-10-24")

        self.assertEqual(result["asleep"], [])
        self.assertEqual(len(result["ready"]), 1)
        ready = (self.root / "ready" / "2026-10-24-sam.txt").read_text(encoding="utf-8")
        self.assertIn("wash the dishes tonight", ready.lower())

    def test_hold_moves_the_note_to_asleep_without_a_reply(self):
        self.write_inbox("mad.txt", "Sam", "I am furious and I should not send this yet.")
        model = FakeModel([reply("", why="still too angry", hold=True)])

        result = nap(self.root, model, today="2026-10-24")

        self.assertEqual(result["asleep"], ["mad.txt"])
        self.assertTrue((self.root / "asleep" / "mad.txt").exists())
        self.assertFalse((self.root / "ready").exists() and any((self.root / "ready").glob("*.txt")))

    def test_morning_counts_ready_replies_and_notes_still_waiting(self):
        ready = self.root / "ready"
        asleep = self.root / "asleep"
        ready.mkdir()
        asleep.mkdir()
        (ready / "a.txt").write_text("x", encoding="utf-8")
        (ready / "b.txt").write_text("x", encoding="utf-8")
        (ready / "c.txt").write_text("x", encoding="utf-8")
        (self.root / "inbox" / "party.txt").write_text("x", encoding="utf-8")
        (asleep / "mad.txt").write_text("x", encoding="utf-8")

        text = morning(self.root)

        self.assertEqual(
            text,
            "3 replies are ready. 2 notes are still in the box.\n"
            "You don't have to write any of them. Read, send, or put them back.",
        )

    def test_undo_puts_the_last_nap_back_in_the_inbox(self):
        self.write_inbox("dishes.txt", "Sam", "Wash the dishes tonight.")
        model = FakeModel([reply("Could you wash the dishes tonight?")])
        nap(self.root, model, today="2026-10-24")

        restored = undo(self.root)

        self.assertEqual(restored, ["dishes.txt"])
        self.assertTrue((self.root / "inbox" / "dishes.txt").exists())
        self.assertFalse((self.root / "kept" / "dishes.txt").exists())
        self.assertEqual(list((self.root / "ready").glob("*.txt")), [])

    def test_second_note_to_the_same_person_does_not_overwrite(self):
        self.write_inbox("one.txt", "Sam", "Wash the dishes tonight.")
        self.write_inbox("two.txt", "Sam", "Also take the bins out tonight.")
        model = FakeModel([
            reply("Could you wash the dishes tonight?"),
            reply("Could you also take the bins out tonight?"),
        ])

        nap(self.root, model, today="2026-10-24")

        names = sorted(p.name for p in (self.root / "ready").glob("*.txt"))
        self.assertEqual(names, ["2026-10-24-sam-2.txt", "2026-10-24-sam.txt"])


class LocalModelTests(unittest.TestCase):
    def test_localhost_is_allowed(self):
        self.assertTrue(is_local_host("http://127.0.0.1:11434"))
        self.assertTrue(is_local_host("http://localhost:11434"))

    def test_a_cloud_host_is_refused(self):
        self.assertFalse(is_local_host("https://generativelanguage.googleapis.com"))
        with self.assertRaises(ValueError):
            OllamaModel(host="https://api.openai.com")


if __name__ == "__main__":
    unittest.main()
