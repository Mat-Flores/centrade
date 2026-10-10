// Caddy standard, recompilé avec une chaîne Go et des dépendances que nous épinglons
// (go.mod, go.sum) : même assemblage que celui de l'image officielle.
package main

import (
	caddycmd "github.com/caddyserver/caddy/v2/cmd"

	_ "github.com/caddyserver/caddy/v2/modules/standard"
)

func main() {
	caddycmd.Main()
}
