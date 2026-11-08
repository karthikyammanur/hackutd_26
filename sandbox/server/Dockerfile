FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py *.sql .
CMD ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8765", "--no-access-log", "--timeout-graceful-shutdown", "10"]
