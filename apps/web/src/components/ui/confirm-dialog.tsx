import { useEffect, useRef, type ReactNode } from "react"

import { cn } from "@/lib/utils"

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([hidden]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])'

/** Tab au bout de la fenêtre revient au début (et Maj+Tab à la fin) : sans cela le focus sort vers le document puis la barre du navigateur. */
function wrapTab(event: React.KeyboardEvent<HTMLDialogElement>) {
  if (event.key !== "Tab") return
  const items = [...event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.offsetParent !== null)
  const first = items[0]
  const last = items[items.length - 1]
  if (!first || !last) return
  const active = document.activeElement
  if (event.shiftKey && (active === first || active === event.currentTarget)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

/**
 * Fenêtre de confirmation sur l'élément natif <dialog> (showModal) : focus piégé, fond inerte, Échap,
 * retour du focus à l'élément d'origine. Pas de Radix ici : son verrou de défilement injecte une
 * balise <style>, que la CSP stricte (`style-src 'self'`) refuse.
 * Source : https://developer.mozilla.org/docs/Web/API/HTMLDialogElement/showModal
 */
export function ConfirmDialog({
  titleId,
  descriptionId,
  busy,
  onClose,
  className,
  children,
}: {
  titleId: string
  descriptionId: string
  /** Envoi en cours : Échap ne ferme pas la fenêtre. */
  busy: boolean
  onClose: () => void
  className?: string
  children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    dialog.showModal()
    dialog.querySelector<HTMLElement>("[data-autofocus]")?.focus()
    // Le parent la démonte : le focus revient à l'élément qui l'avait avant l'ouverture.
    return () => opener?.focus()
  }, [])

  return (
    <dialog
      ref={ref}
      role="alertdialog"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onKeyDown={wrapTab}
      onCancel={(event) => {
        event.preventDefault()
        if (!busy) onClose()
      }}
      className={cn(
        "m-auto w-[calc(100%-2rem)] max-w-lg rounded-xl border bg-card p-6 text-card-foreground shadow-panel backdrop:bg-foreground/40",
        className
      )}
    >
      <div className="flex flex-col gap-4">{children}</div>
    </dialog>
  )
}
