"""People on one dashboard: roster, presence, seen-by, mentions (people.py, comments.py). Run: python3 -m pytest -q tests"""
import os, tempfile, unittest
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import comments, features, people
from autoresearch.core import Project


def project():
    d = Path(tempfile.mkdtemp())
    (d / "research.json").write_text("{}")
    (d / ".research").mkdir()
    return Project(d)


def call(table, path, p, d):
    return dict(table)[path](p, path, d)


class People(unittest.TestCase):
    def setUp(self):
        self.p = project()
        for pid, n in (("p-a0000001", "Ann Lee"), ("p-b0000002", "Bo"), ("p-c0000003", "Ann Ray")):
            self.assertEqual(call(features.POST, "/api/people", self.p, dict(id=pid, name=n, route="#overview"))[0], 200)

    def test_presence_and_roster(self):
        code, v = call(features.GET, "/api/people", self.p, {})
        self.assertEqual({h["id"] for h in v["here"]}, {"p-a0000001", "p-b0000002", "p-c0000003"})
        self.assertEqual(v["here"][0]["route"], "overview")
        self.assertEqual(v["people"]["p-b0000002"]["name"], "Bo")
        self.assertEqual(call(features.POST, "/api/people", self.p, dict(id="bob", name="x"))[0], 400)  # not a person id

    def test_roster_is_per_project(self):
        people.remember("p-d0000004", "Dee", "elsewhere-key")
        self.assertNotIn("p-d0000004", call(features.GET, "/api/people", self.p, {})[1]["people"])
        self.assertEqual(people.mentioned("@bo hi", {"p-1": dict(name="Bo"), "p-2": dict(name="Bo")}), [])  # two Bos: nobody is guessed

    def test_mentions(self):
        r = people.roster()
        self.assertEqual(people.mentioned("ping @bo please", r), ["p-b0000002"])
        self.assertEqual(people.mentioned("@ann what?", r), [])  # two Anns: the first name alone is ambiguous
        self.assertEqual(people.mentioned("@Ann Ray look", r), ["p-c0000003"])
        self.assertEqual(people.mentioned("mail bo@x.com", r), [])

    def test_seen_and_people_talk(self):
        post = lambda d: call(features.POST, "/api/comments", self.p, d)
        _, ev = post(dict(kind="comment", body="what is this tick?", author="Ann Lee", by="p-a0000001", anchor=dict(route="goals")))
        n = len(features.inbox(self.p))
        _, r = post(dict(kind="reply", parent=ev["id"], body="@bo do you know?", author="Ann Lee", by="p-a0000001"))
        self.assertEqual(len(features.inbox(self.p)), n)  # people talking: the agent is not woken
        th = comments.find(self.p, ev["id"])
        self.assertFalse(th["waiting"]); self.assertEqual(th["mentions"], ["p-b0000002"])
        post(dict(kind="reply", parent=ev["id"], body="@bo @agent both of you", author="Ann Lee", by="p-a0000001"))
        self.assertEqual(len(features.inbox(self.p)), n + 1)
        self.assertEqual(post(dict(kind="seen", parent=ev["id"], by="p-b0000002"))[0], 200)
        self.assertEqual(post(dict(kind="seen", parent=ev["id"]))[0], 400)
        th = comments.find(self.p, ev["id"])
        self.assertIn("p-b0000002", th["seen"]); self.assertEqual(th["people"], ["p-a0000001"])
        self.assertEqual(len(th["messages"]), 3)  # seen is not a message


if __name__ == "__main__":
    unittest.main()
