"""
Stage 6 – Full Orchestration E2E Tests

End-to-end flows that combine multiple components:
- Dispatch + WP6 context + response flow (Pydantic V2)
- Dispatch + WP7 indexing flow (Pydantic V2)
- PA Intent Router + stage/phase + allowed tools flow
- Multi-tool scenario (read + filter + update)
- Full pipeline with trace propagation
- Contract compliance across all layers
"""
import json
import uuid
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from .conftest import (
    dispatch_tool_call,
    validate_and_normalize,
    dispatch_mod,
    PYDANTIC_V2,
    requires_pydantic_v2,
    requires_pa_router,
    HAS_PA_ROUTER,
    HAS_PA_STAGES,
    ContextBuilderInput,
    PreferencesV1,
    ContextPackV1,
    assemble_quick_context,
    assemble_comprehensive_context,
    build_context_with_routing,
    select_context_mode,
    IndexerInput,
    IndexerOutput,
    IndexingMode,
    SemanticCategory,
    BatchIndexerInput,
    index_interaction,
    index_interactions_batch,
    analyze_indexer_performance,
    handler,
    TOOL_SPECS,
    get_tool_names,
    ToolError,
)


# ── 6.1  Dispatch + Context Building Flow (Pydantic V2) ────────────────────

@requires_pydantic_v2
class TestDispatchContextFlow:
    """Simulate a request that uses dispatch and context building together."""

    def test_fast_dispatch_then_context(self, mock_delegate, test_user_id):
        delegate = mock_delegate({"blobs": ["file1.json", "file2.json"], "count": 2})

        inp = ContextBuilderInput(user_id=test_user_id, message="List my files")
        pack, metadata = build_context_with_routing(inp)
        assert pack.mode == "FAST"

        result = dispatch_tool_call("list_blobs", {}, test_user_id)
        assert result["status"] == "success"
        assert result["user_id"] == test_user_id

    def test_deep_dispatch_then_context(self, mock_delegate, test_user_id):
        delegate = mock_delegate({"data": [{"id": 1}, {"id": 2}], "total": 10})

        msg = (
            "Analyze the correlation between project milestones and team performance. "
            "Compare Q1 vs Q2 data and evaluate the trend."
        )
        inp = ContextBuilderInput(user_id=test_user_id, message=msg, mode="DEEP")
        pack, metadata = build_context_with_routing(inp)
        assert pack.mode == "DEEP"
        assert pack.budgets["token_limit"] >= 4000

        result = dispatch_tool_call(
            "get_filtered_data",
            {"target_blob_name": "metrics.json", "filter_key": "quarter", "filter_value": "Q1"},
            test_user_id,
        )
        assert result["status"] == "success"


# ── 6.2  Dispatch + Indexing Flow (Pydantic V2) ────────────────────────────

@requires_pydantic_v2
class TestDispatchIndexingFlow:
    """Simulate dispatch + index the interaction."""

    def test_dispatch_then_index(self, mock_delegate, test_user_id):
        delegate = mock_delegate({"data": "time_result"})

        result = dispatch_tool_call("get_current_time", {}, test_user_id)
        assert result["status"] == "success"

        iid = f"INT_{uuid.uuid4().hex[:8]}"
        indexer_input = IndexerInput(
            user_id=test_user_id,
            interaction_id=iid,
            message="What time is it?",
            tool_calls=[{"name": "get_current_time", "result": result}],
            mode=IndexingMode.REALTIME,
        )
        output = index_interaction(indexer_input, use_mock=True)

        assert output.mode_used == IndexingMode.REALTIME
        assert output.items[0].interaction_id == iid
        assert output.total_tokens > 0


# ── 6.3  Multi-Tool Scenario ────────────────────────────────────────────────

