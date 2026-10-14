import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { fr } from "@/i18n/fr";

import { ErrorBoundary } from "./ErrorBoundary";

describe("ErrorBoundary", () => {
  it("switches to the failed state when a child throws", () => {
    expect(ErrorBoundary.getDerivedStateFromError()).toEqual({ failed: true });
  });
  it("renders its children while nothing failed", () => {
    expect(renderToStaticMarkup(<ErrorBoundary><p>ok</p></ErrorBoundary>)).toBe("<p>ok</p>");
  });
  it("renders the sober error screen with a reload button once failed", () => {
    const boundary = new ErrorBoundary({ children: null });
    boundary.state = { failed: true };
    const html = renderToStaticMarkup(boundary.render());
    expect(html).toContain('role="alert"');
    expect(html).toContain(fr.crash.title);
    expect(html).toContain(fr.crash.reload);
  });
});
