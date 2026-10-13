import { useState } from "react";
import { Button, Field, G } from "../ui/ui";

/** Écran de connexion : identifiant, mot de passe, puis code TOTP. Maquette : rien n'est vérifié ni conservé. */
export function Login({ onLogin }: { onLogin: () => void }) {
  const [f, setF] = useState({ user: "", password: "", code: "" });
  const [tried, setTried] = useState(false);
  const bad = {
    user: !f.user.trim() ? "L'identifiant est obligatoire." : undefined,
    password: !f.password ? "Le mot de passe est obligatoire." : undefined,
    code: !/^\d{6}$/.test(f.code) ? "Le code comporte 6 chiffres. Le relire dans l'application d'authentification." : undefined,
  };
  const show = (k: keyof typeof bad) => (tried ? bad[k] : undefined);
  const submit = () => { setTried(true); if (!Object.values(bad).some(Boolean)) onLogin(); };
  return (
    <main className="login">
      <div className="login-card">
        <span className="title">Centrade</span>
        <form className="panel" onSubmit={(e) => { e.preventDefault(); submit(); }} noValidate>
          <h1>Connexion</h1>
          <Field label="Identifiant" required error={show("user")}>
            <input className="input" autoComplete="username" autoFocus value={f.user} onChange={(e) => setF({ ...f, user: e.target.value })} aria-invalid={!!show("user")} />
          </Field>
          <Field label="Mot de passe" required error={show("password")}>
            <input className="input" type="password" autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} aria-invalid={!!show("password")} />
          </Field>
          <Field label="Code à 6 chiffres" required error={show("code")} hint="Affiché par l'application d'authentification.">
            <input className="input num" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.replace(/\D/g, "") })} aria-invalid={!!show("code")} />
          </Field>
          <Button type="submit" variant="go">Se connecter</Button>
        </form>
        <p className="note-sm" style={{ margin: 0 }}>Accès par VPN uniquement. Maquette : n'importe quel identifiant, mot de passe et code <G k="totp" /> sont acceptés.</p>
      </div>
    </main>
  );
}
