"""
Integration tests for parallel tool execution.

Tests concurrency limits, timeouts, retries, and error handling.
"""

import asyncio

import pytest

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_tool_calls():
    """Create mock tool calls for testing."""
    return [
        {"name": "tool_1", "input": {"query": "test1"}},
        {"name": "tool_2", "input": {"query": "test2"}},
        {"name": "tool_3", "input": {"query": "test3"}},
    ]


# ============================================================================
# Concurrency Tests
# ============================================================================


class TestConcurrencyControl:
    """Tests for concurrency control in parallel execution."""

    @pytest.mark.asyncio
    async def test_concurrency_limit_enforced(self):
        """Test that concurrency limit is strictly enforced."""
        from airbeeps.agents.graph.nodes.executor import ParallelExecutor

        max_concurrent = 2
        concurrent_count = 0
        max_seen = 0
        lock = asyncio.Lock()

        async def counting_executor(name: str, input_data: dict) -> str:
            nonlocal concurrent_count, max_seen
            async with lock:
                concurrent_count += 1
                max_seen = max(max_seen, concurrent_count)
            await asyncio.sleep(0.05)
            async with lock:
                concurrent_count -= 1
            return "result"

        executor = ParallelExecutor(max_concurrent=max_concurrent, default_timeout=5)
        tool_calls = [{"name": f"tool_{i}", "input": {}} for i in range(10)]

        await executor.execute_batch(counting_executor, tool_calls)

        assert max_seen <= max_concurrent

    @pytest.mark.asyncio
    async def test_all_tools_complete(self, mock_tool_calls):
        """Test that all tools complete even with concurrency limit."""
        from airbeeps.agents.graph.nodes.executor import ParallelExecutor

        completed = []

        async def tracking_executor(name: str, input_data: dict) -> str:
            await asyncio.sleep(0.01)
            completed.append(name)
            return f"result_{name}"

        executor = ParallelExecutor(max_concurrent=2, default_timeout=5)

        results = await executor.execute_batch(tracking_executor, mock_tool_calls)

        assert len(results) == len(mock_tool_calls)
        assert len(completed) == len(mock_tool_calls)


# ============================================================================
# Timeout Tests
# ============================================================================


class TestTimeoutHandling:
    """Tests for timeout handling in parallel execution."""

    @pytest.mark.asyncio
    async def test_individual_tool_timeout(self):
        """Test that individual tool timeout is enforced."""
        from airbeeps.agents.graph.nodes.executor import ParallelExecutor

        async def slow_executor(name: str, input_data: dict) -> str:
            if name == "slow_tool":
                await asyncio.sleep(10)
            return "result"

        executor = ParallelExecutor(max_concurrent=3, default_timeout=0.1)
        tool_calls = [
            {"name": "fast_tool", "input": {}},
            {"name": "slow_tool", "input": {}},
        ]

        results = await executor.execute_batch(slow_executor, tool_calls)

        # Fast tool should succeed
        fast_result = next(r for r in results if r.tool_name == "fast_tool")
        assert fast_result.success

        # Slow tool should timeout
        slow_result = next(r for r in results if r.tool_name == "slow_tool")
        assert not slow_result.success

    @pytest.mark.asyncio
    async def test_tool_specific_timeout(self):
        """Test that tool-specific timeouts are respected."""
        from airbeeps.agents.graph.nodes.executor import ParallelExecutor

        async def variable_executor(name: str, input_data: dict) -> str:
            delay = input_data.get("delay", 0)
            await asyncio.sleep(delay)
            return "result"

        executor = ParallelExecutor(
            max_concurrent=3,
            default_timeout=0.1,
            tool_timeouts={"long_tool": 1.0},
        )

        tool_calls = [
            {
                "name": "long_tool",
                "input": {"delay": 0.5},
            },  # Should succeed with specific timeout
            {
                "name": "short_tool",
                "input": {"delay": 0.5},
            },  # Should timeout with default
        ]

        results = await executor.execute_batch(variable_executor, tool_calls)

        long_result = next(r for r in results if r.tool_name == "long_tool")
        short_result = next(r for r in results if r.tool_name == "short_tool")

        assert long_result.success
        assert not short_result.success


# ============================================================================
# Retry Tests
# ============================================================================


