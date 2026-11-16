# The API in a container: Uvicorn serving energy_positions.app, as a non-root user,
# and the one-page front end it serves at /.
#
#   docker build -t energy-positions-api .
#   docker run --rm -p 8048:8000 -e DATABASE_URL=... energy-positions-api
#
# Three stages. The first builds the page, with Node. The second installs the locked
# dependencies and the package into a virtual environment with uv. The third copies
# that environment and the built page, and nothing else, onto a clean Python: nothing
# of Node reaches the image.

# Node 22, pinned to the version the page was built and tested with. web/package.json
# says what the page needs, and the `web` job in ci.yml names this same version.
FROM node:22.23.4-slim AS web

WORKDIR /web

# The packages first, in a layer of their own: it is rebuilt only when the lock changes.
COPY web/package.json web/package-lock.json ./
RUN npm ci

# Then the page. Its tests run in CI's `web` job, not here: the image only needs the build.
COPY web/ ./
RUN npm run build


FROM python:3.14-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv

# Use the image's Python, never a downloaded one; compile to bytecode now, so the
# first request does not pay for it; copy files out of uv's cache, which stays here.
ENV UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# The dependencies first, in a layer of their own: it is rebuilt only when uv.lock
# changes, not on every edit to the code.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# Then the package itself, installed as a wheel, not as a link back to src/.
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable


FROM python:3.14-slim

LABEL org.opencontainers.image.source="https://github.com/CliffordKeeble/energy-positions-api" \
      org.opencontainers.image.description="Net energy positions by GB settlement period. A demo, on synthetic data."

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin api

COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# The built page, and where the app finds it. The package is a wheel here, so the
# source-tree default (web/dist beside src/) leads nowhere, and WEB_DIR has to say.
COPY --from=web /web/dist /app/web
ENV WEB_DIR=/app/web

USER api
EXPOSE 8000

# PORT, if the platform sets it; 8000 if not. The proxy-header options make Uvicorn
# believe the X-Forwarded-Proto and X-Forwarded-For that Azure's ingress adds, so the
# app sees https and not the plain http that reaches the container. Every address is
# trusted for them because nothing but the ingress can reach the container.
CMD ["sh", "-c", "exec uvicorn energy_positions.app:app --host 0.0.0.0 --port \"${PORT:-8000}\" --proxy-headers --forwarded-allow-ips '*'"]
