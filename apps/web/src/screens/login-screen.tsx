import { useQueryClient } from "@tanstack/react-query";
import { CircleAlertIcon } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { fr, loginErrorMessage } from "@/i18n/fr";
import { submitLogin, submitTotp, type LoginFailure } from "@/lib/login";
import { meKey } from "@/lib/session";

type Step = "password" | "totp";
type State = { status: "idle" } | { status: "pending" } | { status: "failed"; failure: LoginFailure };

/** Connexion en deux étapes : mot de passe, puis code TOTP (ou code de récupération). */
export function LoginScreen() {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>("password");
  const [state, setState] = useState<State>({ status: "idle" });
  // La référence est sur le formulaire : les composants shadcn ne transmettent pas `ref` en React 18.
  const formRef = useRef<HTMLFormElement>(null);
  const field = (name: string) => formRef.current?.elements.namedItem(name) as HTMLInputElement | null;
  const pending = state.status === "pending";
  const failure = state.status === "failed" ? state.failure : null;
  const messageId = "login-message";

  // Le focus va au champ à remplir quand l'étape change ou qu'un envoi échoue (jamais au premier affichage).
  useEffect(() => {
    if (step === "totp" || failure) field(step === "password" ? "password" : "code")?.focus();
  }, [step, failure]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const data = new FormData(event.currentTarget);
    // Mot de passe et code ne survivent pas à l'envoi : le champ est vidé aussitôt.
    const secret = field(step === "password" ? "password" : "code");
    if (secret) secret.value = "";
    setState({ status: "pending" });
    if (step === "password") {
      const result = await submitLogin({
        username: String(data.get("username") ?? ""),
        password: String(data.get("password") ?? ""),
      });
      if (result.ok) {
        setState({ status: "idle" });
        setStep("totp");
      } else setState({ status: "failed", failure: result });
      return;
    }
    const result = await submitTotp(String(data.get("code") ?? ""));
    if (result.ok) {
      // La session existe côté serveur : /auth/me la confirme, et la coquille s'affiche.
      await queryClient.invalidateQueries({ queryKey: meKey });
      setState({ status: "idle" });
    } else setState({ status: "failed", failure: result });
  }

  const totp = step === "totp";
  return (
    <div className="flex min-h-dvh flex-col gap-6 px-4 py-6 sm:px-10 sm:py-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{fr.productName}</h1>
      </header>

      <main className="flex flex-1 items-center justify-center pb-10">
        <section
          aria-labelledby="login-title"
          className="w-full max-w-sm rounded-xl border bg-card p-6 text-card-foreground shadow-panel sm:p-8"
        >
          <h2 id="login-title" className="text-xl font-semibold tracking-tight">
            {totp ? fr.totp.title : fr.login.title}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">{totp ? fr.totp.help : fr.login.access}</p>

          <form
            key={step}
            ref={formRef}
            onSubmit={onSubmit}
            className="mt-6 flex flex-col gap-5"
            aria-describedby={failure ? messageId : undefined}
          >
            <FieldGroup className="gap-4">
              {totp ? (
                <Field>
                  <FieldLabel htmlFor="code">{fr.totp.code}</FieldLabel>
                  <Input
                    id="code"
                    name="code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    autoCapitalize="none"
                    spellCheck={false}
                    required
                    disabled={pending}
                    aria-invalid={failure ? true : undefined}
                    aria-describedby={failure ? messageId : undefined}
                  />
                </Field>
              ) : (
                <>
                  <Field>
                    <FieldLabel htmlFor="username">{fr.login.username}</FieldLabel>
                    <Input
                      id="username"
                      name="username"
                      type="text"
                      autoComplete="username"
                      autoCapitalize="none"
                      spellCheck={false}
                      required
                      disabled={pending}
                      aria-invalid={failure ? true : undefined}
                      aria-describedby={failure ? messageId : undefined}
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="password">{fr.login.password}</FieldLabel>
                    <Input
                      id="password"
                      name="password"
                      type="password"
                      autoComplete="current-password"
                      required
                      disabled={pending}
                      aria-invalid={failure ? true : undefined}
                      aria-describedby={failure ? messageId : undefined}
                    />
                  </Field>
                </>
              )}
            </FieldGroup>

            {failure && (
              <Alert id={messageId} role="alert">
                <CircleAlertIcon />
                <AlertTitle>{totp ? fr.totp.errorTitle : fr.login.errorTitle}</AlertTitle>
                <AlertDescription>{loginErrorMessage(failure, step)}</AlertDescription>
              </Alert>
            )}

            <Button type="submit" size="lg" disabled={pending}>
              {pending && <Spinner data-icon="inline-start" />}
              {pending ? (totp ? fr.totp.pending : fr.login.pending) : totp ? fr.totp.submit : fr.login.submit}
            </Button>
            {totp && (
              <Button
                type="button"
                variant="ghost"
                disabled={pending}
                onClick={() => {
                  setState({ status: "idle" });
                  setStep("password");
                }}
              >
                {fr.totp.back}
              </Button>
            )}
            <span className="sr-only" role="status">
              {pending ? (totp ? fr.totp.pending : fr.login.pending) : ""}
            </span>
          </form>
        </section>
      </main>

      <footer className="text-sm text-muted-foreground">{fr.footer}</footer>
    </div>
  );
}