class TestMultiToolScenario:
    """Simulate multi-step tool usage: list + read + update."""

    def test_list_read_update_flow(self, mock_delegate, test_user_id, trace_ctx):
        # Step 1: List blobs
        delegate = mock_delegate({"blobs": ["tasks.json"], "count": 1})
        r1 = dispatch_tool_call("list_blobs", {"prefix": "tasks"}, test_user_id, trace_ctx)
        assert r1["status"] == "success"

        # Step 2: Read the file
        delegate = mock_delegate({"data": [{"id": "1", "task": "Review", "status": "pending"}]})
        r2 = dispatch_tool_call(
            "read_blob_file", {"file_name": "tasks.json"}, test_user_id, trace_ctx
        )
        assert r2["status"] == "success"

        # Step 3: Update the entry
        delegate = mock_delegate({"modified": 1})
        r3 = dispatch_tool_call(
            "update_data_entry",
            {
                "target_blob_name": "tasks.json",
                "find_key": "id",
                "find_value": "1",
                "update_key": "status",
                "update_value": "done",
            },
            test_user_id,
            trace_ctx,
        )
        assert r3["status"] == "success"

        # All responses have same trace
        assert r1["trace_id"] == r2["trace_id"] == r3["trace_id"]

    def test_add_then_remove_flow(self, mock_delegate, test_user_id, trace_ctx):
        """Add an entry, then remove it."""
        delegate = mock_delegate({"count": 1})
        r1 = dispatch_tool_call(
            "add_new_data",
            {"target_blob_name": "items.json", "new_entry": {"id": "x", "val": 42}},
            test_user_id,
            trace_ctx,
        )
        assert r1["status"] == "success"

        delegate = mock_delegate({"removed": 1})
        r2 = dispatch_tool_call(
            "remove_data_entry",
            {"target_blob_name": "items.json", "remove_key": "id", "remove_value": "x"},
            test_user_id,
            trace_ctx,
        )
        assert r2["status"] == "success"

    def test_upload_then_read_flow(self, mock_delegate, test_user_id):
        delegate = mock_delegate({"uploaded": "notes.txt"})
        r1 = dispatch_tool_call(
            "upload_data_or_file",
            {"target_blob_name": "notes.txt", "file_content": "Hello World"},
            test_user_id,
        )
        assert r1["status"] == "success"

        delegate = mock_delegate({"data": "Hello World"})
        r2 = dispatch_tool_call(
            "read_blob_file", {"file_name": "notes.txt"}, test_user_id
        )
        assert r2["status"] == "success"


# ── 6.4  PA Intent Router Flow ──────────────────────────────────────────────

@requires_pa_router
class TestPAIntentRouterFlow:
    """PA intent router + stage/phase + allowed tools validation."""

    PA_PHASES = ("DISCOVERY", "PLAN", "CONFIRM", "EXECUTE")

    def test_intent_router_contract(self):
        result = handler._pa_intent_router("Check my emails")
        required_keys = {
            "top_intents",
            "recommended_stage",
            "recommended_phase",
            "need_clarification",
            "clarify_questions",
            "evidence",
        }
        assert required_keys.issubset(result.keys())

    @pytest.mark.skipif(not HAS_PA_STAGES, reason="PA_INTENT_STAGES not available")
    def test_all_stage_phase_combos_have_tools(self):
        if not hasattr(handler, "_pa_allowed_tools_for_stage_phase"):
            pytest.skip("Legacy _pa_allowed_tools_for_stage_phase removed in current runtime")
        for stage in handler.PA_INTENT_STAGES:
            for phase in self.PA_PHASES:
                allowed = handler._pa_allowed_tools_for_stage_phase(stage, phase)
                assert allowed, f"No tools for {stage}/{phase}"

    @pytest.mark.skipif(not HAS_PA_STAGES, reason="PA_INTENT_STAGES not available")
    def test_non_execute_phases_block_write_tools(self):
        if not hasattr(handler, "PA_WRITE_TOOLS") or not hasattr(handler, "_pa_allowed_tools_for_stage_phase"):
            pytest.skip("Legacy PA stage/phase allowlist API not available")
        for stage in handler.PA_INTENT_STAGES:
            for phase in ("DISCOVERY", "PLAN", "CONFIRM"):
                allowed = handler._pa_allowed_tools_for_stage_phase(stage, phase)
                write_overlap = handler.PA_WRITE_TOOLS & allowed
                assert not write_overlap, f"Write tools {write_overlap} in {stage}/{phase}"

    def test_intent_router_to_dispatch(self, mock_delegate):
        delegate = mock_delegate({"ok": True})

        result = handler._pa_intent_router("List my files")
        stage = result["recommended_stage"]

        if HAS_PA_STAGES:
            assert stage in handler.PA_INTENT_STAGES

        r = dispatch_tool_call("list_blobs", {}, "pa_test_user")
        assert r["status"] == "success"


# ── 6.5  Full Pipeline with Trace Propagation ──────────────────────────────

class TestFullPipelineTrace:
    """Trace ID flows through context + dispatch + indexing."""

    def test_trace_through_dispatch(self, mock_delegate, test_user_id):
        trace_id = f"trace-full-{uuid.uuid4().hex[:8]}"
        ctx = {"trace_id": trace_id}

        delegate = mock_delegate({"ok": True})
        result = dispatch_tool_call("get_current_time", {}, test_user_id, ctx)

        assert result["trace_id"] == trace_id

    @requires_pydantic_v2
    def test_correlation_through_context(self, test_user_id):
        corr_id = f"corr-{uuid.uuid4().hex[:8]}"
        inp = ContextBuilderInput(
            user_id=test_user_id, message="Hello", correlation_id=corr_id
        )
        pack = assemble_quick_context(inp)
        assert pack.correlation_id == corr_id


