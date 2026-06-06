FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend
COPY backend/ backend/

# Copy frontend
COPY frontend/ frontend/

# Environment (overridable via .env or -e)
ENV LLM_PROVIDER=openai
ENV LLM_API_KEY=""
ENV LLM_MODEL=gpt-4o

# Expose
EXPOSE 8000

# Run
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
