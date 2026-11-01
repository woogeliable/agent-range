import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from arange.app import App


class CourseTierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(
            db_path=os.path.join(self.tmp.name, "range.sqlite3"),
            lessons_dir=os.path.join(ROOT, "lessons"),
            secret="tier-test-secret",
            web_dir=os.path.join(ROOT, "web"),
        )
        self.user = self.app.store.create_user("tier-tester")
        status, payload = self.app.api.handle("GET", "/api/lessons", "", None, self.user)
        self.assertEqual(status, 200)
        self.payload = payload
        self.stages = {stage["id"]: stage for stage in payload["stages"]}
        self.chapters = {chapter["id"]: chapter for chapter in payload["chapters"]}

    def test_three_stages_cover_the_curriculum(self):
        self.assertEqual([stage["id"] for stage in self.payload["stages"]], ["foundation", "applied", "challenge"])
        self.assertEqual({stage["title"] for stage in self.payload["stages"]}, {"初阶", "中阶", "高阶"})

    def test_stage_counts_and_time_are_balanced(self):
        expected = {
            "foundation": (6, 66, 17),
            "applied": (5, 93, 15),
            "challenge": (6, 115, 18),
        }
        for stage_id, (lessons, minutes, tasks) in expected.items():
            stage = self.stages[stage_id]
            self.assertEqual(stage["lesson_count"], lessons)
            self.assertEqual(stage["minutes"], minutes)
            self.assertEqual(stage["total_tasks"], tasks)
            self.assertEqual(stage["completed_lessons"], 0)
            self.assertEqual(stage["completed_tasks"], 0)

    def test_every_live_lesson_appears_exactly_once(self):
        live = {
            lesson["id"]
            for chapter in self.payload["chapters"]
            if not chapter["upcoming"]
            for lesson in chapter["lessons"]
        }
        staged = []
        for stage in self.payload["stages"]:
            for chapter_id in stage["chapters"]:
                staged.extend(lesson["id"] for lesson in self.chapters[chapter_id]["lessons"])
        self.assertEqual(len(staged), 17)
        self.assertEqual(set(staged), live)
        self.assertEqual(len(set(staged)), len(staged))

    def test_stage_mapping_matches_chapter_bands(self):
        self.assertEqual(self.stages["foundation"]["chapters"], ["00", "01"])
        self.assertEqual(self.stages["applied"]["chapters"], ["02", "03"])
        self.assertEqual(self.stages["challenge"]["chapters"], ["04", "05"])
        for chapter in self.payload["chapters"]:
            if chapter["id"] in {"06", "07"}:
                self.assertEqual(chapter["stage"], "")
                self.assertNotIn(chapter["id"], self.stages["challenge"]["chapters"])
            else:
                self.assertIn(chapter["stage"], self.stages)

    def test_lesson_detail_has_stage_context(self):
        status, payload = self.app.api.handle("GET", "/api/lessons/4.1", "", None, self.user)
        self.assertEqual(status, 200)
        self.assertEqual(payload["chapter"]["stage"], "challenge")
        self.assertEqual(payload["chapter"]["stage_title"], "高阶")
        self.assertEqual(payload["lesson"]["id"], "4.1")

    def test_stage_progress_aggregates_tasks_and_lessons(self):
        self.app.store.mark_task(self.user["id"], "0.1", "t1")
        _, payload = self.app.api.handle("GET", "/api/lessons", "", None, self.user)
        foundation = next(stage for stage in payload["stages"] if stage["id"] == "foundation")
        self.assertEqual(foundation["completed_tasks"], 1)
        self.assertEqual(foundation["completed_lessons"], 0)

        for task_id in ("t2", "t3"):
            self.app.store.mark_task(self.user["id"], "0.1", task_id)
        _, payload = self.app.api.handle("GET", "/api/lessons", "", None, self.user)
        foundation = next(stage for stage in payload["stages"] if stage["id"] == "foundation")
        self.assertEqual(foundation["completed_tasks"], 3)
        self.assertEqual(foundation["completed_lessons"], 1)

    def test_stage_totals_match_lesson_totals(self):
        lessons = [
            lesson
            for chapter in self.payload["chapters"]
            for lesson in chapter["lessons"]
        ]
        self.assertEqual(sum(lesson["total_tasks"] for lesson in lessons), 50)
        self.assertEqual(sum(lesson["minutes"] for lesson in lessons), 274)
        self.assertEqual(sum(stage["total_tasks"] for stage in self.payload["stages"]), 50)
        self.assertEqual(sum(stage["minutes"] for stage in self.payload["stages"]), 274)


if __name__ == "__main__":
    unittest.main()
