FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir flask gunicorn

COPY server.py .

EXPOSE 80

CMD ["gunicorn", "--bind", "0.0.0.0:80", "--workers", "2", "server:app"]
