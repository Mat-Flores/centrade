import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import type { Command } from "../../data/types";
import { Button } from "../../ui/ui";

gsap.registerPlugin(useGSAP);
const LABEL = { lancement: "Lancement", verification: "Vérification", actif: "Actif" } as const;
const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Les trois étapes du démarrage. Une étape n'est cochée que lorsqu'elle est constatée (statut « ok »). */
export function StartStepper({ cmd, onSeen }: { cmd: Command; onSeen: () => void }) {
  const root = useRef<HTMLOListElement>(null);
  const tl = useRef<gsap.core.Timeline | null>(null);
  const done = useRef(new Set<string>());
  const steps = cmd.steps ?? [];
  const okKey = steps.map((x) => x.status).join("|");

  // Une seule timeline par démarrage : chaque étape constatée y ajoute son remplissage puis son trait (≤ 400 ms).
  useGSAP(() => {
    tl.current ??= gsap.timeline();
    steps.forEach((st, k) => {
      if (st.status !== "ok" || done.current.has(st.step)) return;
      done.current.add(st.step);
      const fill = `[data-fill="${st.step}"]`;
      const line = `[data-line="${st.step}"]`;
      if (reduced()) { gsap.set([fill, line], { scale: 1 }); return; }
      tl.current!.to(fill, { scale: 1, duration: 0.18, ease: "power3.out" });
      if (k < steps.length - 1) tl.current!.to(line, { scaleX: 1, duration: 0.2, ease: "power3.out" });
    });
    return () => { tl.current = null; done.current.clear(); };
  }, { scope: root, dependencies: [okKey] });

  const failed = steps.find((x) => x.status === "echec");
  return (
    <div className="in-stepper" role="group" aria-label="Séquence de démarrage" aria-live="polite">
      <ol ref={root} className="in-steps">
        {steps.map((st, k) => (
          <li key={st.step} className={`in-step is-${st.status}`}>
            <div className="in-step-h">
              <span className="in-mark" aria-hidden="true"><i data-fill={st.step} /></span>
              <b>{LABEL[st.step]}</b>
              <span className="xs faint">{{ attente: "en attente", en_cours: "en cours", ok: "constaté", echec: "bloqué" }[st.status]}</span>
              {k < steps.length - 1 && <span className="in-line" aria-hidden="true"><i data-line={st.step} /></span>}
            </div>
            {st.status === "echec" && st.detail && <div className="xs dn in-step-d">{st.detail}</div>}
            {st.status === "ok" && st.step === "verification" && st.detail && (
              <ul className="xs dim in-checks">{st.detail.split("\n").map((l) => <li key={l}>{l}</li>)}</ul>
            )}
          </li>
        ))}
      </ol>
      <span className="sp" />
      {failed && <span className="small dn in-fail">Démarrage incomplet : les achats restent fermés.</span>}
      {cmd.status !== "en_cours" && <Button small onClick={onSeen}>Vu</Button>}
    </div>
  );
}
