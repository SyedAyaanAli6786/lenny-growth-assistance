import asyncio

import pytest

from app.agent.orchestrator import _stoppable


async def _never_ending_agen():
    """Simulates a provider stream still waiting on its next token when the
    consumer gets cancelled — the same shape as a real client disconnect
    mid-generation: the underlying HTTP stream hasn't produced anything new
    yet, so agen.__anext__() is suspended, not finished. A real async
    generator (not a hand-rolled stand-in) matters here: CPython's
    "aclose(): asynchronous generator is already running" guard only exists
    on actual async generator objects.
    """
    while True:
        await asyncio.sleep(3600)
        yield "unreachable"


@pytest.mark.asyncio
async def test_stoppable_cleans_up_pending_anext_when_consumer_is_cancelled():
    """Regression test for a bug only found via live testing: Starlette
    cancels a StreamingResponse's body-generator task when it detects the
    client disconnected. That cancellation lands inside _stoppable's
    `await asyncio.wait({next_task, stop_task}, ...)` — but asyncio.wait()
    does not cancel its member futures just because it was itself cancelled,
    so next_task (wrapping agen.__anext__()) was left running. The caller's
    own `finally: await agen.aclose()` (see respond_stream/_generate_streamed)
    then raised "RuntimeError: aclose(): asynchronous generator is already
    running", which killed the whole generation on any real disconnect —
    the opposite of the disconnect-safety streaming was built to provide.
    _stoppable's cleanup must cancel next_task itself before the
    CancelledError propagates further.
    """
    agen = _never_ending_agen()
    started = asyncio.Event()

    async def consume() -> None:
        started.set()
        async for _ in _stoppable(agen, asyncio.Event()):
            pass

    task = asyncio.ensure_future(consume())
    await started.wait()
    await asyncio.sleep(0)  # let the loop reach the anext() await point
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    # Must not raise "already running" — _stoppable must have cancelled the
    # in-flight anext() before the cancellation propagated out of it.
    await agen.aclose()
