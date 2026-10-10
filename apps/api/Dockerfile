# Contexte de build : la racine du dépôt (voir deploy/compose/core.yml).
# Sources : https://docs.astral.sh/uv/guides/integration/docker/
FROM ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 AS uv

FROM python:3.14.7-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /src
COPY pyproject.toml uv.lock ./
# Dépendances de production seulement, exactement celles de uv.lock.
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.14.7-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin centrade
COPY --from=build /opt/venv /opt/venv
COPY apps/api/centrade_api /app/centrade_api
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
USER 10001
EXPOSE 8000
CMD ["uvicorn", "centrade_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
