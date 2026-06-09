import asyncio
import json
from typing import AsyncGenerator

# In-memory store of active SSE queues keyed by job_id
_queues: dict[str, asyncio.Queue] = {}


def get_or_create_queue(job_id: str) -> asyncio.Queue:
    if job_id not in _queues:
        _queues[job_id] = asyncio.Queue()
    return _queues[job_id]


async def emit(job_id: str, payload: dict):
    queue = get_or_create_queue(job_id)
    print(f"[SSE-EMIT] putting to queue job={job_id[:8]} type={payload.get('type')}, qsize={queue.qsize()}")
    await queue.put(payload)


async def event_stream(job_id: str) -> AsyncGenerator[str, None]:
    queue = get_or_create_queue(job_id)
    print(f"[SSE] event_stream OPEN for job {job_id}")
    while True:
        try:
            payload = await asyncio.wait_for(queue.get(), timeout=30)
            print(f"[SSE] emitting to frontend: type={payload.get('type')}")
            yield f"data: {json.dumps(payload)}\n\n"
            if payload.get("type") in ("complete", "error"):
                print(f"[SSE] event_stream CLOSED (complete/error)")
                break
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'ping'})}\n\n"