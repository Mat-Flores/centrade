import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

// Pile réelle et jetable (scripts/e2e_stack.py) : API, worker et FakeEngine. Les identifiants sont
// générés à chaque exécution et lus dans un fichier temporaire hors du dépôt.
const creds = JSON.parse(readFileSync(process.env.E2E_CREDS_FILE ?? "", "utf8")) as {
  email: string;
  password: string;
  totp_secret: string;
};

const B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

/** TOTP RFC 6238 (SHA-1, 6 chiffres, pas de 30 s) calculé dans le test. */
function totp(secret: string, at = Date.now()): string {
  let bits = "";
  for (const c of secret.replace(/=+$/, "").toUpperCase()) bits += B32.indexOf(c).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g)?.map((b) => parseInt(b, 2)) ?? []);
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 30_000)));
  const h = createHmac("sha1", key).update(counter).digest();
  const o = h[h.length - 1]! & 0xf;
  const n = ((h[o]! & 0x7f) << 24) | (h[o + 1]! << 16) | (h[o + 2]! << 8) | h[o + 3]!;
  return String(n % 1_000_000).padStart(6, "0");
}

test("pile réelle : connexion, création, état observé en temps réel, réouverture des entrées vérifiée", async ({ page }) => {
  const errors: string[] = [];
  const foreign: string[] = [];
  // Le 401 de /auth/me avant la connexion est normal : seules les autres erreurs comptent (CSP comprise).
  page.on("console", (m) => m.type() === "error" && !m.text().includes("401") && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (u.hostname !== "localhost" && u.protocol.startsWith("http")) foreign.push(r.url());
  });

  await page.goto("/");
  await page.getByLabel("Identifiant").fill(creds.email);
  await page.getByLabel("Mot de passe").fill(creds.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await page.getByLabel("Code").fill(totp(creds.totp_secret));
  await page.getByRole("button", { name: "Valider le code" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "Cockpit" })).toBeVisible();
  await expect(page.getByText("Aucune instance")).toBeVisible();
  await expect(page.getByRole("banner").getByText(/Mode dégradé/)).toHaveCount(0);
  await page.evaluate(() => ((window as unknown as { __noReload: boolean }).__noReload = true));

  await page.getByRole("button", { name: "Créer une instance simulée" }).click();
  await page.getByLabel("Nom de l'instance").fill("e2e-fake");
  await page.getByRole("button", { name: "Créer l'instance" }).click();

  // L'instance apparaît sans rechargement, puis son état observé passe à « sorties seules » (FakeEngine).
  const row = page.locator('li[data-instance="e2e-fake"]');
  await expect(row).toBeVisible();
  await expect(row.locator('[data-state="fresh"]').filter({ hasText: "sorties seules" })).toBeVisible({ timeout: 30_000 });
  await expect(row.getByText("simulé")).toBeVisible();

  // Rouvrir les entrées : la confirmation annonce la conséquence, puis la commande va jusqu'à verified.
  await row.getByRole("button", { name: "Rouvrir les entrées" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("État observé à cet instant : sorties seules");
  await dialog.getByRole("button", { name: "Rouvrir les entrées" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(row.locator('[data-command-status="verified"]')).toContainText("faite, effet observé dans le moteur", { timeout: 30_000 });
  await expect(row.locator('[data-state="fresh"]').filter({ hasText: "en marche" })).toBeVisible({ timeout: 30_000 });

  expect(await page.evaluate(() => (window as unknown as { __noReload?: boolean }).__noReload)).toBe(true);
  expect(foreign).toEqual([]);
  expect(errors).toEqual([]);
});
