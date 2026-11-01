FROM python:3.12-slim
WORKDIR /app
COPY requirements-backend.txt .
RUN pip install --no-cache-dir -r requirements-backend.txt
COPY . .
ENV OSS_WORK_REPO=/workspace/oss-work-universal-ai-agent
CMD ["uvicorn", "oss_work_api:app", "--host", "0.0.0.0", "--port", "8000"]
