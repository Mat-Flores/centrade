import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState, type FormEvent } from "react";

import { ALL_TAB, href, navigate } from "@/app/router";
import { fr } from "@/i18n/fr";
import { accountsQuery, paperAccounts } from "@/lib/accounts";
import { ApiError } from "@/lib/api";
import { applyStreamMessage } from "@/lib/cockpit";
import { deployPaper, instancesKey, isValidInstanceName, type DeployPaperBody } from "@/lib/instances";
import { fieldsFromSchema, initialValues, validateParams } from "@/lib/params-form";
import { approvedVersions, strategiesQuery, versionsQuery } from "@/lib/strategies";
import { Button, Dialog, Field, SimTag } from "@/ui/ui";

import { refusal } from "./errors";
import { ParamInput } from "./ParamInput";

const t = fr.instances.create;

/** Form body: always paper, nothing is sent before every field passes the same checks as the API. */
function CreateForm({ formId, pending, onSubmit }: { formId: string; pending: boolean; onSubmit: (body: DeployPaperBody) => void }) {
  const strategies = useQuery(strategiesQuery);
  const accounts = useQuery(accountsQuery);
  const [name, setName] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [shown, setShown] = useState(false); // errors only show after a first attempt

  const versions = useQuery({ ...versionsQuery(strategyId), enabled: strategyId !== "" });
  const approved = approvedVersions(versions.data?.items ?? []);
  const version = approved.find((v) => v.id === versionId);
  const { fields, unsupported } = fieldsFromSchema(version?.manifest.params_schema);
  const paper = paperAccounts(accounts.data?.items ?? []);

  const checked = validateParams(fields, values);
  const nameOk = isValidInstanceName(name.trim());
  const valid = nameOk && version !== undefined && accountId !== "" && Object.keys(checked.errors).length === 0;

  const pickStrategy = (id: string) => { setStrategyId(id); setVersionId(""); setValues({}); };
  const pickVersion = (id: string) => {
    setVersionId(id);
    const v = approved.find((x) => x.id === id);
    setValues(v ? initialValues(fieldsFromSchema(v.manifest.params_schema).fields) : {});
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setShown(true);
    if (!valid || pending || !version) return;
    onSubmit({ name: name.trim(), params: checked.values, strategy_version_id: version.id, account_id: accountId });
  };

  return (
    <form id={formId} onSubmit={submit} noValidate className="form-grid" aria-label={t.title}>
      <Field label={t.name} required hint={t.nameHint} error={shown && !nameOk ? t.nameInvalid : undefined}>
        <input className="input" value={name} disabled={pending} autoComplete="off" spellCheck={false} aria-invalid={shown && !nameOk ? true : undefined} onChange={(e) => setName(e.target.value)} />
      </Field>

      <div className="form-grid two">
        <Field label={t.strategy} required error={shown && strategyId === "" ? t.strategyInvalid : undefined} hint={strategies.isSuccess && strategies.data.items.length === 0 ? t.noStrategy : undefined}>
          <select className="select" value={strategyId} disabled={pending || !strategies.isSuccess || strategies.data.items.length === 0} onChange={(e) => pickStrategy(e.target.value)}>
            <option value="">{t.strategyNone}</option>
            {(strategies.data?.items ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
        <Field label={t.version} required error={shown && strategyId !== "" && version === undefined ? t.versionInvalid : undefined} hint={strategyId !== "" && versions.isSuccess && approved.length === 0 ? t.noVersion : undefined}>
          <select className="select" value={versionId} disabled={pending || strategyId === "" || approved.length === 0} onChange={(e) => pickVersion(e.target.value)}>
            <option value="">{t.versionNone}</option>
            {approved.map((v) => <option key={v.id} value={v.id}>{t.versionLabel(v.version)}</option>)}
          </select>
        </Field>
      </div>

      <Field label={t.account} required error={shown && accountId === "" ? t.accountInvalid : undefined} hint={accounts.isSuccess && paper.length === 0 ? t.noAccount : undefined}>
        <select className="select" value={accountId} disabled={pending || paper.length === 0} onChange={(e) => setAccountId(e.target.value)}>
          <option value="">{t.accountNone}</option>
          {paper.map((a) => <option key={a.id} value={a.id}>{t.accountLabel(a.label, a.currency)}</option>)}
        </select>
      </Field>

      {version && (
        <fieldset className="fieldset">
          <legend>{t.params}</legend>
          {fields.length === 0 && <span className="quiet">{t.noParams}</span>}
          {fields.map((f) => (
            <ParamInput key={f.key} f={f} value={values[f.key] ?? ""} error={shown ? checked.errors[f.key] : undefined} disabled={pending} onChange={(v) => setValues({ ...values, [f.key]: v })} />
          ))}
          {unsupported.length > 0 && <span className="quiet">{t.unsupported(unsupported.join(", "))}</span>}
        </fieldset>
      )}

      {(strategies.isError || accounts.isError || versions.isError) && <div role="alert" className="inline-err">{t.choicesError}</div>}
      <p className="notice"><SimTag /><span>{t.paperOnly}</span></p>
      {shown && !valid && <div role="alert" className="inline-err">{t.fix}</div>}
    </form>
  );
}

/** Creation is always dry-run (paper); live goes through promotion. The server's refusal is shown in full. */
export function CreateInstanceDialog({ open, onClose, degraded }: { open: boolean; onClose: () => void; degraded: boolean }) {
  const qc = useQueryClient();
  const formId = useId();
  // The idempotency key follows the request: a retry of the same body replays it, another body gets its own.
  const attempt = useRef<{ sig: string; key: string } | null>(null);

  const deploy = useMutation({
    mutationFn: (body: DeployPaperBody) => {
      const sig = JSON.stringify(body);
      if (attempt.current?.sig !== sig) attempt.current = { sig, key: crypto.randomUUID() };
      return deployPaper(body, attempt.current.key);
    },
    onSuccess: (instance) => {
      attempt.current = null;
      applyStreamMessage(qc, { event: "instance", server_time: instance.server_time, instance });
      void qc.invalidateQueries({ queryKey: instancesKey });
      onClose();
      navigate(href({ page: "instance", id: instance.id, tab: ALL_TAB }));
    },
  });

  const error = deploy.error;
  const conflict = error instanceof ApiError && error.status === 409;
  const failure = deploy.isError ? refusal(error, t.errorFallback) : null;
  const close = () => { deploy.reset(); onClose(); };

  return (
    <Dialog
      open={open}
      wide
      onClose={close}
      title={t.title}
      foot={
        <>
          <Button onClick={close}>{t.cancel}</Button>
          <Button variant="go" type="submit" form={formId} disabled={deploy.isPending || degraded}>{deploy.isPending ? t.pending : t.submit}</Button>
        </>
      }
    >
      {degraded && <div role="status" className="notice">{t.degraded}</div>}
      <CreateForm formId={formId} pending={deploy.isPending} onSubmit={(body) => deploy.mutate(body)} />
      {failure && (
        <div role="alert" className="inline-err">
          <strong>{t.errorTitle}</strong> {conflict ? t.errorConflict : failure.text}
          {failure.reasons.length > 0 && (
            <>
              {" "}{t.reasonsIntro}
              <ul>{failure.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </>
          )}
        </div>
      )}
    </Dialog>
  );
}
