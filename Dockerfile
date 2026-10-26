FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000 SHELFWATCH_STATE_DIR=/data
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser && mkdir /data && chown appuser:appuser /data
COPY requirements.lock .
RUN pip install --no-cache-dir --no-compile -r requirements.lock
COPY --chown=appuser:appuser . .
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health', timeout=2)" || exit 1
CMD ["python", "run.py"]

