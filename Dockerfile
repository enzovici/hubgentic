FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY ontology ./ontology
RUN uv sync --frozen --no-dev
ENV HOST=0.0.0.0 PORT=8000 HUBGENTIC_DB=/data/hubgentic.db HUBGENTIC_SECURE_COOKIES=1
VOLUME /data
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "hubgentic-web"]
