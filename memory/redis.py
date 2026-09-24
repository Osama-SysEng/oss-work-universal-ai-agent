"""
Redis session client for OSS Work.
Handles: session caching, rate limiting, temporary storage.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import redis


@dataclass
class RedisConfig:
    url: str = "redis://localhost:6379/0"
    prefix: str = "oss_work:"
    default_ttl: int = 3600  # 1 hour
    rate_limit_window: int = 60  # 1 minute
    rate_limit_max: int = 100  # requests per window


class RedisClient:

    def __init__(self, config: RedisConfig | None = None) -> None:
        self.config = config or RedisConfig()
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        """Connect to Redis."""
        self._client = redis.from_url(
            self.config.url,
            decode_responses=True,
        )
        # Test connection
        self._client.ping()

    async def close(self) -> None:
        """Close connection."""
        if self._client:
            self._client.close()
            self._client = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    def _key(self, *parts: str) -> str:
        """Build a Redis key with prefix."""
        return self.config.prefix + ":".join(parts)

    # ── Session Management ─────────────────────────────────────

    async def set_session(self, user_id: str, session_data: dict[str, Any],
                          ttl: int | None = None) -> None:
        """Store session data for a user."""
        if not self._client:
            raise RuntimeError("Not connected")
        key = self._key("session", user_id)
        value = json.dumps(session_data, ensure_ascii=False)
        self._client.set(key, value, ex=ttl or self.config.default_ttl)

    async def get_session(self, user_id: str) -> dict[str, Any] | None:
        """Get session data for a user."""
        if not self._client:
            raise RuntimeError("Not connected")
        key = self._key("session", user_id)
        value = self._client.get(key)
        if value:
            return json.loads(value)
        return None

    async def delete_session(self, user_id: str) -> None:
        """Delete session for a user."""
        if not self._client:
            raise RuntimeError("Not connected")
        key = self._key("session", user_id)
        self._client.delete(key)

    async def update_session_task(self, user_id: str, task: str,
                                   result: dict[str, Any]) -> None:
        """Append a task result to user's session history."""
        session = await self.get_session(user_id) or {}
        history = session.get("task_history", [])
        history.append({
            "task": task,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Keep last 100 tasks
        session["task_history"] = history[-100:]
        await self.set_session(user_id, session)

    async def get_session_history(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent task history for a user."""
        session = await self.get_session(user_id)
        if session and session.get("task_history"):
            return session["task_history"][-limit:]
        return []

    # ── Rate Limiting ──────────────────────────────────────────

    async def check_rate_limit(self, user_id: str) -> bool:
        """
        Check if user is within rate limits.
        Returns True if allowed, False if rate limited.
        Uses sliding window counter.
        """
        if not self._client:
            raise RuntimeError("Not connected")

        key = self._key("ratelimit", user_id)
        window = self.config.rate_limit_window
        max_requests = self.config.rate_limit_max

        # Use Redis INCR with EXPIRE
        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        results = pipe.execute()

        current_count = results[0]
        return current_count <= max_requests

    async def get_rate_limit_status(self, user_id: str) -> dict[str, Any]:
        """Get current rate limit status for a user."""
        if not self._client:
            raise RuntimeError("Not connected")

        key = self._key("ratelimit", user_id)
        current = self._client.get(key)
        count = int(current) if current else 0

        return {
            "user_id": user_id,
            "current_requests": count,
            "max_requests": self.config.rate_limit_max,
            "window_seconds": self.config.rate_limit_window,
            "remaining": max(0, self.config.rate_limit_max - count),
            "is_limited": count > self.config.rate_limit_max,
        }

    async def reset_rate_limit(self, user_id: str) -> None:
        """Reset rate limit for a user."""
        if not self._client:
            raise RuntimeError("Not connected")
        key = self._key("ratelimit", user_id)
        self._client.delete(key)

    # ── Temporary Storage ──────────────────────────────────────

    async def set_temp(self, key: str, value: Any, ttl: int = 300) -> None:
        """Store temporary data with TTL."""
        if not self._client:
            raise RuntimeError("Not connected")
        full_key = self._key("temp", key)
        self._client.set(full_key, json.dumps(value, ensure_ascii=False), ex=ttl)

    async def get_temp(self, key: str) -> Any | None:
        """Get temporary data."""
        if not self._client:
            raise RuntimeError("Not connected")
        full_key = self._key("temp", key)
        value = self._client.get(full_key)
        if value:
            return json.loads(value)
        return None

    async def delete_temp(self, key: str) -> None:
        """Delete temporary data."""
        if not self._client:
            raise RuntimeError("Not connected")
        full_key = self._key("temp", key)
        self._client.delete(full_key)

    # ── Task Queue (simple) ────────────────────────────────────

    async def enqueue_task(self, user_id: str, task: str,
                           priority: int = 0) -> str:
        """Add a task to the queue."""
        if not self._client:
            raise RuntimeError("Not connected")

        task_id = f"{int(time.time() * 1000)}:{user_id}"
        task_data = json.dumps({
            "task_id": task_id,
            "user_id": user_id,
            "task": task,
            "priority": priority,
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False)

        # Use sorted set with score = -priority for ordering
        key = self._key("task_queue")
        self._client.zadd(key, {task_data: -priority})

        return task_id

    async def dequeue_task(self, worker_id: str) -> dict[str, Any] | None:
        """Dequeue a task for a worker."""
        if not self._client:
            raise RuntimeError("Not connected")

        key = self._key("task_queue")
        # Get highest priority task (lowest score)
        tasks = self._client.zrange(key, 0, 0)
        if not tasks:
            return None

        task_data = tasks[0]
        task = json.loads(task_data)

        # Remove from queue
        self._client.zrem(key, task_data)

        # Mark as processing
        processing_key = self._key("task_processing", worker_id)
        self._client.set(processing_key, task_data, ex=300)

        return task

    async def get_queue_size(self) -> int:
        """Get current queue size."""
        if not self._client:
            raise RuntimeError("Not connected")
        key = self._key("task_queue")
        return self._client.zcard(key)

    # ── Counters ───────────────────────────────────────────────

    async def increment_counter(self, counter_name: str,
                                 user_id: str | None = None) -> int:
        """Increment a global or user-specific counter."""
        if not self._client:
            raise RuntimeError("Not connected")

        if user_id:
            key = self._key("counter", counter_name, user_id)
        else:
            key = self._key("counter", counter_name)

        return self._client.incr(key)

    async def get_counter(self, counter_name: str,
                          user_id: str | None = None) -> int:
        """Get counter value."""
        if not self._client:
            raise RuntimeError("Not connected")

        if user_id:
            key = self._key("counter", counter_name, user_id)
        else:
            key = self._key("counter", counter_name)

        value = self._client.get(key)
        return int(value) if value else 0

    # ── Health Check ───────────────────────────────────────────

    async def health_check(self) -> dict[str, Any]:
        try:
            if not self._client:
                return {"status": "disconnected"}
            pong = self._client.ping()
            return {"status": "healthy", "ping": pong}
        except Exception as e:
            return {"status": "error", "error": str(e)}
