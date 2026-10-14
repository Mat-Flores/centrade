import type { AnchorHTMLAttributes } from "react";

import { href, onLinkClick, type Route } from "./router";

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & { to: Route };

/** A real `<a href>`: opens in a new tab with Ctrl/Cmd/Shift/middle click, navigates in place otherwise. */
export function Link({ to, onClick, ...rest }: LinkProps) {
  const path = href(to);
  return <a {...rest} href={path} onClick={(e) => { onClick?.(e); onLinkClick(e, path); }} />;
}
