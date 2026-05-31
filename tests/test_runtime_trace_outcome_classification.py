"""Fixture tests for offline runtime trace outcome classification."""
from __future__ import annotations

import unittest

from scripts.analyze_runtime_trace_outcome import classify_task_outcome, evidence_from_events


def metrics(**overrides):
    base = {
        "reward": 0.0,
        "db_match": False,
        "db_reward": 0.0,
        "write_actions_total": 1,
        "write_actions_matched": 0,
        "write_action_names": ["create_task"],
        "normal_stop": True,
        "termination_reason": "user_stop",
    }
    base.update(overrides)
    return base


def evidence(**overrides):
    base = {
        "live_write_tool_detected_before_evaluation": False,
        "state_hash_changed_during_live_write": False,
        "tool_result_payload_count": 0,
        "mutation_evidence_present": False,
    }
    base.update(overrides)
    return base


class RuntimeTraceOutcomeClassificationTests(unittest.TestCase):
    def outcome(self, metric_overrides=None, evidence_overrides=None):
        return classify_task_outcome(metrics(**(metric_overrides or {})), evidence(**(evidence_overrides or {})))[
            "task_outcome"
        ]

    def test_success_requires_reward_db_action_match_and_normal_stop(self):
        success_metrics = metrics(reward=1.0, db_match=True, db_reward=1.0, write_actions_matched=1)
        self.assertEqual(classify_task_outcome(success_metrics, evidence())["task_outcome"], "success")

        missing_required_success_evidence = [
            {"reward": 0.0},
            {"db_match": False},
            {"write_actions_matched": 0},
            {"normal_stop": False, "termination_reason": "max_steps"},
        ]
        for override in missing_required_success_evidence:
            with self.subTest(override=override):
                candidate = dict(success_metrics)
                candidate.update(override)
                self.assertNotEqual(classify_task_outcome(candidate, evidence())["task_outcome"], "success")

    def test_failed_no_write_detects_expected_write_not_performed(self):
        no_write_metrics = metrics(reward=0.0, db_match=False, write_actions_total=1, write_actions_matched=0)
        no_write_evidence = evidence_from_events(
            [
                {"_sequence": 1, "event_type": "agent_response"},
                {"_sequence": 2, "event_type": "evaluation_start"},
                {"_sequence": 3, "event_type": "tool_dispatch_start", "tool_name": "create_task"},
            ],
            no_write_metrics,
        )

        self.assertFalse(no_write_evidence["live_write_tool_detected_before_evaluation"])
        self.assertEqual(no_write_evidence["evaluation_write_event_count"], 1)
        self.assertEqual(classify_task_outcome(no_write_metrics, no_write_evidence)["task_outcome"], "failed_no_write")

    def test_failed_partial_progress_detects_live_write_evidence_but_failed_result(self):
        partial_metrics = metrics(reward=0.0, db_match=False, write_actions_total=1, write_actions_matched=0)
        partial_evidence = evidence_from_events(
            [
                {
                    "_sequence": 1,
                    "event_id": "dispatch-start-1",
                    "event_type": "tool_dispatch_start",
                    "tool_name": "create_task",
                    "payload": {"state_hash_before": "state-a"},
                },
                {
                    "_sequence": 2,
                    "event_id": "dispatch-end-1",
                    "event_type": "tool_dispatch_end",
                    "tool_name": "create_task",
                    "payload": {
                        "state_hash_before": "state-a",
                        "state_hash_after": "state-b",
                        "result": {"task_id": "task_2", "status": "created"},
                    },
                },
                {"_sequence": 3, "event_type": "evaluation_start"},
            ],
            partial_metrics,
        )

        self.assertTrue(partial_evidence["live_write_tool_detected_before_evaluation"])
        self.assertTrue(partial_evidence["state_hash_changed_during_live_write"])
        self.assertEqual(partial_evidence["tool_result_payload_count"], 1)
        self.assertEqual(classify_task_outcome(partial_metrics, partial_evidence)["task_outcome"], "failed_partial_progress")

    def test_failed_max_steps_is_distinct_from_generic_unknown(self):
        self.assertEqual(
            self.outcome({"termination_reason": "max_steps", "normal_stop": False, "write_actions_total": 0}),
            "failed_max_steps",
        )
        self.assertEqual(
            self.outcome({"termination_reason": "agent_stop", "normal_stop": False, "write_actions_total": 0}),
            "failed_unknown",
        )

    def test_failed_unknown_catches_insufficient_or_ambiguous_evidence(self):
        ambiguous_metrics = metrics(
            reward=None,
            db_match=None,
            db_reward=None,
            write_actions_total=0,
            write_actions_matched=0,
            write_action_names=[],
            normal_stop=False,
            termination_reason=None,
        )
        result = classify_task_outcome(ambiguous_metrics, evidence())

        self.assertEqual(result["task_outcome"], "failed_unknown")
        self.assertFalse(result["outcome_is_success"])


if __name__ == "__main__":
    unittest.main()
