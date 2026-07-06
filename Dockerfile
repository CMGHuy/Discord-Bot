# syntax=docker/dockerfile:1
#
# Single image, shared by both the bot and admin-ui services in
# docker-compose.yml (they just run different commands against it).
#
# Build-speed notes:
#   - requirements.txt now pins every package to an exact version instead
#     of a ">=" floor, so pip/uv's resolver has exactly one candidate per
#     package and never needs to backtrack across releases to find a
#     compatible set -- that backtracking (plus a metadata round-trip per
#     candidate it considers) was the single biggest cost on a cold build.
#   - Installs run through `uv` (astral's pip-compatible installer)
#     instead of plain pip: it resolves and downloads packages in
#     parallel rather than pip's one-at-a-time fetch, so even a fully
#     cold build (no cache at all) finishes faster. It's a drop-in CLI
#     (`uv pip install`), so nothing else about this Dockerfile changes.
#   - `--mount=type=cache,target=/root/.cache/uv` persists uv's package
#     cache in a BuildKit cache volume that lives OUTSIDE the image layer
#     (so it doesn't bloat the final image size) but survives between
#     builds -- a rebuild after only touching source files, or after
#     bumping one package's pin, reuses every already-downloaded wheel
#     instead of re-fetching from PyPI. Requires BuildKit, which is the
#     default for `docker build`/`docker compose build` on any reasonably
#     current Docker install; nothing extra needs enabling.
#   - No system-level build tools needed: every package in requirements.txt
#     ships pre-built binary wheels for Python 3.11 on linux/amd64 and
#     linux/arm64. --prefer-binary tells the installer to ALWAYS take the
#     wheel over a source distribution, so nothing ever compiles from
#     C/Fortran.
#   - requirements.txt is copied and installed BEFORE the source tree so
#     Docker's layer cache reuses this whole layer on every
#     `docker compose up --build` where only source files changed (the
#     common case) -- on top of uv's own cache mount above.
#   - The image is built ONCE and tagged; docker-compose.yml references it
#     by tag for the admin service instead of triggering a second build.
FROM python:3.11-slim

WORKDIR /app

# curl: used by the HEALTHCHECK in docker-compose.yml (admin service) and
# handy for ad-hoc debugging inside a running container. Installed before
# the Python deps so it's in its own cached layer -- a requirements.txt
# bump doesn't re-run apt.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# uv itself is tiny and rarely changes -- installing it in its own layer
# (before requirements.txt is even copied in) means it's cached
# independently of every dependency-pin bump below.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefer-binary uv

COPY requirements.txt .
# uv has no --prefer-binary flag (unlike pip) -- it already prefers
# prebuilt wheels over source distributions by default, so there's
# nothing to opt into here.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt

COPY . .

# Default command runs the bot; docker-compose.yml overrides this to
# `python admin_ui.py` for the admin service, from the same image.
CMD ["python", "bot.py"]
