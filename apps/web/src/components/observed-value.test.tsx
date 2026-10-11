import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ObservedValue } from "./observed-value";

const SERVER = "2026-10-10T18:32:05Z";
const render = (props: Partial<Parameters<typeof ObservedValue>[0]>) =>
  renderToStaticMarkup(
    <ObservedValue value="1 250,00 USDT" observedAt="2026-10-10T18:32:02Z" serverTime={SERVER} staleAfterMs={5_000} {...props} />,
  );

describe("ObservedValue", () => {
  it("affiche une valeur fraîche, focalisable pour lire son âge", () => {
    const html = render({});
    expect(html).toContain('data-state="fresh"');
    expect(html).toContain("1 250,00 USDT");
    expect(html).toContain('tabindex="0"');
    expect(html).not.toContain("périmé");
  });

  it("estompe une valeur périmée et la marque « périmé depuis … »", () => {
    const html = render({ observedAt: "2026-10-10T18:31:20Z" }); // 45 s, seuil 5 s : périmée depuis 40 s
    expect(html).toContain('data-state="stale"');
    expect(html).toContain("color-mix");
    expect(html).toContain("périmé depuis 40 s");
  });

  it.each([undefined, null, "", "unknown"])("affiche « inconnu » quand la valeur est %j", (value) => {
    const html = render({ value });
    expect(html).toContain('data-state="unknown"');
    expect(html).toContain("inconnu");
  });

  it("n'affiche jamais la valeur sans horodatage lisible : « inconnu » (I1)", () => {
    for (const observedAt of [null, undefined, "pas une date"]) {
      const html = render({ observedAt });
      expect(html).toContain('data-state="unknown"');
      expect(html).not.toContain("1 250,00 USDT");
    }
  });

  it("n'affiche pas la dernière valeur connue quand l'état est inconnu", () => {
    expect(render({ value: "unknown" })).not.toContain("1 250,00 USDT");
  });

  it("la chasse fixe est réservée aux identifiants, prix et horodatages : jamais par défaut", () => {
    expect(render({ value: "en marche" })).not.toContain("font-mono");
    expect(render({ value: "1 250,00", mono: true })).toContain("font-mono");
  });

  it("« inconnu » se distingue autrement que par la couleur : italique", () => {
    expect(render({ value: "unknown" })).toContain("italic");
  });
});
