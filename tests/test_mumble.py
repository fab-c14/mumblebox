import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mumble.box import draft_note, morning, nap, undo
from mumble.decide import guard_text, parse_drafts
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


def three(soft, brief, plain, hold=False):
    return json.dumps(
        {
            "hold": hold,
            "drafts": [
                {"tone": "soft", "text": soft},
                {"tone": "brief", "text": brief},
                {"tone": "plain", "text": plain},
            ],
        }
    )


class DraftTests(unittest.TestCase):
    def test_parses_three_different_replies(self):
        parsed = parse_drafts(
            three(
                "Could you wash the dishes tonight? They have been there since Monday.",
                "The dishes have been there since Monday. Please wash them tonight.",
                "Wash the dishes tonight. They have been in the sink since Monday.",
            )
        )
        self.assertEqual([item["tone"] for item in parsed["drafts"]], ["soft", "brief", "plain"])
        self.assertFalse(parsed["hold"])

    def test_rejects_three_copies_of_the_same_reply(self):
        with self.assertRaises(ValueError):
            parse_drafts(three("Wash them tonight.", "Wash them tonight.", "Wash them tonight."))

    def test_rejects_an_invented_number(self):
        with self.assertRaises(ValueError) as caught:
            guard_text("I can meet for 45 minutes on Friday.", "I can't do the Friday meeting.")
        self.assertIn("45", str(caught.exception))

    def test_retries_then_keeps_three_replies(self):
        model = FakeModel(
            [
                "not json",
                three(
                    "Could you wash the dishes tonight?",
                    "Please wash the dishes tonight.",
                    "Wash the dishes tonight.",
                ),
            ]
        )
        parsed = draft_note(model, "Sam", "Wash the dishes tonight.", "To: Sam\nWash the dishes tonight.")
        self.assertEqual(len(parsed["drafts"]), 3)
        self.assertEqual(len(model.prompts), 2)

    def test_a_cloud_host_is_refused(self):
        self.assertTrue(is_local_host("http://127.0.0.1:11434"))
        with self.assertRaises(ValueError):
            OllamaModel(host="https://api.openai.com")


class NapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "inbox").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_note_becomes_three_files_and_the_rest_wait(self):
        (self.root / "inbox" / "dishes.txt").write_text(
            "To: Sam\nWash the dishes tonight.\n", encoding="utf-8"
        )
        (self.root / "inbox" / "party.txt").write_text(
            "To: Alex\nI don't want to go to the party.\n", encoding="utf-8"
        )
        model = FakeModel(
            [
                three(
                    "Could you wash the dishes tonight?",
                    "Please wash the dishes tonight.",
                    "Wash the dishes tonight.",
                )
            ]
        )
        result = nap(self.root, model, today="2026-10-24")
        self.assertEqual(len(result["ready"]), 3)
        self.assertEqual(result["left"], ["party.txt"])
        self.assertTrue((self.root / "ready" / "2026-10-24-sam-soft.txt").exists())
        self.assertTrue((self.root / "ready" / "2026-10-24-sam-brief.txt").exists())
        self.assertTrue((self.root / "ready" / "2026-10-24-sam-plain.txt").exists())
        self.assertTrue((self.root / "inbox" / "party.txt").exists())
        text = morning(self.root)
        self.assertIn("3 drafts are ready", text)
        self.assertIn("1 note is still in the box", text)

    def test_undo_puts_the_note_back_and_removes_the_three_drafts(self):
        (self.root / "inbox" / "dishes.txt").write_text(
            "To: Sam\nWash the dishes tonight.\n", encoding="utf-8"
        )
        model = FakeModel(
            [
                three(
                    "Could you wash the dishes tonight?",
                    "Please wash the dishes tonight.",
                    "Wash the dishes tonight.",
                )
            ]
        )
        nap(self.root, model, today="2026-10-24")
        restored = undo(self.root)
        self.assertEqual(restored, ["dishes.txt"])
        self.assertTrue((self.root / "inbox" / "dishes.txt").exists())
        self.assertEqual(list((self.root / "ready").glob("*.txt")), [])

    def test_a_note_that_says_not_to_send_is_not_drafted(self):
        (self.root / "inbox" / "mad.txt").write_text(
            "To: Sam\nI should not send this yet.\n", encoding="utf-8"
        )
        model = FakeModel([json.dumps({"hold": True, "drafts": []})])
        result = nap(self.root, model, today="2026-10-24")
        self.assertEqual(result["asleep"], ["mad.txt"])
        self.assertEqual(result["ready"], [])


if __name__ == "__main__":
    unittest.main()
