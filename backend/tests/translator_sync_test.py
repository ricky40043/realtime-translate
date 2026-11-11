import os

os.environ.setdefault("JWT_SECRET", "test-secret")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from app.ws import translator_sync

app = FastAPI()
app.include_router(translator_sync.router)


def token():
    return jwt.encode({"sub": "u1"}, os.environ["JWT_SECRET"], algorithm="HS256")


def url(room, cid):
    return f"/ws/translator-sync/{room}?token={token()}&cid={cid}"


def entry(key, text, t=1.0, final=False):
    return {"key": key, "t": t, "sourceLang": "zh-TW", "targetLang": "en", "ended": final,
            "pieces": [{"transcript": text, "translation": text + "!", "final": final}]}


def test_sync_between_devices_and_late_join():
    client = TestClient(app)
    with client.websocket_connect(url("ROOM1234", "phone")) as phone:
        snap = phone.receive_json()
        assert snap["type"] == "snapshot" and snap["entries"] == [] and snap["peers"] == 1
        assert snap["now"] > 1e12

        with client.websocket_connect(url("ROOM1234", "pc")) as pc:
            assert pc.receive_json()["peers"] == 2
            assert phone.receive_json() == {"type": "peers", "peers": 2}

            phone.send_json({"type": "langs", "langA": ["zh-TW"], "langB": ["en"]})
            assert pc.receive_json()["langA"] == ["zh-TW"]

            phone.send_json({"type": "entries", "upserts": [entry("phone:1", "你好")], "removed": []})
            got = pc.receive_json()
            assert got["type"] == "entries" and got["from"] == "phone"
            assert got["upserts"][0]["pieces"][0]["transcript"] == "你好"

            # 同一句越講越長：用同一個 key 更新
            phone.send_json({"type": "entries", "upserts": [entry("phone:1", "你好嗎", final=True)], "removed": []})
            assert pc.receive_json()["upserts"][0]["pieces"][0]["transcript"] == "你好嗎"

        # pc 離開；晚加入的裝置拿到完整畫面
        assert phone.receive_json() == {"type": "peers", "peers": 1}
        with client.websocket_connect(url("ROOM1234", "tablet")) as tablet:
            snap = tablet.receive_json()
            assert [e["pieces"][0]["transcript"] for e in snap["entries"]] == ["你好嗎"]
            assert snap["langs"]["langB"] == ["en"]


def test_removed_reset_and_isolation():
    client = TestClient(app)
    with client.websocket_connect(url("ROOM_A", "a")) as a, client.websocket_connect(url("ROOM_B", "b")) as b:
        a.receive_json(); b.receive_json()
        a.send_json({"type": "entries", "upserts": [entry("a:1", "x"), entry("a:2", "y", t=2.0)], "removed": []})
        a.send_json({"type": "entries", "upserts": [], "removed": ["a:1"]})
        a.send_json({"type": "ping"})
        assert a.receive_json() == {"type": "pong"}   # 自己不會收到自己的更新
    with client.websocket_connect(url("ROOM_A", "c")) as c:
        assert [e["key"] for e in c.receive_json()["entries"]] == ["a:2"]
        c.send_json({"type": "reset"})
    with client.websocket_connect(url("ROOM_A", "d")) as d:
        assert d.receive_json()["entries"] == []
    with client.websocket_connect(url("ROOM_B", "e")) as e:
        assert e.receive_json()["entries"] == []     # 別的房間不受影響


def test_rejects_bad_token_room_and_junk():
    client = TestClient(app)
    for path in ("/ws/translator-sync/ROOM1234?token=bad&cid=x", f"/ws/translator-sync/a?token={token()}&cid=x"):
        try:
            with client.websocket_connect(path):
                raise AssertionError("should be rejected")
        except Exception as exc:  # starlette 會在 close 時丟 WebSocketDisconnect
            assert "AssertionError" not in type(exc).__name__
    with client.websocket_connect(url("ROOM_J", "j")) as ws:
        ws.receive_json()
        ws.send_text("not json")
        ws.send_json({"type": "entries", "upserts": [{"key": 5}, "x", {"key": "k" * 200}], "removed": [1]})
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