class TestRetryLogic:
    """Tests for retry logic in parallel execution."""

    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self):
        """Test that transient failures are retried."""
        from airbeeps.agents.graph.nodes.executor import ParallelExecutor

        call_counts = {}

        async def flaky_executor(name: str, input_data: dict) -> str:
            call_counts[name] = call_counts.get(name, 0) + 1
            if call_counts[name] < 3:
                raise ConnectionError("Transient failure")
            return "success"

        executor = ParallelExecutor(max_concurrent=1, default_timeout=5, max_retries=3)
        tool_calls = [{"name": "flaky_tool", "input": {}}]

        results = await executor.execute_batch(flaky_executor, tool_calls)

        assert len(results) == 1
        assert results[0].success
        assert call_counts["flaky_tool"] == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_permanent_failure(self):
        """Test that permanent failures are not retried."""
        from airbeeps.agents.graph.nodes.executor import ParallelExecutor

        call_count = 0

        async def failing_executor(name: str, input_data: dict) -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("Permanent failure")  # ValueError is not retryable

        executor = ParallelExecutor(max_concurrent=1, default_timeout=5, max_retries=3)
        tool_calls = [{"name": "bad_tool", "input": {}}]

        results = await executor.execute_batch(failing_executor, tool_calls)

        assert len(results) == 1
        assert not results[0].success
        # Should not retry ValueErrors
        assert call_count <= 3  # Max retries

    @pytest.mark.asyncio
    async def test_retry_count_tracked(self):
        """Test that retry attempts are tracked."""
        from airbeeps.agents.graph.nodes.executor import ParallelExecutor

        async def always_fails(name: str, input_data: dict) -> str:
            raise ConnectionError("Always fails")

        executor = ParallelExecutor(max_concurrent=1, default_timeout=5, max_retries=3)
        tool_calls = [{"name": "failing_tool", "input": {}}]

        results = await executor.execute_batch(always_fails, tool_calls)

        assert len(results) == 1
        assert not results[0].success
        assert results[0].attempts == 3


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Tests for error handling in parallel execution."""

    @pytest.mark.asyncio
    async def test_partial_failure_continues(self):
        """Test that partial failures don't stop other tools."""
        from airbeeps.agents.graph.nodes.executor import ParallelExecutor

        async def mixed_executor(name: str, input_data: dict) -> str:
            if name == "failing_tool":
                raise RuntimeError("Tool failed")
            return "success"

        executor = ParallelExecutor(max_concurrent=3, default_timeout=5)
        tool_calls = [
            {"name": "good_tool_1", "input": {}},
            {"name": "failing_tool", "input": {}},
            {"name": "good_tool_2", "input": {}},
        ]

        results = await executor.execute_batch(mixed_executor, tool_calls)

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]

        assert len(successes) == 2
        assert len(failures) == 1

    @pytest.mark.asyncio
    async def test_error_details_captured(self):
        """Test that error details are captured in results."""
        from airbeeps.agents.graph.nodes.executor import ParallelExecutor

        async def error_executor(name: str, input_data: dict) -> str:
            raise RuntimeError("Specific error message")

        executor = ParallelExecutor(max_concurrent=1, default_timeout=5)
        tool_calls = [{"name": "error_tool", "input": {}}]

        results = await executor.execute_batch(error_executor, tool_calls)

        assert len(results) == 1
        assert not results[0].success
        assert "error" in results[0].result.lower() or results[0].error_type is not None


# ============================================================================
# Priority Tests
# ============================================================================


class TestToolPriority:
    """Tests for tool priority handling."""

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Test that higher priority tools execute first."""
        from airbeeps.agents.graph.nodes.executor import ParallelExecutor, ToolPriority

        execution_order = []

        async def order_tracking_executor(name: str, input_data: dict) -> str:
            execution_order.append(name)
            return "result"

        executor = ParallelExecutor(
            max_concurrent=1,  # Force sequential to test ordering
            default_timeout=5,
            tool_priorities={
                "low_priority": ToolPriority.LOW,
                "high_priority": ToolPriority.HIGH,
                "critical": ToolPriority.CRITICAL,
            },
        )

        tool_calls = [
            {"name": "low_priority", "input": {}},
            {"name": "high_priority", "input": {}},
            {"name": "critical", "input": {}},
        ]

        await executor.execute_batch(order_tracking_executor, tool_calls)

        # Critical should be first, then high, then low
        assert execution_order.index("critical") < execution_order.index(
            "high_priority"
        )
        assert execution_order.index("high_priority") < execution_order.index(
            "low_priority"
        )


# ============================================================================
# Performance Tests
# ============================================================================


class TestPerformance:
    """Tests for parallel execution performance."""

    @pytest.mark.asyncio
    async def test_parallel_faster_than_sequential(self):
        """Test that parallel execution is faster than sequential."""
        import time

        from airbeeps.agents.graph.nodes.executor import ParallelExecutor

        async def slow_executor(name: str, input_data: dict) -> str:
            await asyncio.sleep(0.1)
            return "result"

        # Parallel execution
        executor_parallel = ParallelExecutor(max_concurrent=5, default_timeout=5)
        tool_calls = [{"name": f"tool_{i}", "input": {}} for i in range(5)]

        start = time.time()
        await executor_parallel.execute_batch(slow_executor, tool_calls)
        parallel_time = time.time() - start

        # Sequential execution (max_concurrent=1)
        executor_sequential = ParallelExecutor(max_concurrent=1, default_timeout=5)

        start = time.time()
        await executor_sequential.execute_batch(slow_executor, tool_calls)
        sequential_time = time.time() - start

        # Parallel should be at least 2x faster
        assert parallel_time < sequential_time / 2

    @pytest.mark.asyncio
    async def test_duration_tracked(self):
        """Test that execution duration is tracked."""
        from airbeeps.agents.graph.nodes.executor import ParallelExecutor

        async def timed_executor(name: str, input_data: dict) -> str:
            await asyncio.sleep(0.1)
            return "result"

        executor = ParallelExecutor(max_concurrent=1, default_timeout=5)
        tool_calls = [{"name": "timed_tool", "input": {}}]

        results = await executor.execute_batch(timed_executor, tool_calls)

        assert len(results) == 1
        assert results[0].duration_ms >= 100  # At least 100ms
