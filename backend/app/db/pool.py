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
        database_url = os.getenv("POSTGRES_URL", "postgres://user:pass@localhost:5432/rt")
        logger.info(f"Connecting to DB: {database_url[:40]}...")
        try:
            _pool = await asyncpg.create_pool(
                database_url,
                ssl='require',       # Neon 需要 SSL
                min_size=1,
                max_size=5,
                command_timeout=60
            )
            logger.info("DB pool created successfully.")
        except Exception as e:
            logger.error(f"Failed to create DB pool: {e}")
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