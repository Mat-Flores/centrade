# ADR-0003 : Caddy recompilé dans le dépôt

## Statut
Acceptée

## Date
2026-10-10

## Contexte
Trivy bloquait la CI : le binaire de l'image officielle `caddy:2.11.7-alpine`, dernière version publiée, était compilé avec Go 1.26.8 et `golang.org/x/net` 0.59.0, qui portent trois CVE élevées de déni de service (CVE-2026-78667, CVE-2026-78669, CVE-2026-97031). Aucune image corrigée n'existait. Par ailleurs ce binaire porte une capacité de fichier (`NET_BIND_SERVICE`) qui empêchait de retirer toutes les capacités, et le Caddy frontal tournait en root (écart avec le §13).

## Décision
`deploy/caddy/Dockerfile` recompile Caddy à partir de `deploy/caddy/build/` (`main.go`, `go.mod`, `go.sum`) : la version de Caddy, celle de Go (image `golang` épinglée par digest) et celle de chaque dépendance sont fixées dans le dépôt. Le binaire remplace celui de l'image officielle, qui reste la base (système, certificats racine). Le même fichier produit deux cibles : `proxy` (frontal TLS) et `web` (fichiers du front). Les deux tournent sous l'uid 10002, sans aucune capacité.

L'assemblage est celui de l'image officielle : `caddycmd.Main()` et les modules standard, sans greffon.

## Alternatives écartées
- Accepter le risque 30 jours et ignorer les CVE dans Trivy : rien à maintenir, mais le même blocage revient à chaque CVE de Go, et le délai dépend d'un tiers.
- `xcaddy` : un outil de plus à épingler, pour un résultat identique à un `go build`.
- Laisser la CI rouge.

## Conséquences
- Une CVE de Go ou d'une dépendance se corrige en montant une version dans `go.mod` ou l'image `golang`, sans attendre Caddy. Dependabot suit `gomod` (`deploy/caddy/build`) et `docker` (`deploy/caddy`).
- Monter Caddy, c'est changer sa version dans `go.mod` et le tag de l'image de base, ensemble.
- Le build de l'image dure plus longtemps (compilation de Caddy), hors cache.
- `apps/web/Dockerfile` disparaît : l'image du front est la cible `web`.
- Un volume `caddy_data` créé avant ce changement appartient à root : le rendre à l'uid 10002 (`chown`) une fois. Un volume neuf est correct d'emblée.
