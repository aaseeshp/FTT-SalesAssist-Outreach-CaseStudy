# SalesAssist Outreach Assist (POC) - container image
#   docker build -t outreach-poc .
#   docker run -p 8000:8000 -e LLM_PROVIDER=gemini -e GEMINI_API_KEY=... outreach-poc
# Never bake keys into the image: pass them at run time (or as platform secrets).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CREWAI_TRACING_ENABLED=false \
    OTEL_SDK_DISABLED=true \
    WARM_CACHE=true

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir "anthropic==2.12.0"

COPY app ./app
COPY data ./data

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
# Single worker on purpose: the draft cache and action log are in memory in this POC.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
