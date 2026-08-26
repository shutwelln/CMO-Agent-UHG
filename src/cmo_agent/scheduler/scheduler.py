"""In-process async scheduler for periodic agent tasks."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

import structlog

logger = structlog.get_logger()

TaskFactory = Callable[[], Awaitable[Any]]


class ScheduledTask:
    """A task registered with the scheduler."""

    def __init__(
        self,
        name: str,
        coro_factory: TaskFactory,
        interval_seconds: int,
        enabled: bool = True,
        daily_at: Optional[Tuple[int, int]] = None,
        tz_offset_hours: float = 0.0,
        run_immediately: bool = False,
        every_n_days: int = 1,
    ) -> None:
        self.name = name
        self.coro_factory = coro_factory
        self.interval_seconds = interval_seconds
        self.enabled = enabled
        self.daily_at = daily_at  # (hour, minute) in the target timezone
        self.tz_offset_hours = tz_offset_hours
        self.run_immediately = run_immediately
        self.every_n_days = max(1, every_n_days)
        self._task: Optional[asyncio.Task[None]] = None
        self.last_run: Optional[datetime] = None
        self.run_count: int = 0
        self.error_count: int = 0


class AgentScheduler:
    """Manages periodic async tasks for agent operations.

    Uses asyncio tasks with sleep loops (no external cron dependency).
    Runs inside the same process as the Slack bot or web server.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, ScheduledTask] = {}
        self._running = False

    def register_task(
        self,
        name: str,
        coro_factory: TaskFactory,
        interval_seconds: int,
        enabled: bool = True,
        daily_at: Optional[Tuple[int, int]] = None,
        tz_offset_hours: float = 0.0,
        run_immediately: bool = False,
        every_n_days: int = 1,
    ) -> None:
        """Register a periodic task.

        Args:
            name: Unique task name.
            coro_factory: Async callable that takes no args and performs the work.
            interval_seconds: Seconds between runs (used as fallback if daily_at not set).
            enabled: Whether the task should run when the scheduler starts.
            daily_at: Optional (hour, minute) to run at a specific time each day.
                When set, interval_seconds is ignored and the task runs once per cycle.
            tz_offset_hours: UTC offset for daily_at (e.g. -6.0 for CST).
            run_immediately: If True, run the task once on startup before
                entering the regular schedule.
            every_n_days: Run every N days (default 1 = daily). Only applies
                when daily_at is set.
        """
        self._tasks[name] = ScheduledTask(
            name=name,
            coro_factory=coro_factory,
            interval_seconds=interval_seconds,
            enabled=enabled,
            daily_at=daily_at,
            tz_offset_hours=tz_offset_hours,
            run_immediately=run_immediately,
            every_n_days=every_n_days,
        )
        schedule_desc = f"interval={interval_seconds}s"
        if daily_at:
            sign = "+" if tz_offset_hours >= 0 else ""
            freq = "daily" if every_n_days <= 1 else f"every {every_n_days} days"
            schedule_desc = (
                f"{freq} at {daily_at[0]:02d}:{daily_at[1]:02d} UTC{sign}{tz_offset_hours}"
            )
        logger.info(
            "scheduler_task_registered",
            name=name,
            schedule=schedule_desc,
            enabled=enabled,
            run_immediately=run_immediately,
        )

    def start(self) -> None:
        """Start all enabled tasks as background asyncio tasks."""
        if self._running:
            return
        self._running = True
        for task in self._tasks.values():
            if task.enabled:
                task._task = asyncio.create_task(
                    self._run_loop(task), name=f"scheduler:{task.name}"
                )
        logger.info(
            "scheduler_started",
            tasks=[t.name for t in self._tasks.values() if t.enabled],
        )

    def stop(self) -> None:
        """Cancel all running tasks."""
        self._running = False
        for task in self._tasks.values():
            if task._task and not task._task.done():
                task._task.cancel()
                task._task = None
        logger.info("scheduler_stopped")

    async def trigger_now(self, task_name: str) -> Any:
        """Manually trigger a task immediately. Returns the task result."""
        task = self._tasks.get(task_name)
        if not task:
            raise KeyError(f"Unknown task: {task_name}")
        logger.info("scheduler_manual_trigger", task=task_name)
        return await self._execute_task(task)

    def get_status(self) -> Dict[str, Any]:
        """Get the status of all scheduled tasks."""
        return {
            "running": self._running,
            "tasks": {
                name: {
                    "enabled": t.enabled,
                    "interval_seconds": t.interval_seconds,
                    "daily_at": f"{t.daily_at[0]:02d}:{t.daily_at[1]:02d}" if t.daily_at else None,
                    "every_n_days": t.every_n_days if t.daily_at else None,
                    "last_run": t.last_run.isoformat() if t.last_run else None,
                    "run_count": t.run_count,
                    "error_count": t.error_count,
                    "active": t._task is not None and not t._task.done() if t._task else False,
                }
                for name, t in self._tasks.items()
            },
        }

    async def _run_loop(self, task: ScheduledTask) -> None:
        """Internal loop that runs a task on its schedule."""
        # Run immediately on startup if requested
        if task.run_immediately:
            await asyncio.sleep(5)  # Brief stagger
            await self._execute_task(task)

        if task.daily_at:
            await self._run_daily_loop(task)
        else:
            # Interval-based: initial stagger then repeat
            if not task.run_immediately:
                await asyncio.sleep(5)
            while self._running:
                await self._execute_task(task)
                await asyncio.sleep(task.interval_seconds)

    async def _run_daily_loop(self, task: ScheduledTask) -> None:
        """Run a task at the configured time every N days."""
        tz = timezone(timedelta(hours=task.tz_offset_hours))
        target_hour, target_minute = task.daily_at  # type: ignore[misc]
        step = timedelta(days=task.every_n_days)

        while self._running:
            now = datetime.now(tz)
            # Build today's target time
            target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            # If we already passed today's target, advance by one step
            if now >= target:
                target += step

            wait_seconds = (target - now).total_seconds()
            logger.info(
                "scheduler_daily_waiting",
                task=task.name,
                next_run=target.isoformat(),
                wait_seconds=int(wait_seconds),
            )

            await asyncio.sleep(wait_seconds)
            if self._running:
                await self._execute_task(task)

    async def _execute_task(self, task: ScheduledTask) -> Any:
        """Execute a single task with error handling."""
        try:
            logger.info("scheduler_task_running", task=task.name)
            result = await task.coro_factory()
            task.last_run = datetime.utcnow()
            task.run_count += 1
            logger.info(
                "scheduler_task_completed",
                task=task.name,
                run_count=task.run_count,
            )
            return result
        except asyncio.CancelledError:
            raise
        except Exception as e:
            task.error_count += 1
            logger.error(
                "scheduler_task_failed",
                task=task.name,
                error=str(e),
                error_count=task.error_count,
            )
            return None
