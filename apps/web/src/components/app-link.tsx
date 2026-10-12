import type { AnchorHTMLAttributes } from "react";

import { navigate } from "@/lib/router";

/** Lien interne : clic simple = navigation sans rechargement ; Ctrl, Cmd, Maj ou clic milieu gardent le comportement du lien. */
export function AppLink({ to, onClick, ...props }: { to: string } & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">) {
  return (
    <a
      href={to}
      onClick={(event) => {
        onClick?.(event);
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        navigate(to);
      }}
      {...props}
    />
  );
}
