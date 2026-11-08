# Runs next to Nemotron on the same GPU, using the torch build already in the vLLM image.
FROM vllm/vllm-openai:latest
RUN pip install --no-cache-dir -q gliclass
COPY guard_server.py /app/guard_server.py
ENTRYPOINT ["python3", "-m", "uvicorn", "guard_server:app", "--app-dir", "/app", "--host", "127.0.0.1", "--port", "8002", "--no-access-log"]
