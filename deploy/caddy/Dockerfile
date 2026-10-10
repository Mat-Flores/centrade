# Contexte de build : la racine du dépôt (voir deploy/compose/core.yml).
# Deux cibles sur le même Caddy : `proxy` (frontal TLS) et `web` (fichiers du front).
#
# Caddy est recompilé ici, avec la chaîne Go et les dépendances épinglées dans build/go.mod,
# plutôt que repris de l'image officielle : on corrige une CVE de Go ou d'une dépendance
# sans attendre une publication de Caddy (ADR 0003). Le binaire n'a aucune capacité de
# fichier : il tourne sans root et sans aucune capacité.
FROM golang:1.26.9-alpine3.23@sha256:6750308561953d451210ed1a8086d36c8c8bdcbf672d38d9d0d424b8a7a0216c AS caddy-build
ENV CGO_ENABLED=0 GOTOOLCHAIN=local GOFLAGS=-mod=readonly
WORKDIR /src
COPY deploy/caddy/build/go.mod deploy/caddy/build/go.sum ./
RUN go mod download
COPY deploy/caddy/build/main.go ./
RUN go build -trimpath -ldflags="-s -w" -o /caddy .

# L'image officielle fournit le système de base, les certificats racine et les dossiers.
FROM caddy:2.11.7-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f AS base
COPY --from=caddy-build /caddy /usr/bin/caddy
RUN adduser -S -D -H -u 10002 caddy && chown -R 10002 /data /config
USER 10002

# nosemgrep: centrade-image-tag-latest-dockerfile -- `base` est une étape de ce fichier, pas une image
FROM base AS proxy
EXPOSE 8443

# Contrat du front : apps/web/.node-version, package.json (champ packageManager),
# pnpm-lock.yaml, script `build` qui produit apps/web/dist.
FROM node:22.23.3-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS web-build
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /web
COPY apps/web/.node-version apps/web/package.json apps/web/pnpm-lock.yaml ./
# L'image Node est épinglée par digest : refuse le build si elle diverge de .node-version.
RUN test "v$(tr -d '[:space:]' < .node-version)" = "$(node -v)" \
 && corepack enable \
 && pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN pnpm build

# nosemgrep: centrade-image-tag-latest-dockerfile -- `base` est une étape de ce fichier, pas une image
FROM base AS web
COPY <<'EOF2' /etc/caddy/Caddyfile
{
	admin off
	auto_https off
}
:8080 {
	root * /srv
	encode zstd gzip
	# Application à page unique : repli sur index.html.
	try_files {path} /index.html
	file_server
}
EOF2
COPY --from=web-build /web/dist /srv
EXPOSE 8080
