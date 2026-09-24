"""
PostgreSQL async client for OSS Work memory.
Handles: user profiles, interactions, skills, model usage, feedback.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import asyncpg


@dataclass
class PGConfig:
    url: str = ""
    min_connections: int = 5
    max_connections: int = 20
    timeout: float = 30.0


class PostgreSQLClient:

    def __init__(self, config: PGConfig | None = None) -> None:
        self.config = config or PGConfig()
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if not self.config.url:
            raise ValueError("PostgreSQL URL not configured")
        self._pool = await asyncpg.create_pool(
            self.config.url,
            min_size=self.config.min_connections,
            max_size=self.config.max_connections,
            timeout=self.config.timeout,
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    @property
    def is_connected(self) -> bool:
        return self._pool is not None

    # ── User Operations ────────────────────────────────────────

    async def create_user(self, telegram_chat_id: str, username: str = "",
                          first_name: str = "", language: str = "ar") -> str | None:
        if not self._pool:
            raise RuntimeError("Not connected")
        row = await self._pool.fetchrow("""
            INSERT INTO users (telegram_chat_id, username, first_name, language_preference)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (telegram_chat_id) DO NOTHING
            RETURNING id
        """, telegram_chat_id, username, first_name, language)
        return str(row["id"]) if row else None

    async def get_user_by_chat_id(self, telegram_chat_id: str) -> dict[str, Any] | None:
        if not self._pool:
            raise RuntimeError("Not connected")
        row = await self._pool.fetchrow("""
            SELECT id, telegram_chat_id, username, first_name, language_preference,
                   subscription_tier, total_tasks, created_at, last_active
            FROM users WHERE telegram_chat_id = $1
        """, telegram_chat_id)
        if not row:
            return None
        return dict(row)

    async def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        if not self._pool:
            raise RuntimeError("Not connected")
        row = await self._pool.fetchrow("""
            SELECT id, telegram_chat_id, username, first_name, language_preference,
                   subscription_tier, total_tasks, created_at, last_active
            FROM users WHERE id = $1
        """, user_id)
        if not row:
            return None
        return dict(row)

    async def update_user_stats(self, user_id: str, tasks_completed: int = 0,
                                tokens_used: int = 0) -> None:
        if not self._pool:
            raise RuntimeError("Not connected")
        await self._pool.execute("""
            UPDATE users
            SET total_tasks = total_tasks + $2,
                total_tokens = total_tokens + $3,
                last_active = NOW()
            WHERE id = $1
        """, user_id, tasks_completed, tokens_used)

    async def update_user_last_active(self, telegram_chat_id: str) -> None:
        if not self._pool:
            raise RuntimeError("Not connected")
        await self._pool.execute("""
            UPDATE users SET last_active = NOW() WHERE telegram_chat_id = $1
        """, telegram_chat_id)

    # ── Interaction Operations ─────────────────────────────────

    async def store_interaction(self, user_id: str, task: str, result: dict,
                                agent_used: str, model_used: str = "",
                                status: str = "completed", tokens: int = 0,
                                latency_ms: int = 0, invented: bool = False,
                                completed_thought: str = "") -> str | None:
        if not self._pool:
            raise RuntimeError("Not connected")
        row = await self._pool.fetchrow("""
            INSERT INTO interactions (user_id, task, result, agent_used, model_used,
                                     status, tokens_used, latency_ms, invented,
                                     completed_thought, timestamp)
            VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8, $9, $10, NOW())
            RETURNING id
        """, user_id, task, result, agent_used, model_used, status,
            tokens, latency_ms, invented, completed_thought)
        return str(row["id"]) if row else None

    async def get_user_interactions(self, user_id: str, limit: int = 50,
                                   offset: int = 0) -> list[dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Not connected")
        rows = await self._pool.fetch("""
            SELECT id, task, result, agent_used, model_used, status,
                   tokens_used, latency_ms, invented, timestamp
            FROM interactions
            WHERE user_id = $1
            ORDER BY timestamp DESC
            LIMIT $2 OFFSET $3
        """, user_id, limit, offset)
        return [dict(r) for r in rows]

    async def get_recent_interactions(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return await self.get_user_interactions(user_id, limit)

    async def get_interaction_count(self, user_id: str) -> int:
        if not self._pool:
            raise RuntimeError("Not connected")
        row = await self._pool.fetchval("""
            SELECT COUNT(*) FROM interactions WHERE user_id = $1
        """, user_id)
        return row or 0

    # ── Profile Operations ─────────────────────────────────────

    async def get_or_create_profile(self, user_id: str) -> dict[str, Any]:
        if not self._pool:
            raise RuntimeError("Not connected")
        row = await self._pool.fetchrow("""
            SELECT * FROM user_profiles WHERE user_id = $1
        """, user_id)
        if row:
            return dict(row)

        # Create default profile
        await self._pool.execute("""
            INSERT INTO user_profiles (user_id)
            VALUES ($1)
        """, user_id)
        return await self.get_or_create_profile(user_id)

    async def update_profile(self, user_id: str, **updates: Any) -> None:
        if not self._pool:
            raise RuntimeError("Not connected")
        if not updates:
            return

        fields = []
        values = []
        for key, value in updates.items():
            fields.append(f"{key} = ${len(values) + 1}")
            values.append(value)
        fields.append("updated_at = NOW()")
        values.append(user_id)

        query = f"UPDATE user_profiles SET {', '.join(fields)} WHERE user_id = ${len(values)}"
        await self._pool.execute(query, *values)

    async def increment_imagination_requests(self, user_id: str) -> None:
        if not self._pool:
            raise RuntimeError("Not connected")
        await self._pool.execute("""
            UPDATE user_profiles
            SET imagination_requests = imagination_requests + 1,
                updated_at = NOW()
            WHERE user_id = $1
        """, user_id)

    # ── Skill Operations ───────────────────────────────────────

    async def list_skills(self, active: bool = True) -> list[dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Not connected")
        rows = await self._pool.fetch("""
            SELECT * FROM skills WHERE active = $1 ORDER BY name
        """, active)
        return [dict(r) for r in rows]

    async def get_skill_by_name(self, name: str) -> dict[str, Any] | None:
        if not self._pool:
            raise RuntimeError("Not connected")
        row = await self._pool.fetchrow("""
            SELECT * FROM skills WHERE name = $1
        """, name)
        return dict(row) if row else None

    async def save_skill(self, name: str, source: str, capability: str,
                         version: str = "", description: str = "",
                         install_path: str = "", stars: int = 0,
                         repository_url: str = "") -> str | None:
        if not self._pool:
            raise RuntimeError("Not connected")
        row = await self._pool.fetchrow("""
            INSERT INTO skills (name, source, capability, version, description,
                                install_path, stars, repository_url)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (name) DO UPDATE SET
                source = EXCLUDED.source,
                capability = EXCLUDED.capability,
                version = EXCLUDED.version,
                description = EXCLUDED.description,
                install_path = EXCLUDED.install_path,
                stars = EXCLUDED.stars,
                repository_url = EXCLUDED.repository_url,
                active = TRUE
            RETURNING id
        """, name, source, capability, version, description,
            install_path, stars, repository_url)
        return str(row["id"]) if row else None

    async def mark_skill_used(self, skill_name: str) -> None:
        if not self._pool:
            raise RuntimeError("Not connected")
        await self._pool.execute("""
            UPDATE skills
            SET last_used = NOW(), usage_count = usage_count + 1
            WHERE name = $1
        """, skill_name)

    # ── Model Usage ────────────────────────────────────────────

    async def record_model_usage(self, model_id: str, user_id: str,
                                  tokens_in: int, tokens_out: int,
                                  latency_ms: int, success: bool,
                                  task_type: str = "", route: str = "",
                                  provider: str = "") -> None:
        if not self._pool:
            raise RuntimeError("Not connected")
        await self._pool.execute("""
            INSERT INTO model_usage (model_id, user_id, tokens_in, tokens_out,
                                     latency_ms, success, task_type, route, provider)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """, model_id, user_id, tokens_in, tokens_out,
            latency_ms, success, task_type, route, provider)

    async def get_model_stats(self, model_id: str, days: int = 7) -> dict[str, Any]:
        if not self._pool:
            raise RuntimeError("Not connected")
        row = await self._pool.fetchrow("""
            SELECT
                COUNT(*) AS request_count,
                SUM(tokens_in + tokens_out) AS total_tokens,
                AVG(latency_ms) AS avg_latency,
                AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) AS success_rate
            FROM model_usage
            WHERE model_id = $1
              AND timestamp >= NOW() - INTERVAL '{days} days'
        """.format(days=days), model_id)
        return dict(row) if row else {}

    # ── Feedback ───────────────────────────────────────────────

    async def submit_feedback(self, user_id: str, interaction_id: str,
                              rating: int, comment: str = "") -> str | None:
        if not self._pool:
            raise RuntimeError("Not connected")
        row = await self._pool.fetchrow("""
            INSERT INTO feedback (user_id, interaction_id, rating, comment)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """, user_id, interaction_id, rating, comment)
        return str(row["id"]) if row else None

    # ── Notifications ──────────────────────────────────────────

    async def create_notification(self, user_id: str, title: str,
                                   message: str = "", notification_type: str = "info") -> str | None:
        if not self._pool:
            raise RuntimeError("Not connected")
        row = await self._pool.fetchrow("""
            INSERT INTO notifications (user_id, title, message, type)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """, user_id, title, message, notification_type)
        return str(row["id"]) if row else None

    async def get_unread_notifications(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Not connected")
        rows = await self._pool.fetch("""
            SELECT * FROM notifications
            WHERE user_id = $1 AND read = FALSE
            ORDER BY created_at DESC
            LIMIT $2
        """, user_id, limit)
        return [dict(r) for r in rows]

    async def mark_notification_read(self, notification_id: str) -> None:
        if not self._pool:
            raise RuntimeError("Not connected")
        await self._pool.execute("""
            UPDATE notifications SET read = TRUE WHERE id = $1
        """, notification_id)

    # ── Health Check ───────────────────────────────────────────

    async def health_check(self) -> dict[str, Any]:
        if not self._pool:
            return {"status": "disconnected", "error": "Not connected"}
        try:
            await self._pool.fetchval("SELECT 1")
            return {"status": "healthy", "pool_size": self._pool.get_size()}
        except Exception as e:
            return {"status": "error", "error": str(e)}
