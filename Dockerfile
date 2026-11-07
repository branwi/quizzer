FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATABASE_URL=sqlite:////data/quizapp.db
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 quizzer && mkdir /data && chown quizzer:quizzer /data
COPY app ./app
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini .
USER quizzer
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["sh", "-c", "python -m scripts.migrate && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
