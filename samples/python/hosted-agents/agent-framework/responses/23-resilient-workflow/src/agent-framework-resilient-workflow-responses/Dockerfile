FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.13-slim

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

EXPOSE 8088

RUN PYTHONDONTWRITEBYTECODE= /app/.venv/bin/python -m compileall -q $(/app/.venv/bin/python -c "import sysconfig as s; print(s.get_paths()['stdlib'], s.get_paths()['purelib'])") || true; \
    PYTHONDONTWRITEBYTECODE= /app/.venv/bin/python -m compileall -q -x '[.]venv' .

CMD ["/app/.venv/bin/python", "main.py"]
