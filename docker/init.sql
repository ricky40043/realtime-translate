-- 啟用 UUID 擴充功能
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 使用者表
CREATE TABLE app_user (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  display_name TEXT NOT NULL,
  preferred_lang TEXT NOT NULL,
  input_lang TEXT DEFAULT '',
  output_lang TEXT DEFAULT 'zh-TW',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 房間表
CREATE TABLE room (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  default_board_lang TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 房間語言覆寫表
CREATE TABLE room_lang_override (
  room_id UUID REFERENCES room(id) ON DELETE CASCADE,
  speaker_id UUID REFERENCES app_user(id) ON DELETE CASCADE,
  target_lang TEXT NOT NULL,
  PRIMARY KEY(room_id, speaker_id)
);

-- 訊息表
CREATE TABLE message (
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

-- 訊息翻譯表
CREATE TABLE message_translation (
  message_id UUID REFERENCES message(id) ON DELETE CASCADE,
  target_lang TEXT NOT NULL,
  text TEXT NOT NULL,
  latency_ms INTEGER,
  quality REAL,
  PRIMARY KEY(message_id, target_lang)
);

-- 建立索引以提升查詢效能
CREATE INDEX idx_message_room_id ON message(room_id);
CREATE INDEX idx_message_created_at ON message(created_at);
CREATE INDEX idx_message_translation_message_id ON message_translation(message_id);