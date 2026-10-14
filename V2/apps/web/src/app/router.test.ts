import { describe, expect, it } from "vitest";

import { href, isPlainClick, parse, type Route } from "./router";

describe("parse", () => {
  it("opens the instances list on the root path", () => {
    expect(parse("/")).toEqual({ page: "instances" });
    expect(parse("/instances")).toEqual({ page: "instances" });
  });
  it("tolerates a trailing slash", () => {
    expect(parse("/instances/")).toEqual({ page: "instances" });
    expect(parse("/journal/")).toEqual({ page: "journal" });
  });
  it("reads an instance with the all tab by default", () => {
    expect(parse("/instances/abc")).toEqual({ page: "instance", id: "abc", tab: "all" });
  });
  it("reads an instance with an explicit tab and decodes it", () => {
    expect(parse("/instances/abc/BTC%2FUSDT")).toEqual({ page: "instance", id: "abc", tab: "BTC/USDT" });
    expect(parse("/instances/abc/all")).toEqual({ page: "instance", id: "abc", tab: "all" });
  });
  it("reads the three library tabs and defaults a bare library path to keys", () => {
    expect(parse("/library/keys")).toEqual({ page: "library", tab: "keys" });
    expect(parse("/library/strategies")).toEqual({ page: "library", tab: "strategies" });
    expect(parse("/library/automations")).toEqual({ page: "library", tab: "automations" });
    expect(parse("/library")).toEqual({ page: "library", tab: "keys" });
  });
  it("reads the single pages", () => {
    expect(parse("/journal")).toEqual({ page: "journal" });
    expect(parse("/advanced")).toEqual({ page: "advanced" });
    expect(parse("/settings")).toEqual({ page: "settings" });
  });
  it("refuses an unknown path, an unknown library tab, extra segments and a malformed escape", () => {
    for (const path of ["/nope", "/library/other", "/journal/x", "/instances/a/b/c", "/instances//x", "/instances/%E0%A4%A"]) {
      expect(parse(path)).toEqual({ page: "notFound" });
    }
  });
});

describe("href", () => {
  const routes: Route[] = [
    { page: "instances" },
    { page: "instance", id: "abc", tab: "all" },
    { page: "instance", id: "abc", tab: "BTC/USDT" },
    { page: "library", tab: "automations" },
    { page: "journal" },
    { page: "advanced" },
    { page: "settings" },
  ];
  it("builds the canonical path of each route", () => {
    expect(routes.map(href)).toEqual([
      "/instances", "/instances/abc", "/instances/abc/BTC%2FUSDT", "/library/automations", "/journal", "/advanced", "/settings",
    ]);
  });
  it("gives back the same route when its path is parsed", () => {
    for (const route of routes) expect(parse(href(route))).toEqual(route);
  });
});

describe("isPlainClick", () => {
  const click = { button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, defaultPrevented: false };
  it("takes over a plain left click only", () => {
    expect(isPlainClick(click)).toBe(true);
    expect(isPlainClick({ ...click, ctrlKey: true })).toBe(false);
    expect(isPlainClick({ ...click, metaKey: true })).toBe(false);
    expect(isPlainClick({ ...click, shiftKey: true })).toBe(false);
    expect(isPlainClick({ ...click, button: 1 })).toBe(false);
    expect(isPlainClick({ ...click, defaultPrevented: true })).toBe(false);
  });
});
