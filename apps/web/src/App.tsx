import { CircleAlertIcon, CircleCheckIcon } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { fr, loginErrorMessage } from "@/i18n/fr";
import { submitLogin, type LoginResult } from "@/lib/login";

type State = { status: "idle" } | { status: "pending" } | { status: "done"; result: LoginResult };

export function App() {
  const [state, setState] = useState<State>({ status: "idle" });
  // La référence est sur le formulaire : les composants shadcn ne transmettent pas `ref` en React 18.
  const formRef = useRef<HTMLFormElement>(null);
  const passwordInput = () => formRef.current?.elements.namedItem("password") as HTMLInputElement | null;
  const pending = state.status === "pending";
  const failure = state.status === "done" && !state.result.ok ? state.result : null;
  const accepted = state.status === "done" && state.result.ok;
  const messageId = "login-message";

  // Les champs sont réactivés après l'envoi : le focus revient alors au mot de passe.
  useEffect(() => {
    if (failure) passwordInput()?.focus();
  }, [failure]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const data = new FormData(event.currentTarget);
    const credentials = {
      username: String(data.get("username") ?? ""),
      password: String(data.get("password") ?? ""),
    };
    // Le mot de passe ne survit pas à l'envoi : le champ est vidé aussitôt.
    const password = passwordInput();
    if (password) password.value = "";
    setState({ status: "pending" });
    const result = await submitLogin(credentials);
    setState({ status: "done", result });
  }

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
            {fr.login.title}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">{fr.login.access}</p>

          <form ref={formRef} onSubmit={onSubmit} className="mt-6 flex flex-col gap-5" aria-describedby={failure ? messageId : undefined}>
            <FieldGroup className="gap-4">
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
            </FieldGroup>

            {failure && (
              <Alert id={messageId} role="alert">
                <CircleAlertIcon />
                <AlertTitle>{fr.login.errorTitle}</AlertTitle>
                <AlertDescription>{loginErrorMessage(failure)}</AlertDescription>
              </Alert>
            )}
            {accepted && (
              <Alert role="status">
                <CircleCheckIcon />
                <AlertTitle>{fr.login.successTitle}</AlertTitle>
                <AlertDescription>{fr.login.success}</AlertDescription>
              </Alert>
            )}

            <Button type="submit" size="lg" disabled={pending}>
              {pending && <Spinner data-icon="inline-start" />}
              {pending ? fr.login.pending : fr.login.submit}
            </Button>
            <span className="sr-only" role="status">
              {pending ? fr.login.pending : ""}
            </span>
          </form>
        </section>
      </main>

      <footer className="text-sm text-muted-foreground">{fr.footer}</footer>
    </div>
  );
}
