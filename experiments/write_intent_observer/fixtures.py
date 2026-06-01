"""In-memory no-LLM fixtures for passive write-intent observer smoke tests."""
from __future__ import annotations

from typing import Any


def fixture_cases() -> list[dict[str, Any]]:
    """Return deterministic cases covering known write-intent gap classes."""
    return [
        {
            "case_id": "airline_task8_baseline_missing_kevin_wrong_payment",
            "label": "airline task 8 baseline: missing Kevin + wrong payment",
            "domain": "airline",
            "source": "known_failed_runtime_trace_summary",
            "expected_write": True,
            "write_tool_names": ["book_reservation"],
            "ledger": {
                "required_entities": ["Kevin", "Daniel"],
                "expected_write_args": {
                    "payment_method": "travel_certificate",
                    "total_price": 600,
                },
                "required_prerequisite_reads": ["search_flights", "get_user_details"],
                "supported_options": ["option_with_kevin_and_daniel"],
                "evidence": [
                    {"evidence_id": "b1", "source": "tool_response", "tool_name": "search_flights", "description": "flight option supports Kevin and Daniel", "turn_index": 4},
                    {"evidence_id": "b2", "source": "tool_response", "tool_name": "get_user_details", "description": "travel certificate available", "turn_index": 2},
                ],
            },
            "tool_calls": [
                {
                    "event_id": "b-write-1",
                    "turn_index": 7,
                    "tool_name": "book_reservation",
                    "arguments": {
                        "passengers": [{"name": "Daniel"}],
                        "payment_method": "credit_card",
                        "total_price": 500,
                        "selected_option": "option_daniel_only",
                    },
                }
            ],
            "post_write_state": {"matches_expected": False, "description": "reservation omitted Kevin and charged card"},
            "evaluation": {"ambiguous": False},
            "expected_warning_codes": ["required_entity_missing", "payment_mismatch", "price_mismatch", "selected_option_unsupported", "requires_future_control_to_block"],
        },
        {
            "case_id": "airline_task8_prompt_variant_wrong_payment_missing_search",
            "label": "airline task 8 prompt variant: passengers preserved, wrong payment, missing prerequisite search evidence",
            "domain": "airline",
            "source": "known_prompt_variant_trace_summary",
            "expected_write": True,
            "write_tool_names": ["book_reservation"],
            "ledger": {
                "required_entities": ["Kevin", "Daniel"],
                "expected_write_args": {"payment_method": "travel_certificate", "total_price": 600},
                "required_prerequisite_reads": ["search_flights", "get_user_details"],
                "supported_options": ["option_with_kevin_and_daniel"],
                "evidence": [
                    {"evidence_id": "v1", "source": "tool_response", "tool_name": "get_user_details", "description": "travel certificate available", "turn_index": 2}
                ],
            },
            "tool_calls": [
                {
                    "event_id": "v-write-1",
                    "turn_index": 6,
                    "tool_name": "book_reservation",
                    "arguments": {
                        "passengers": [{"name": "Kevin"}, {"name": "Daniel"}],
                        "payment_method": "credit_card",
                        "total_price": 600,
                        "selected_option": "option_with_kevin_and_daniel",
                    },
                }
            ],
            "post_write_state": {"matches_expected": False, "description": "passengers preserved but wrong payment source"},
            "evaluation": {"ambiguous": False},
            "expected_warning_codes": ["payment_mismatch", "write_before_prerequisite_read", "requires_future_control_to_block"],
        },
        {
            "case_id": "successful_create_task_1",
            "label": "successful create_task_1: supported write with no warning",
            "domain": "mock",
            "source": "known_successful_runtime_trace_summary",
            "expected_write": True,
            "write_tool_names": ["create_task"],
            "ledger": {
                "required_entities": ["task:call_user"],
                "expected_write_args": {"title": "Call user", "assignee": "assistant"},
                "required_prerequisite_reads": ["list_users"],
                "supported_options": ["assistant"],
                "evidence": [
                    {"evidence_id": "s1", "source": "tool_response", "tool_name": "list_users", "description": "assistant user exists", "turn_index": 1}
                ],
            },
            "tool_calls": [
                {
                    "event_id": "s-write-1",
                    "turn_index": 3,
                    "tool_name": "create_task",
                    "arguments": {"title": "Call user", "assignee": "assistant", "entity_refs": ["task:call_user"]},
                }
            ],
            "post_write_state": {"matches_expected": True, "description": "created task matches expected DB state"},
            "evaluation": {"ambiguous": False},
            "expected_warning_codes": [],
        },
        {
            "case_id": "failed_no_write_expected_absent",
            "label": "failed no-write case: expected write absent",
            "domain": "mock",
            "source": "failed_partial_trace_summary",
            "expected_write": True,
            "write_tool_names": ["update_task"],
            "ledger": {
                "required_entities": ["task:overdue_followup"],
                "expected_write_args": {"status": "completed"},
                "required_prerequisite_reads": ["get_task"],
                "supported_options": ["completed"],
                "evidence": [
                    {"evidence_id": "n1", "source": "tool_response", "tool_name": "get_task", "description": "target task exists", "turn_index": 1}
                ],
            },
            "tool_calls": [],
            "post_write_state": {"matches_expected": False, "description": "task remained unchanged because no write occurred"},
            "evaluation": {"ambiguous": False},
            "expected_warning_codes": ["no_write_observed", "post_write_state_mismatch"],
        },
        {
            "case_id": "db_mismatch_scoring_ambiguity",
            "label": "DB mismatch / scoring ambiguity case",
            "domain": "mock",
            "source": "update_task_user_tools_db_mismatch_summary",
            "expected_write": True,
            "write_tool_names": ["update_task"],
            "ledger": {
                "required_entities": ["task:customer_callback"],
                "expected_write_args": {"status": "completed", "task_id": "customer_callback"},
                "required_prerequisite_reads": ["get_task"],
                "supported_options": ["completed"],
                "evidence": [
                    {"evidence_id": "d1", "source": "tool_response", "tool_name": "get_task", "description": "task exists and can be completed", "turn_index": 1}
                ],
            },
            "tool_calls": [
                {
                    "event_id": "d-write-1",
                    "turn_index": 3,
                    "tool_name": "update_task",
                    "arguments": {"task_id": "customer_callback", "status": "completed", "entity_refs": ["task:customer_callback"]},
                }
            ],
            "post_write_state": {"matches_expected": False, "description": "runtime write looked valid but persisted DB did not match scorer expectation"},
            "evaluation": {"ambiguous": True, "description": "tool DB and evaluation DB appear to disagree"},
            "expected_warning_codes": ["post_write_state_mismatch", "scoring_evaluation_ambiguity"],
        },
    ]
