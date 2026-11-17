"""Isolated persistence and review-policy tests; never reads learner history."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import coach


def lesson(day, **updates):
    """生成纯模拟的指定日期课程；只用于测试，不读取任何学习历史。"""
    item = dict(key="grammar-example", kind="grammar", expression="にもまして", observed=True,
                state="passive", evidence="Synthetic learner explained the meaning.", support="none",
                is_review=False, independent_correct=False, transfer=False)
    item.update(updates)
    return dict(version=1, id=f"test-{day}", created_at=f"2026-11-{day:02d}T20:00:00+08:00",
                language="ja", mode="daily", summary="Synthetic lesson", audio_observed=False,
                pronunciation_notes=[], items=[item], focus_next=[])


def passed(day):
    """构造延迟、无提示且正确的新语境复测证据，供日期规则测试使用。"""
    return lesson(day, state="independent", is_review=True, independent_correct=True, transfer=True)


class CoachTests(unittest.TestCase):
    def test_cli_archive_and_resume_in_separate_processes(self):
        """在两个独立进程中验证保存与续接，确认复习数据不依赖进程内状态。"""
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as temp:
            root = Path(temp)
            source = root / "input.json"
            source.write_text(json.dumps(lesson(17)), encoding="utf-8")
            script = str(Path(coach.__file__).resolve())
            result = subprocess.run([sys.executable, script, "archive", "--data-dir", str(root), "--input", str(source)], capture_output=True, text=True, check=True)
            self.assertIn("saved", json.loads(result.stdout))
            result = subprocess.run([sys.executable, script, "due", "--data-dir", str(root), "--on", "2026-11-18"], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)["due"][0]["due_date"], "2026-11-18")

    def test_immutable_and_idempotent(self):
        """验证重复归档不重复记课，冲突 ID 不覆盖原始记录。"""
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as temp:
            root = Path(temp)
            record = lesson(17)
            target = coach.archive(root, record)
            self.assertEqual(coach.archive(root, record), target)
            changed = copy.deepcopy(record)
            changed["summary"] = "different"
            with self.assertRaises(ValueError):
                coach.archive(root, changed)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), record)
            self.assertEqual(coach.load_sessions(root), [record])

    def test_paths_and_audio_claims(self):
        """验证非法或设备名 ID 及没有音频的发音断言被拒绝。"""
        for value in ("../escape", "..", "bad/name", "bad.name", "CON", "NUL", "COM1"):
            record = lesson(17)
            record["id"] = value
            with self.assertRaises(ValueError):
                coach.validate(record)
        record = lesson(17)
        record["pronunciation_notes"] = ["perfect pitch"]
        with self.assertRaises(ValueError):
            coach.validate(record)

    def test_model_cannot_count_as_independent(self):
        """验证模仿示范不能记录为独立掌握。"""
        with self.assertRaises(ValueError):
            coach.validate(lesson(18, state="independent", support="model", transfer=True, independent_correct=True))

    def test_day_1_3_7_and_completion(self):
        """验证第 1、3、7 天逐轮复习及最终完成后的队列状态。"""
        records = [lesson(17)]
        self.assertEqual(coach.review_queue(records, date(2026, 11, 17)), [])
        self.assertEqual(coach.review_queue(records, date(2026, 11, 18))[0]["due_date"], "2026-11-18")
        records.append(passed(18))
        self.assertEqual(coach.review_queue(records, date(2026, 11, 19)), [])
        self.assertEqual(coach.review_queue(records, date(2026, 11, 20))[0]["completed_rounds"], 1)
        records.append(passed(20))
        self.assertEqual(coach.review_queue(records, date(2026, 11, 24))[0]["completed_rounds"], 2)
        records.append(passed(24))
        self.assertEqual(coach.review_queue(records, date(2026, 11, 30)), [])

    def test_no_same_day_or_early_credit(self):
        """验证同一天多次作答或提前复测不能跳过间隔。"""
        records = [lesson(17), passed(17)]
        self.assertEqual(coach.review_queue(records, date(2026, 11, 18))[0]["completed_rounds"], 0)
        records += [passed(18), passed(18), passed(19)]
        self.assertEqual(coach.review_queue(records, date(2026, 11, 20))[0]["completed_rounds"], 1)

    def test_late_pass_spreads_backlog(self):
        """验证迟到复习通过后至少间隔一天，不把积压任务挤在当天。"""
        records = [lesson(17), passed(27)]
        self.assertEqual(coach.review_queue(records, date(2026, 11, 27)), [])
        row = coach.review_queue(records, date(2026, 11, 28))[0]
        self.assertEqual((row["due_date"], row["completed_rounds"]), ("2026-11-28", 1))

    def test_failed_review_restarts_from_next_day(self):
        """验证复测遗忘后从次日重新安排巩固，而不是保留虚假的通过轮次。"""
        records = [lesson(17), passed(18), lesson(20, state="reconsolidate", is_review=True)]
        self.assertEqual(coach.review_queue(records, date(2026, 11, 20)), [])
        row = coach.review_queue(records, date(2026, 11, 21))[0]
        self.assertEqual((row["due_date"], row["completed_rounds"]), ("2026-11-21", 0))

    def test_unobserved_preserves_previous_state(self):
        """验证未获得表达机会不会覆盖旧状态或改变复习日期。"""
        missed = lesson(18)
        missed["items"] = [dict(key="grammar-example", kind="grammar", expression="にもまして", observed=False)]
        row = coach.review_queue([lesson(17), missed], date(2026, 11, 18))[0]
        self.assertEqual((row["state"], row["due_date"]), ("passive", "2026-11-18"))

    def test_future_records_do_not_affect_past_queue(self):
        """验证查询过去日期时不会提前使用未来课程证据。"""
        row = coach.review_queue([lesson(17), passed(20)], date(2026, 11, 18))[0]
        self.assertEqual(row["completed_rounds"], 0)


if __name__ == "__main__":
    unittest.main()
