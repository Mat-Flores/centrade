// Standard Caddy, recompiled with a Go toolchain and dependencies that we pin
// (go.mod, go.sum): same assembly as the official image's.
package main

import (
	caddycmd "github.com/caddyserver/caddy/v2/cmd"

	_ "github.com/caddyserver/caddy/v2/modules/standard"
)

func main() {
	caddycmd.Main()
}
