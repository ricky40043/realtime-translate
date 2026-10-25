# Linux 伺服器用（CPU）。Mac / Windows 請用專案根目錄的一鍵安裝，會直接用電腦的 GPU
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY stt_server.py .
ENV STT_HOST=0.0.0.0 STT_PORT=9000 HF_HOME=/models
EXPOSE 9000
CMD ["python", "stt_server.py"]
