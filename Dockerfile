# One image serves the application and the verification tooling, so local runs and CI exercise
# byte-identical dependencies through the same boundary.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable \
 && uv sync --frozen --no-editable

COPY tests ./tests

# Every container runs as this unprivileged account; nothing in the demo needs root.
RUN groupadd --gid 10001 flowjack \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin flowjack \
 && chown -R flowjack:flowjack /app /opt/venv
USER 10001:10001

CMD ["uvicorn", "flowjack.secure_app:app", "--host", "0.0.0.0", "--port", "8000"]
