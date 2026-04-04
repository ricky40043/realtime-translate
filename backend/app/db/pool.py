import asyncpg
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 全域資料庫連線池
_pool: Optional[asyncpg.Pool] = None

async def init_db() -> None:
    """初始化資料庫連線池"""
    global _pool
    if _pool is None:
        database_url = os.getenv("POSTGRES_URL", "")
        print(f"[DB] POSTGRES_URL starts with: {database_url[:50]}")
        if not database_url:
            print("[DB] ERROR: POSTGRES_URL is not set!")
            raise RuntimeError("POSTGRES_URL environment variable is not set")
        try:
            _pool = await asyncpg.create_pool(
                database_url,
                ssl='require',
                min_size=1,
                max_size=5,
                command_timeout=60
            )
            print("[DB] Pool created successfully!")
        except Exception as e:
            print(f"[DB] FAILED to create pool: {type(e).__name__}: {e}")
            raise

async def get_db_pool() -> asyncpg.Pool:
    """取得資料庫連線池"""
    if _pool is None:
        await init_db()
    return _pool

async def close_db() -> None:
    """關閉資料庫連線池"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None