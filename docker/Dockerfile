# syntax=docker/dockerfile:1
#
# One image, two processes. The API and the worker run the same code and the
# same package, so a recipe cannot behave differently depending on which one
# executed it. They differ only in the command compose gives them.
#
# Build from the repository root, not from docker/:
#   docker compose -f docker/compose.yml build

# --- the front end ------------------------------------------------------------
# Built here rather than committed, so the served app always matches this source.
FROM node:22-alpine AS web

WORKDIR /web
# The lock file first, so a source edit does not reinstall every dependency.
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build


# --- the python service -------------------------------------------------------
FROM python:3.12-slim AS app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}" \
    MPLBACKEND=Agg

# Agg above because figures are written to files and there is no display here.
# Without it matplotlib picks an interactive backend and a recipe dies on import.

RUN pip install --no-cache-dir uv==0.12.10

WORKDIR /app

# Dependencies from the lock file, in their own layer. --frozen means the lock is
# used exactly as committed: a container must not quietly resolve a different
# version of scipy than the one a run record claims.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
COPY configs/ configs/
COPY manifest/ manifest/
COPY scripts/ scripts/
RUN uv sync --frozen --no-dev

COPY --from=web /web/dist web/dist

# Provenance. There is no .git in the image, so without this every run record
# from a container would claim no commit, and every bundle README would call the
# result provisional. Passed by the build, not guessed at run time:
#   GIT_COMMIT=$(git rev-parse HEAD) \
#   GIT_DIRTY=$(test -n "$(git status --porcelain)" && echo true || echo false) \
#   docker compose -f docker/compose.yml build
ARG GIT_COMMIT=""
ARG GIT_DIRTY="false"
ENV DBSSPEECH_GIT_COMMIT="${GIT_COMMIT}" \
    DBSSPEECH_GIT_DIRTY="${GIT_DIRTY}"

# Runs as a normal user. The uid is fixed and stated in docs/deploy.md because
# the host directories behind the volumes have to be writable by it.
RUN useradd --create-home --uid 10001 dbsspeech \
    && mkdir -p /app/derivatives /app/runs /app/var \
    && chown -R dbsspeech:dbsspeech /app
USER dbsspeech

EXPOSE 8000

# The API. compose overrides this for the worker.
CMD ["python", "-m", "dbsspeech", "serve", "--host", "0.0.0.0", "--port", "8000"]
