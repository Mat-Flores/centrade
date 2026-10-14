import { Menu, type MenuItem } from "@/app/Menu";
import { navigate, href, ALL_TAB } from "@/app/router";
import { fr } from "@/i18n/fr";
import { CONFIRMED, type RowAction } from "@/lib/instance-row";
import type { ActionType, Instance } from "@/lib/instances";
import { Button } from "@/ui/ui";

import type { ConfirmedAction } from "./ActionDialog";

type Confirm = (instanceId: string, action: ConfirmedAction) => void;

/** The row's one button (from the observed state), plus the "more" menu for the actions that reduce risk. */
export function RowActions({ instance, action, canAct, sending, onSend, onConfirm }: { instance: Instance; action: RowAction; canAct: boolean; sending: boolean; onSend: (action: ActionType) => void; onConfirm: Confirm }) {
  const t = fr.instances;
  const open = () => navigate(href({ page: "instance", id: instance.id, tab: ALL_TAB }));

  const press = (a: ActionType) => (CONFIRMED.has(a) ? onConfirm(instance.id, a as ConfirmedAction) : onSend(a));
  const more: MenuItem[] = [
    { label: t.moreActions.flatten, hint: t.moreHint.flatten, onSelect: () => onConfirm(instance.id, "flatten"), danger: true },
    { label: t.moreActions.stop, hint: t.moreHint.stop, onSelect: () => onConfirm(instance.id, "stop"), danger: true },
  ];

  let button;
  if (action.kind === "open") button = <Button small data-tip={t.rowActionTips.open} onClick={open}>{t.rowActions.open}</Button>;
  else if (action.kind === "starting") button = <Button small aria-disabled="true">{t.rowActions.starting}</Button>;
  else {
    const a = action.action;
    button = (
      <Button
        small
        // aria-disabled keeps the button focusable; the reason is on hover and read with it.
        aria-disabled={action.enabled && !sending ? undefined : true}
        data-tip={action.enabled ? t.rowActionTips[a as "start"] : (action.reason ?? undefined)}
        onClick={() => action.enabled && !sending && press(a)}
      >
        {t.rowActions[a as "start"]}
      </Button>
    );
  }
  return (
    <>
      {button}
      {canAct && <Menu ghost btnClassName="icon" ariaLabel={t.more(instance.name)} label={<span aria-hidden="true">⋯</span>} items={more} />}
    </>
  );
}