# ── 6.6  Contract Compliance ────────────────────────────────────────────────

class TestContractCompliance:
    """Verify contracts are enforced at every layer."""

    @requires_pydantic_v2
    def test_context_pack_v1_contract(self, builder_input_factory):
        inp = builder_input_factory(message="Contract test")
        pack = assemble_quick_context(inp)

        assert pack.schema_version == "omniflow.context_pack.v1"
        assert pack.mode in ("FAST", "DEEP")
        assert all(k in pack.budgets for k in ("token_limit", "byte_limit", "max_sources"))
        assert all(k in pack.layers for k in ("L0", "L1", "L2", "L3"))

    def test_dispatch_response_contract(self, mock_delegate, test_user_id):
        delegate = mock_delegate({"data": "test"})
        result = dispatch_tool_call("list_blobs", {}, test_user_id)

        assert result["status"] == "success"
        assert result["tool"] == "list_blobs"
        assert result["user_id"] == test_user_id

    def test_error_response_contract(self, test_user_id):
        result = dispatch_tool_call("invalid_tool_xyz", {}, test_user_id)

        assert result["status"] == "error"
        assert "code" in result
        assert "message" in result

    @requires_pydantic_v2
    def test_indexer_output_contract(self, indexer_input_factory):
        inp = indexer_input_factory(message="Contract test")
        output = index_interaction(inp, use_mock=True)

        assert len(output.items) >= 1
        assert output.mode_used in (IndexingMode.REALTIME, IndexingMode.BATCH)
        assert output.total_tokens > 0
        assert output.processing_time_ms >= 0

    def test_all_tools_have_specs(self):
        for tool_name, spec in TOOL_SPECS.items():
            assert "description" in spec, f"{tool_name} missing description"
            assert "method" in spec, f"{tool_name} missing method"
            assert "params" in spec, f"{tool_name} missing params"
            assert "examples" in spec, f"{tool_name} missing examples"
            assert len(spec["examples"]) >= 1, f"{tool_name} has no examples"


# ── 6.7  Polish Language E2E ────────────────────────────────────────────────

class TestPolishLanguageE2E:
    """Polish language queries work end-to-end."""

    @requires_pa_router
    def test_polish_intent_routing(self):
        result = handler._pa_intent_router("Sprawdzić maile")
        assert result["top_intents"][0]["stage"] in ("EMAIL_QUERY", "EMAIL_WRITE")

    @requires_pydantic_v2
    def test_polish_context_building(self, builder_input_factory):
        inp = builder_input_factory(message="Pokaż moje pliki i zadania", mode="AUTO")
        pack, metadata = build_context_with_routing(inp)
        assert isinstance(pack, ContextPackV1)

    @requires_pydantic_v2
    def test_polish_indexing(self):
        inp = IndexerInput(
            user_id="polish_user",
            interaction_id="INT_pl001",
            message="Sprawdzić maile od wczoraj",
            mode=IndexingMode.REALTIME,
        )
        output = index_interaction(inp, use_mock=True)
        assert len(output.items) >= 1


# ── 6.8  Batch Operations E2E ───────────────────────────────────────────────

class TestBatchOperationsE2E:
    """End-to-end batch scenarios."""

    def test_batch_read_then_index(self, mock_delegate, test_user_id):
        delegate = mock_delegate({"items": [{"file": "a.json"}, {"file": "b.json"}], "count": 2})

        r = dispatch_tool_call(
            "read_many_blobs", {"files": ["a.json", "b.json"]}, test_user_id
        )
        assert r["status"] == "success"

        if not PYDANTIC_V2:
            pytest.skip("Batch indexing requires Pydantic V2")

        batch_input = BatchIndexerInput(
            user_id=test_user_id,
            interactions=[
                {"id": "INT_batch_a", "message": "Read a.json", "tools": [{"name": "read_many_blobs"}]},
                {"id": "INT_batch_b", "message": "Read b.json", "tools": [{"name": "read_many_blobs"}]},
            ],
        )
        output = index_interactions_batch(batch_input, use_mock=True)

        assert output.mode_used == IndexingMode.BATCH
        assert len(output.items) == 2

    @requires_pydantic_v2
    def test_performance_after_batch(self, test_user_id):
        outputs = []
        for i in range(3):
            inp = IndexerInput(
                user_id=test_user_id,
                interaction_id=f"INT_perf_{i}",
                message=f"Query {i}",
                mode=IndexingMode.REALTIME,
            )
            outputs.append(index_interaction(inp, use_mock=True))

        metrics = analyze_indexer_performance(outputs)
        assert metrics.cache_efficiency > 0
        assert metrics.avg_processing_time_ms >= 0
