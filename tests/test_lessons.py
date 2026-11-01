import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from arange import lessons as lesson_mod


class LessonPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lessons = lesson_mod.load(os.path.join(ROOT, "lessons"))

    def test_all_packs_load_and_ids_are_stable(self):
        self.assertEqual(set(self.lessons), {"0.1", "0.2", "1.1", "1.2", "1.3", "1.4", "2.1", "2.2", "3.1", "3.2", "3.3", "5.1"})
        for lesson_id, lesson in self.lessons.items():
            self.assertEqual(lesson["id"], lesson_id)
            self.assertIn(lesson["chapter"], lesson_mod.CHAPTER_MAP)
            self.assertIn(lesson["type"], {"chat", "quiz"})
            self.assertTrue(lesson.get("title"))
            self.assertTrue(lesson.get("subtitle"))
            self.assertGreaterEqual(len(lesson.get("levels") or []), 1)
            self.assertLessEqual(set(lesson["levels"]), {"vulnerable", "basic", "hardened", "reference"})
            self.assertIn(lesson["default_level"], lesson["levels"])

    def test_tasks_have_verifiers_and_unique_ids(self):
        for lesson in self.lessons.values():
            tasks = lesson.get("tasks") or []
            self.assertGreaterEqual(len(tasks), 1, lesson["id"])
            ids = [task["id"] for task in tasks]
            self.assertEqual(len(ids), len(set(ids)))
            for task in tasks:
                self.assertTrue(task.get("title"))
                self.assertIsInstance(task.get("verify"), dict)
                self.assertTrue(task["verify"])

    def test_chat_packs_are_complete(self):
        for lesson in self.lessons.values():
            if lesson["type"] != "chat":
                continue
            target = lesson.get("target") or {}
            self.assertTrue(target.get("name"))
            self.assertTrue(target.get("system_prompt"))
            self.assertIsInstance(target.get("tools"), list)
            doc_ids = [doc.get("id") for doc in target.get("docs") or []]
            self.assertEqual(len(doc_ids), len(set(doc_ids)))
            editable = target.get("editable_doc")
            if editable:
                self.assertIn(editable, doc_ids)
            source = lesson.get("source") or {}
            self.assertTrue(source)
            self.assertLessEqual(set(source), set(lesson["levels"]))
            self.assertTrue(lesson.get("hints"))
            self.assertTrue(lesson.get("solution"))
            self.assertTrue(lesson.get("brief", {}).get("threat_model"))
            self.assertTrue(lesson.get("brief", {}).get("goal"))

    def test_quiz_answers_are_in_range(self):
        for lesson in self.lessons.values():
            if lesson["type"] != "quiz":
                continue
            questions = lesson.get("quiz", {}).get("questions") or []
            self.assertGreaterEqual(len(questions), 1)
            for question in questions:
                self.assertTrue(question.get("prompt"))
                self.assertGreaterEqual(len(question.get("options") or []), 2)
                self.assertGreaterEqual(question.get("answer"), 0)
                self.assertLess(question.get("answer"), len(question["options"]))
                self.assertTrue(question.get("explain"))

    def test_public_projection_is_consistent(self):
        lesson = self.lessons["1.1"]
        public = lesson_mod.public_lesson(lesson, {"t1": True}, {"hints_used": 1, "solution_used": 0})
        self.assertEqual(public["score"], 90)
        self.assertTrue(public["tasks"][0]["done"])
        self.assertNotIn("system_prompt", public["target"])
        self.assertNotIn("solution", public)
        self.assertEqual(public["hints_used"], 1)

    def test_score_floor(self):
        self.assertEqual(lesson_mod.score_for({"hints_used": 9, "solution_used": 1}), 0)


if __name__ == "__main__":
    unittest.main()
