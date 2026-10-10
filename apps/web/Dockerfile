# Contexte de build : la racine du dépôt (voir deploy/compose/core.yml).
# Contrat : apps/web/.node-version, apps/web/package.json (champ packageManager),
# apps/web/pnpm-lock.yaml, script `build` qui produit apps/web/dist.
FROM node:22.23.3-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS build
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /web
COPY apps/web/.node-version apps/web/package.json apps/web/pnpm-lock.yaml ./
# L'image Node est épinglée par digest : refuse le build si elle diverge de .node-version.
RUN test "v$(tr -d '[:space:]' < .node-version)" = "$(node -v)" \
 && corepack enable \
 && pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN pnpm build

# Même image Caddy que le service `caddy` (core.yml) ; TLS fait par le Caddy frontal.
FROM caddy:2.11.7-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f
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
COPY --from=build /web/dist /srv
RUN adduser -S -D -H -u 10002 web
USER 10002
EXPOSE 8080
