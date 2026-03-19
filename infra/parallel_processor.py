"""Parallel Processing Module.

Provides utilities for parallel execution of tasks and batch processing.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class TaskResult(Generic[R]):
    """Result of a parallel task execution."""

    task_id: int
    success: bool
    result: R | None = None
    error: str | None = None
    duration_seconds: float = 0.0


@dataclass
class BatchResult(Generic[R]):
    """Result of a batch execution."""

    total_tasks: int
    successful: int
    failed: int
    results: list[TaskResult[R]] = field(default_factory=list)
    total_duration_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.successful / self.total_tasks if self.total_tasks > 0 else 0.0


class ParallelExecutor:
    """Execute tasks in parallel using thread pools."""

    def __init__(
        self,
        max_workers: int | None = None,
        timeout_per_task: float = 60.0,
    ) -> None:
        self.max_workers = max_workers or min(32, (os.cpu_count() or 1) + 4)
        self.timeout_per_task = timeout_per_task

    def map(
        self,
        func: Callable[[T], R],
        items: list[T],
        show_progress: bool = False,
    ) -> BatchResult[R]:
        """Execute function on all items in parallel."""
        if not items:
            return BatchResult(total_tasks=0, successful=0, failed=0)

        start_time = time.monotonic()
        results: list[TaskResult[R]] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_id = {
                executor.submit(self._execute_task, func, item, i): i
                for i, item in enumerate(items)
            }

            for future in as_completed(
                future_to_id, timeout=self.timeout_per_task * len(items),
            ):
                task_id = future_to_id[future]
                try:
                    result = future.result(timeout=self.timeout_per_task)
                    results.append(result)
                except Exception as e:
                    results.append(TaskResult(task_id=task_id, success=False, error=str(e)))

        total_duration = time.monotonic() - start_time
        successful = sum(1 for r in results if r.success)

        return BatchResult(
            total_tasks=len(items),
            successful=successful,
            failed=len(results) - successful,
            results=sorted(results, key=lambda r: r.task_id),
            total_duration_seconds=total_duration,
        )

    def _execute_task(self, func: Callable[[T], R], item: T, task_id: int) -> TaskResult[R]:
        start = time.monotonic()
        try:
            result = func(item)
            duration = time.monotonic() - start
            return TaskResult(
                task_id=task_id, success=True, result=result, duration_seconds=duration,
            )
        except Exception as e:
            duration = time.monotonic() - start
            return TaskResult(
                task_id=task_id, success=False, error=str(e), duration_seconds=duration,
            )


def parallel_map(func: Callable[[T], R], items: list[T], max_workers: int = 4) -> list[R]:
    """Simple parallel map function."""
    executor = ParallelExecutor(max_workers=max_workers)
    batch_result = executor.map(func, items, show_progress=False)
    return [r.result for r in batch_result.results if r.success and r.result is not None]


def run_parallel(tasks: list[Callable[[], R]], max_workers: int = 4) -> BatchResult[R]:
    """Run multiple callables in parallel."""
    executor = ParallelExecutor(max_workers=max_workers)

    def execute_callable(task: Callable[[], R]) -> R:
        return task()

    return executor.map(execute_callable, tasks)
