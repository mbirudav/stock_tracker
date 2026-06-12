# Stage 1: Build Next.js frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + serve frontend
FROM python:3.12-slim AS runtime
WORKDIR /app

# Install uv
RUN pip install uv

# Install Python dependencies
COPY backend/pyproject.toml backend/uv.lock* ./backend/
RUN cd backend && uv sync --frozen --no-dev

# Copy backend source
COPY backend/ ./backend/

# Copy frontend static export from stage 1
# NOTE: backend/main.py serves static files from <backend_dir>/../static = /app/static
COPY --from=frontend-builder /app/frontend/out ./static

# Create db directory
RUN mkdir -p /app/db

# Expose port
EXPOSE 8000

# Run — invoke the venv's interpreter directly (bypasses `uv run`, which would
# re-resolve and re-sync the entire environment on every container start)
CMD ["/app/backend/.venv/bin/python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
