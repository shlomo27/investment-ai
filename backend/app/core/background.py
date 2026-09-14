"""Fire-and-forget background tasks that actually survive.

asyncio.create_task() returns a task the event loop holds only a WEAK
reference to. If nothing else keeps a reference, the garbage collector is
free to collect it mid-run — the coroutine simply stops partway, with no
exception, no log line, and no indication that anything was ever started.

This is the bug that had a beta measurement stop halfway through the
universe. Route every detached task through detach().
"""
import asyncio

# Strong references to in-flight tasks, dropped automatically on completion.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def detach(coro) -> asyncio.Task:
    """Start a background task and keep it alive until it finishes."""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


def pending_count() -> int:
    """How many detached tasks are still running — for health endpoints."""
    return len(_BACKGROUND_TASKS)
