"""Tests for shared nodes and graph wiring.

Graph compilation tests verify the structure is valid without executing LLM calls.
Shared node tests are fully rule-based — no mocking needed.
"""

from __future__ import annotations

from eval_models.schemas import EvalSubResult
from nodes.shared.aggregator import aggregator_node
from nodes.shared.threshold_check import threshold_check_node


class TestAggregatorNode:
    def test_sums_tokens_from_all_sub_results(self, eval_config):
        state = {
            "config": eval_config,
            "eval_results": [
                EvalSubResult(target="rag",   aggregates={}, tokens_used=1000),
                EvalSubResult(target="agent", aggregates={}, tokens_used=500),
            ],
            "total_tokens": 0,
            "cost_usd": 0.0,
        }
        result = aggregator_node(state)

        assert result["total_tokens"] == 1500
        assert result["cost_usd"] > 0

    def test_cost_is_nonzero_for_nonzero_tokens(self, eval_config):
        state = {
            "config": eval_config,
            "eval_results": [EvalSubResult(target="rag", aggregates={}, tokens_used=10000)],
            "total_tokens": 0,
            "cost_usd": 0.0,
        }
        result = aggregator_node(state)
        assert result["cost_usd"] > 0.0


class TestThresholdCheckNode:
    def _make_state(self, eval_config, rag_agg, agent_agg):
        return {
            "config": eval_config,
            "eval_results": [
                EvalSubResult(target="rag",   aggregates=rag_agg,   tokens_used=0),
                EvalSubResult(target="agent", aggregates=agent_agg, tokens_used=0),
            ],
        }

    def test_overall_pass_when_all_metrics_pass(self, eval_config):
        state = self._make_state(
            eval_config,
            rag_agg={
                "faithfulness": 0.85, "answer_relevance": 0.80,
                "context_recall": 0.70, "context_precision": 0.68,
            },
            agent_agg={
                "bug_recall": 0.80, "false_positive_rate": 0.20, "comment_quality": 0.75,
            },
        )
        result = threshold_check_node(state)
        assert result["overall"] == "PASS"

    def test_overall_fail_when_rag_metric_below_threshold(self, eval_config):
        state = self._make_state(
            eval_config,
            rag_agg={
                "faithfulness": 0.50,  # below 0.70
                "answer_relevance": 0.80, "context_recall": 0.70, "context_precision": 0.68,
            },
            agent_agg={
                "bug_recall": 0.80, "false_positive_rate": 0.20, "comment_quality": 0.75,
            },
        )
        result = threshold_check_node(state)
        assert result["overall"] == "FAIL"

    def test_overall_fail_when_fpr_exceeds_threshold(self, eval_config):
        state = self._make_state(
            eval_config,
            rag_agg={
                "faithfulness": 0.85, "answer_relevance": 0.80,
                "context_recall": 0.70, "context_precision": 0.68,
            },
            agent_agg={
                "bug_recall": 0.80,
                "false_positive_rate": 0.60,   # above 0.40 threshold (lower is better)
                "comment_quality": 0.75,
            },
        )
        result = threshold_check_node(state)
        assert result["overall"] == "FAIL"

    def test_overall_pass_with_only_rag_results(self, eval_config):
        state = {
            "config": eval_config,
            "eval_results": [
                EvalSubResult(
                    target="rag",
                    aggregates={
                        "faithfulness": 0.85, "answer_relevance": 0.80,
                        "context_recall": 0.70, "context_precision": 0.68,
                    },
                    tokens_used=0,
                )
            ],
        }
        result = threshold_check_node(state)
        assert result["overall"] == "PASS"


class TestGraphCompilation:
    def test_rag_graph_compiles(self):
        from graphs.rag_graph import build_rag_graph
        graph = build_rag_graph().compile()
        assert graph is not None

    def test_agent_graph_compiles(self):
        from graphs.agent_graph import build_agent_graph
        graph = build_agent_graph().compile()
        assert graph is not None

    def test_eval_graph_compiles(self):
        from graphs.eval_graph import build_eval_graph
        graph = build_eval_graph().compile()
        assert graph is not None
