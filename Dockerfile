# The Aggravation website. Build and run:
#   docker build -t aggravation .
#   docker run -p 8000:8000 aggravation
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "aggervation-web"]
