FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.13-slim
ENV PYTHONNOUSERSITE=1
COPY --from=uv /uv /bin/uv
WORKDIR /app
COPY requirements.txt .
RUN uv venv && uv pip sync --python .venv/bin/python requirements.txt
COPY main.py .
EXPOSE 8088
CMD ["/app/.venv/bin/python", "main.py"]
