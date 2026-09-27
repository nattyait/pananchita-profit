FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
COPY config ./config
RUN pip install --no-cache-dir .
ENV PNC_DATA_DIR=/data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.web.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
