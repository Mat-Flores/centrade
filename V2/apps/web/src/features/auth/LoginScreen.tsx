import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { fr, loginErrorMessage } from "@/i18n/fr";
import { submitLogin, submitTotp, type LoginFailure } from "@/lib/login";
import { meKey } from "@/lib/session";
import { Button, Field } from "@/ui/ui";

type Step = "password" | "totp";
type State = { status: "idle" } | { status: "pending" } | { status: "failed"; failure: LoginFailure };

const messageId = "login-message";

/** Two-step login: password, then TOTP code (or recovery code). Secrets live only in the DOM field until sent. */
export function LoginScreen() {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>("password");
  const [state, setState] = useState<State>({ status: "idle" });
  const [returned, setReturned] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const field = (name: string) => formRef.current?.elements.namedItem(name) as HTMLInputElement | null;
  const pending = state.status === "pending";
  const failure = state.status === "failed" ? state.failure : null;
  const totp = step === "totp";

  // Focus goes to the field to fill when the step changes or a submit fails (never on the first display).
  useEffect(() => {
    if (failure) field(totp ? "code" : "password")?.focus();
    else if (totp || returned) field(totp ? "code" : "username")?.focus();
  }, [step, failure, returned]); // eslint-disable-line react-hooks/exhaustive-deps

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const data = new FormData(event.currentTarget);
    // The password and the code do not survive the submit: the field is emptied at once.
    const secret = field(totp ? "code" : "password");
    if (secret) secret.value = "";
    setState({ status: "pending" });
    if (!totp) {
      const result = await submitLogin({ username: String(data.get("username") ?? ""), password: String(data.get("password") ?? "") });
      if (result.ok) {
        setState({ status: "idle" });
        setStep("totp");
      } else setState({ status: "failed", failure: result });
      return;
    }
    const result = await submitTotp(String(data.get("code") ?? ""));
    if (result.ok) {
      // The session exists server side: /auth/me confirms it, and the shell shows.
      await queryClient.invalidateQueries({ queryKey: meKey });
      setState({ status: "idle" });
    } else setState({ status: "failed", failure: result });
  }

  const invalid = { "aria-invalid": failure ? true : undefined, "aria-describedby": failure ? messageId : undefined };
  const pendingText = totp ? fr.totp.pending : fr.login.pending;
  return (
    <main className="login">
      <div className="login-card">
        <span className="title">{fr.productName}</span>
        <form key={step} ref={formRef} className="panel" onSubmit={onSubmit} aria-labelledby="login-title" aria-describedby={failure ? messageId : undefined}>
          <h1 id="login-title">{totp ? fr.totp.title : fr.login.title}</h1>
          {totp ? (
            <>
              <p className="note-sm" style={{ margin: 0 }}>{fr.totp.help}</p>
              <Field label={fr.totp.code} required>
                <input className="input num" name="code" type="text" inputMode="text" autoComplete="one-time-code" autoCapitalize="characters" spellCheck={false} required disabled={pending} {...invalid} />
              </Field>
            </>
          ) : (
            <>
              <Field label={fr.login.username} required>
                <input className="input" name="username" type="text" autoComplete="username" autoCapitalize="none" spellCheck={false} required disabled={pending} {...invalid} />
              </Field>
              <Field label={fr.login.password} required>
                <input className="input" name="password" type="password" autoComplete="current-password" required disabled={pending} {...invalid} />
              </Field>
            </>
          )}
          {failure && (
            <div id={messageId} role="alert" className="notice loss">
              <span><b>{totp ? fr.totp.errorTitle : fr.login.errorTitle}.</b> {loginErrorMessage(failure, step)}</span>
            </div>
          )}
          <Button type="submit" variant="go" disabled={pending}>{pending ? pendingText : totp ? fr.totp.submit : fr.login.submit}</Button>
          {totp && (
            <Button variant="ghost" disabled={pending} onClick={() => { setState({ status: "idle" }); setStep("password"); setReturned(true); }}>
              {fr.totp.back}
            </Button>
          )}
          <span className="sr" role="status">{pending ? pendingText : ""}</span>
        </form>
        <p className="note-sm" style={{ margin: 0 }}>{fr.login.access}</p>
      </div>
    </main>
  );
}
