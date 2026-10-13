import { useSyncExternalStore } from "react";

export type LibraryTab = "cles" | "strategies" | "automatisations";
export type Route =
  | { page: "instances" }
  | { page: "instance"; id: string; tab: string } // tab : "tout" ou une paire, ex. "BTC/USDT"
  | { page: "bibliotheque"; tab: LibraryTab }
  | { page: "journal" }
  | { page: "avance" }
  | { page: "parametres" };

// Route dans le fragment d'URL : rien n'est persistant, mais le retour arrière du navigateur fonctionne.
export function parse(hash: string): Route {
  const [page, a, ...rest] = decodeURIComponent(hash.replace(/^#\/?/, "")).split("/");
  if (page === "instance" && a) return { page, id: a, tab: rest.join("/") || "tout" };
  if (page === "bibliotheque") return { page, tab: a === "strategies" || a === "automatisations" ? a : "cles" };
  if (page === "journal" || page === "avance" || page === "parametres") return { page };
  return { page: "instances" };
}

export function href(r: Route): string {
  if (r.page === "instance") return `#/instance/${r.id}/${r.tab}`;
  if (r.page === "bibliotheque") return `#/bibliotheque/${r.tab}`;
  return `#/${r.page}`;
}

export function go(r: Route) {
  location.hash = href(r);
}

const subscribe = (cb: () => void) => {
  addEventListener("hashchange", cb);
  return () => removeEventListener("hashchange", cb);
};
let last = { hash: "", route: parse("") };
export function useRoute(): Route {
  return useSyncExternalStore(subscribe, () => {
    if (location.hash !== last.hash) last = { hash: location.hash, route: parse(location.hash) };
    return last.route;
  });
}
