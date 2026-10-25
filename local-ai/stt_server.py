"""
本機語音辨識服務（Whisper），介面和 OpenAI / Groq 的 /v1/audio/transcriptions 相同。

- Apple Silicon Mac：用 mlx-whisper（跑在 Mac 的 GPU 上，最快）
- 其他電腦：用 faster-whisper（有 NVIDIA 顯卡就用顯卡，沒有就用 CPU）

啟動：python stt_server.py   （預設 http://127.0.0.1:9000）
環境變數：
  STT_MODELS   可選的模型，逗號分隔，第一個是預設（預設 "large-v3-turbo,large-v3"）
  STT_HOST / STT_PORT
"""

import os
import platform
import sys
import tempfile
import threading
import time

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

MODELS = [m.strip() for m in os.getenv("STT_MODELS", "large-v3-turbo,large-v3").split(",") if m.strip()]
USE_MLX = sys.platform == "darwin" and platform.machine() == "arm64"
# 用全部核心反而慢很多（實測 16 核：一句 7–15 秒；8 核：1.4 秒），而且要留給翻譯模型
CPU_THREADS = int(os.getenv("STT_THREADS", "0")) or max(4, min(8, (os.cpu_count() or 8) // 2))

# mlx 版的模型放在 mlx-community
_MLX_REPOS = {
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "small": "mlx-community/whisper-small-mlx",
}

app = FastAPI(title="Local Whisper")
_models = {}
_on_gpu = {}
_lock = threading.Lock()  # 同一時間只跑一段，避免記憶體爆掉


def _load(name: str):
    if name in _models:
        return _models[name]
    print(f"⏳ 載入 Whisper {name}（第一次要下載，可能要幾分鐘）…", flush=True)
    start = time.time()
    if USE_MLX:
        import mlx_whisper
        from huggingface_hub import snapshot_download

        repo = _MLX_REPOS.get(name, name)
        snapshot_download(repo)  # 先下載好，之後不用網路
        _models[name] = ("mlx", repo, mlx_whisper)
    else:
        from faster_whisper import WhisperModel

        model = None
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                model = WhisperModel(name, device="cuda", compute_type="float16")
                _on_gpu[name] = True
                print("   使用 NVIDIA 顯卡", flush=True)
        except Exception as e:
            print(f"   顯卡無法使用，改用 CPU：{e}", flush=True)
        if model is None:
            model = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=CPU_THREADS)
        _models[name] = ("faster", name, model)
    print(f"✅ Whisper {name} 就緒（{time.time() - start:.0f} 秒）", flush=True)
    return _models[name]


def _transcribe(name: str, path: str, language: str = None) -> dict:
    kind, repo, model = _load(name)
    if kind == "mlx":
        result = model.transcribe(path, path_or_hf_repo=repo, language=language, temperature=0.0,
                                  condition_on_previous_text=False)
        segments = [{"text": s.get("text", ""), "no_speech_prob": s.get("no_speech_prob", 0.0),
                     "compression_ratio": s.get("compression_ratio", 0.0)} for s in result.get("segments", [])]
        return {"text": result.get("text", ""), "language": result.get("language", ""), "segments": segments}

    parts, info = model.transcribe(path, language=language, beam_size=1, temperature=0.0,
                                   condition_on_previous_text=False, vad_filter=False)
    segments = [{"text": s.text, "no_speech_prob": s.no_speech_prob, "compression_ratio": s.compression_ratio}
                for s in parts]
    return {"text": "".join(s["text"] for s in segments), "language": info.language, "segments": segments}


@app.get("/v1/models")
def list_models():
    return {"object": "list", "data": [{"id": m, "object": "model"} for m in MODELS]}


@app.get("/health")
def health():
    return {"ok": True, "engine": "mlx-whisper" if USE_MLX else "faster-whisper", "loaded": list(_models)}


@app.post("/v1/audio/transcriptions")
async def transcriptions(
    file: UploadFile = File(...),
    model: str = Form(""),
    language: str = Form(""),
    response_format: str = Form("json"),
):
    name = model or MODELS[0]
    if name not in MODELS:
        raise HTTPException(status_code=400, detail=f"unknown model {name}")
    suffix = os.path.splitext(file.filename or "")[1] or ".wav"
    data = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        start = time.time()
        with _lock:
            try:
                result = _transcribe(name, path, language or None)
            except Exception as e:
                # 顯卡加速元件缺檔（Windows 常見）：改用 CPU 再跑一次，之後都用 CPU
                if _on_gpu.get(name) is not True:
                    raise
                print(f"⚠️ 顯卡辨識失敗，改用 CPU：{e}", flush=True)
                from faster_whisper import WhisperModel
                _models[name] = ("faster", name, WhisperModel(name, device="cpu", compute_type="int8",
                                                              cpu_threads=CPU_THREADS))
                _on_gpu[name] = False
                result = _transcribe(name, path, language or None)
        print(f"🎤 {name} {time.time() - start:.2f}s [{result['language']}] {result['text'][:40]}", flush=True)
    finally:
        os.unlink(path)
    if response_format == "verbose_json":
        return result
    return {"text": result["text"]}


if __name__ == "__main__":
    if "--download-only" in sys.argv:
        for m in MODELS:
            _load(m)
        sys.exit(0)
    # 預設模型先載入，第一句話才不會等很久
    threading.Thread(target=_load, args=(MODELS[0],), daemon=True).start()
    uvicorn.run(app, host=os.getenv("STT_HOST", "127.0.0.1"), port=int(os.getenv("STT_PORT", "9000")))
