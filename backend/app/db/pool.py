import asyncpg
import os
from typing import Optional

# 全域資料庫連線池
_pool: Optional[asyncpg.Pool] = None

async def init_db() -> None:
    """初始化資料庫連線池"""
    global _pool
    if _pool is None:
        database_url = os.getenv("POSTGRES_URL", "postgres://user:pass@localhost:5432/rt")
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=1,
            max_size=10,
            command_timeout=60
        )

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