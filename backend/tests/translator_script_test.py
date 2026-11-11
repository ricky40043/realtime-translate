"""中日夾雜判斷：日文的漢字要算日文，不能因為漢字比假名多就被當成中文"""
import os
import sys
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-secret")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.translator import _dominant_side, _split_mixed  # noqa: E402

A = ["zh-TW", "en"]   # 使用者截圖的設定：繁中 + English ⇄ 日本語
B = ["ja"]


def test_kanji_heavy_japanese_is_not_chinese():
    # 6 個漢字 + 5 個假名：以前被判成中文（A），日文翻成日文，看起來沒翻
    assert _dominant_side("私は日本語は大好きです。", A, B) in (None, 1)
    assert _split_mixed("私は日本語は大好きです。", A, B) is None
    assert _dominant_side("今日は天気がいいので散歩に行きます", A, B) in (None, 1)
    assert _dominant_side("お願いします", A, B) in (None, 1)


def test_chinese_stays_chinese():
    assert _dominant_side("現在我要說話", A, B) in (None, 0)
    assert _dominant_side("我覺得這個很好", A, B) in (None, 0)
    # 中文句子順口夾一個日文單字，仍然是中文
    assert _dominant_side("我很喜歡ラーメン這種食物而且每天都吃", A, B) == 0


def test_two_speakers_in_one_chunk_still_split():
    parts = _split_mixed("我覺得這個很好。ありがとうございます。", A, B)
    assert parts == [("我覺得這個很好。", 0), ("ありがとうございます。", 1)]
    parts = _split_mixed("私は日本語は大好きです。我也很喜歡這個地方。", A, B)
    assert [side for _, side in parts] == [1, 0]


def test_without_chinese_side_kanji_goes_to_japanese():
    assert _dominant_side("私は日本語が好きです I like it", ["en"], ["ja"]) == 1
    parts = _split_mixed("Thank you very much. 私は日本語が好きです。", ["en"], ["ja"])
    assert [side for _, side in parts] == [0, 1]
