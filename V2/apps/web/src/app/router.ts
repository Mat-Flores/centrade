import { useSyncExternalStore, type MouseEvent } from "react";

/**
 * Minimal router on the History API: real paths, shareable URLs, back button, no dependency.
 * Source: https://developer.mozilla.org/docs/Web/API/History_API
 */

export type LibraryTab = "keys" | "strategies" | "automations";
export const LIBRARY_TABS: readonly LibraryTab[] = ["keys", "strategies", "automations"];

export type Route =
  | { page: "instances" }
  | { page: "instance"; id: string; tab: string } // tab: "all" or a pair; the pair-to-path conversion belongs to the instance screen
  | { page: "library"; tab: LibraryTab }
  | { page: "journal" }
  | { page: "advanced" }
  | { page: "settings" }
  | { page: "notFound" };

export const ALL_TAB = "all";

const SIMPLE_PAGES = ["journal", "advanced", "settings"] as const;

/** Route of a pathname. `/` is the instances list; an unknown path is `notFound`. A trailing slash is tolerated. */
export function parse(pathname: string): Route {
  const clean = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  let segments: string[];
  try {
    segments = clean.split("/").slice(1).map(decodeURIComponent);
  } catch {
    return { page: "notFound" }; // malformed escape
  }
  const [page, a, b, ...rest] = segments;
  if (rest.length > 0) return { page: "notFound" };
  if (page === "" && a === undefined) return { page: "instances" };
  if (page === "instances") {
    if (a === undefined) return { page: "instances" };
    if (a === "" || b === "") return { page: "notFound" };
    return { page: "instance", id: a, tab: b ?? ALL_TAB };
  }
  if (page === "library") {
    if (b !== undefined) return { page: "notFound" };
    if (a === undefined) return { page: "library", tab: "keys" };
    const tab = LIBRARY_TABS.find((t) => t === a);
    return tab ? { page: "library", tab } : { page: "notFound" };
  }
  const simple = SIMPLE_PAGES.find((p) => p === page);
  if (simple && a === undefined) return { page: simple };
  return { page: "notFound" };
}

/** Canonical path of a route (the reverse of `parse`). */
export function href(route: Route): string {
  switch (route.page) {
    case "instances": return "/instances";
    case "instance": return route.tab === ALL_TAB ? `/instances/${encodeURIComponent(route.id)}` : `/instances/${encodeURIComponent(route.id)}/${encodeURIComponent(route.tab)}`;
    case "library": return `/library/${route.tab}`;
    case "notFound": return "/";
    default: return `/${route.page}`;
  }
}

/** A plain left click, with no modifier: the only click the router takes over. */
export function isPlainClick(e: { button: number; metaKey: boolean; ctrlKey: boolean; shiftKey: boolean; altKey: boolean; defaultPrevented: boolean }): boolean {
  return !e.defaultPrevented && e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey;
}

// True from the first navigation of the session: the first display does not steal the focus, the next ones move it.
let navigated = false;
export const hasNavigated = () => navigated;
if (typeof window !== "undefined") window.addEventListener("popstate", () => (navigated = true));

const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

export function navigate(path: string): void {
  if (path === window.location.pathname) return;
  navigated = true;
  window.history.pushState(null, "", path);
  notify();
}

/** Replaces the current entry (canonical URL): no new history step. */
export function replace(path: string): void {
  window.history.replaceState(null, "", path);
  notify();
}

/** Click handler for an `<a href>`: a plain click navigates in place; Ctrl/Cmd/Shift/middle click keep the native link. */
export function onLinkClick(e: MouseEvent, path: string): void {
  if (!isPlainClick(e)) return;
  e.preventDefault();
  navigate(path);
}

// A string snapshot keeps useSyncExternalStore stable; the route object is derived from it.
const pathname = () => window.location.pathname;
let cached: { path: string; route: Route } | null = null;
function routeAt(path: string): Route {
  if (cached?.path !== path) cached = { path, route: parse(path) };
  return cached.route;
}
export function useRoute(): Route {
  return routeAt(useSyncExternalStore(subscribe, pathname));
}
