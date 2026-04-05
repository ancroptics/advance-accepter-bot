import json
import logging
import os
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

MIGRATION_SQL_PATH = os.path.join(os.path.dirname(__file__), 'migrations', '001_initial_schema.sql')

class DatabaseModels:
    """Wraps all database operations for the bot."""

    def __init__(self, pool):
        self.pool = pool

    async def run_migrations(self):
        """Run SQL migrations from file."""
        try:
            if os.path.exists(MIGRATION_SQL_PATH):
                with open(MIGRATION_SQL_PATH, 'r') as f:
                    sql = f.read()
                async with self.pool.acquire() as conn:
                    await conn.execute(sql)
                logger.info("Migrations completed successfully")
            else:
                logger.warning(f"Migration file not found: {MIGRATION_SQL_PATH}")
        except Exception as e:
            logger.error(f"Migration error: {e}")
            raise

    # --- User operations ---

    async def upsert_user(self, user_id: int, username: str = None, first_name: str = None):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO users (user_id, username, first_name)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO UPDATE
                SET username = $2, first_name = $3
            ''', user_id, username, first_name)

    async def get_user(self, user_id: int):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
            return dict(row) if row else None

    async def get_all_users(self):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('SELECT * FROM users ORDER BY created_at DESC')
            return [dict(r) for r in rows]

    async def ban_user(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute('UPDATE users SET is_banned = TRUE WHERE user_id = $1', user_id)

    async def unban_user(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute('UPDATE users SET is_banned = FALSE WHERE user_id = $1', user_id)

    async def is_banned(self, user_id: int):
        async with self.pool.acquire() as conn:
            return await conn.fetchval('SELECT is_banned FROM users WHERE user_id = $1', user_id)

    async def check_approval_limit(self, user_id: int):
        """Check if user has reached monthly approval limit. Returns (remaining, limit)."""
        from config import TIER_LIMITS
        user = await self.get_user(user_id)
        if not user:
            return 0, 0

        tier = user.get('tier', 'free')
        limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
        max_approvals = limits['monthly_approvals']

        if max_approvals == -1:
            return 999999, -1

        # Reset monthly count if needed
        today = date.today()
        reset_date = user.get('approval_reset_date')
        if not reset_date or reset_date.month != today.month:
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    UPDATE users SET monthly_approvals = 0, approval_reset_date = $1
                    WHERE user_id = $2
                ''', today, user_id)
            return max_approvals, max_approvals

        used = user.get('monthly_approvals', 0)
        return max(0, max_approvals - used), max_approvals

    async def increment_approvals(self, user_id: int, count: int = 1):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE users SET monthly_approvals = monthly_approvals + $1
                WHERE user_id = $2
            ''', count, user_id)

    # --- Channel operations ---

    async def add_channel(self, chat_id: int, chat_title: str, owner_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO channels (chat_id, chat_title, owner_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (chat_id) DO UPDATE
                SET chat_title = $2
            ''', chat_id, chat_title, owner_id)

    async def remove_channel(self, chat_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute('DELETE FROM channels WHERE chat_id = $1', chat_id)

    async def get_channel(self, chat_id: int):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM channels WHERE chat_id = $1', chat_id)
            return dict(row) if row else None

    async def get_user_channels(self, owner_id: int):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('SELECT * FROM channels WHERE owner_id = $1 ORDER BY created_at', owner_id)
            return [dict(r) for r in rows]

    async def get_all_channels(self):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('SELECT * FROM channels ORDER BY created_at')
            return [dict(r) for r in rows]

    async def update_channel(self, chat_id: int, **kwargs):
        if not kwargs:
            return
        set_clauses = []
        values = []
        for i, (k, v) in enumerate(kwargs.items(), 1):
            set_clauses.append(f"{k} = ${i}")
            values.append(v)
        values.append(chat_id)
        query = f"UPDATE channels SET {'%, '.join(set_clauses)} WHERE chat_id = ${len(values)}"
        async with self.pool.acquire() as conn:
            await conn.execute(query, *values)

    async def get_channel_count_for_user(self, owner_id: int):
        async with self.pool.acquire() as conn:
            return await conn.fetchval('SELECT COUNT(*) FROM channels WHERE owner_id = $1', owner_id)

    async def clone_channel_settings(self, src_chat_id: int, dst_chat_id: int):
        """Clone settings from one channel to another."""
        src = await self.get_channel(src_chat_id)
        if not src:
            return False
        await self.update_channel(
            dst_chat_id,
            approve_mode=src['approve_mode'],
            drip_rate=src['drip_rate'],
            drip_interval=src['drip_interval'],
            dm_enabled=src['dm_enabled'],
            dm_template=src['dm_template']
        )
        return True

    # --- Join request operations ---

    async def add_join_request(self, chat_id: int, user_id: int, username: str = None, first_name: str = None):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO join_requests (chat_id, user_id, username, first_name)
                VALUES ($1, $2, $3, $4)
            ''', chat_id, user_id, username, first_name)
            # Update pending count
            await conn.execute('''
                UPDATE channels SET pending_requests = pending_requests + 1
                WHERE chat_id = $1
            ''', chat_id)

    async def approve_request(self, chat_id: int, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE join_requests SET status = 'approved', processed_at = NOW()
                WHERE chat_id = $1 AND user_id = $2 AND status = 'pending'
            ''', chat_id, user_id)
            await conn.execute('''
                UPDATE channels SET
                    pending_requests = GREATEST(pending_requests - 1, 0),
                    total_approved = total_approved + 1
                WHERE chat_id = $1
            ''', chat_id)
            # Update daily stats
            await conn.execute('''
                INSERT INTO daily_stats (chat_id, approved) VALUES ($1, 1)
                ON CONFLICT (chat_id, stat_date) DO UPDATE SET approved = daily_stats.approved + 1
            ''', chat_id)

    async def decline_request(self, chat_id: int, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE join_requests SET status = 'declined', processed_at = NOW()
                WHERE chat_id = $1 AND user_id = $2 AND status = 'pending'
            ''', chat_id, user_id)
            await conn.execute('''
                UPDATE channels SET
                    pending_requests = GREATEST(pending_requests - 1, 0),
                    total_declined = total_declined + 1
                WHERE chat_id = $1
            ''', chat_id)
            await conn.execute('''
                INSERT INTO daily_stats (chat_id, declined) VALUES ($1, 1)
                ON CONFLICT (chat_id, stat_date) DO UPDATE SET declined = daily_stats.declined + 1
            ''', chat_id)

    async def approve_batch_requests(self, chat_id: int, user_ids: list):
        """Batch approve multiple requests."""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE join_requests SET status = 'approved', processed_at = NOW()
                WHERE chat_id = $1 AND user_id = ANY($2::bigint[]) AND status = 'pending'
            ''', chat_id, user_ids)
            count = len(user_ids)
            await conn.execute('''
                UPDATE channels SET
                    pending_requests = GREATEST(pending_requests - $1, 0),
                    total_approved = total_approved + $1
                WHERE chat_id = $2
            ''', count, chat_id)
            await conn.execute('''
                INSERT INTO daily_stats (chat_id, approved) VALUES ($1, $2)
                ON CONFLICT (chat_id, stat_date) DO UPDATE SET approved = daily_stats.approved + $2
            ''', chat_id, count)
            return count

    async def get_pending_requests(self, chat_id: int, limit: int = 50):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT * FROM join_requests
                WHERE chat_id = $1 AND status = 'pending'
                ORDER BY created_at ASC
                LIMIT $2
            ''', chat_id, limit)
            return [dict(r) for r in rows]

    async def get_pending_count(self, chat_id: int):
        async with self.pool.acquire() as conn:
            return await conn.fetchval('''
                SELECT COUNT(*) FROM join_requests
                WHERE chat_id = $1 AND status = 'pending'
            ''', chat_id)

    async def get_approved_users(self, chat_id: int):
        """Get all approved user IDs for a channel."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT DISTINCT user_id FROM join_requests
                WHERE chat_id = $1 AND status = 'approved'
            ''', chat_id)
            return [r['user_id'] for r in rows]

    async def export_requests_csv(self, chat_id: int):
        """Export join requests as CSV string."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT user_id, username, first_name, status, created_at, processed_at
                FROM join_requests WHERE chat_id = $1
                ORDER BY created_at DESC
            ''', chat_id)

        if not rows:
            return None

        lines = ['user_id,username,first_name,status,created_at,processed_at']
        for r in rows:
            lines.append(f"{r['user_id']},{r.get('username', '')},{r.get('first_name', '')},{r['status']},{r['created_at']},{r.get('processed_at', '')}")
        return '\n'.join(lines)

    # --- Stats ---

    async def get_daily_stats(self, chat_id: int, days: int = 7):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT * FROM daily_stats
                WHERE chat_id = $1 AND stat_date >= CURRENT_DATE - $2
                ORDER BY stat_date
            ''', chat_id, timedelta(days=days))
            return [dict(r) for r in rows]

    async def get_global_stats(self):
        """Get global stats for admin panel."""
        async with self.pool.acquire() as conn:
            stats = {}
            stats['total_users'] = await conn.fetchval('SELECT COUNT(*) FROM users')
            stats['total_channels'] = await conn.fetchval('SELECT COUNT(*) FROM channels')
            stats['total_requests'] = await conn.fetchval('SELECT COUNT(*) FROM join_requests')
            stats['total_approved'] = await conn.fetchval("SELECT COUNT(*) FROM join_requests WHERE status = 'approved'")
            stats['total_pending'] = await conn.fetchval("SELECT COUNT(*) FROM join_requests WHERE status = 'pending'")
            stats['today_approved'] = await conn.fetchval("SELECT COUNT(*) FROM join_requests WHERE status = 'approved' AND processed_at::date = CURRENT_DATE")
            return stats

    async def close(self):
        if self.pool:
            await self.pool.close()
            logger.info('Database connection closed')
