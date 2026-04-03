"""
資料庫 migration 腳本 - 在後端啟動前執行以確保 schema 存在。
所有語句使用 IF NOT EXISTS，可安全重複執行。
"""
import asyncio
import asyncpg
import os

INIT_SQL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS app_user (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  display_name TEXT NOT NULL,
  preferred_lang TEXT NOT NULL,
  input_lang TEXT DEFAULT '',
  output_lang TEXT DEFAULT 'zh-TW',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS room (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  default_board_lang TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS room_lang_override (
  room_id UUID REFERENCES room(id) ON DELETE CASCADE,
  speaker_id UUID REFERENCES app_user(id) ON DELETE CASCADE,
  target_lang TEXT NOT NULL,
  PRIMARY KEY(room_id, speaker_id)
);

CREATE TABLE IF NOT EXISTS message (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  room_id UUID REFERENCES room(id) ON DELETE CASCADE,
  speaker_id UUID REFERENCES app_user(id) ON DELETE SET NULL,
  source_lang TEXT,
  text TEXT NOT NULL,
  is_final BOOLEAN NOT NULL DEFAULT TRUE,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS message_translation (
  message_id UUID REFERENCES message(id) ON DELETE CASCADE,
  target_lang TEXT NOT NULL,
  text TEXT NOT NULL,
  latency_ms INTEGER,
  quality REAL,
  PRIMARY KEY(message_id, target_lang)
);

CREATE INDEX IF NOT EXISTS idx_message_room_id ON message(room_id);
CREATE INDEX IF NOT EXISTS idx_message_created_at ON message(created_at);
CREATE INDEX IF NOT EXISTS idx_message_translation_message_id ON message_translation(message_id);
"""


async def run_migrations() -> None:
    database_url = os.getenv("POSTGRES_URL", "postgres://user:pass@localhost:5432/rt")
    print("Running database migrations...")
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(INIT_SQL)
        print("Migrations completed successfully.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migrations())
