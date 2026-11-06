FROM ghcr.io/astral-sh/uv:0.11.0 AS uv
FROM python:3.13-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY src/ src/
COPY data/ data/
RUN uv sync --locked --no-dev
RUN useradd --create-home salesops && mkdir -p logs traces reports && chown -R salesops:salesops /app
USER salesops
ENTRYPOINT ["uv", "run", "--no-sync", "salesops-agent"]
