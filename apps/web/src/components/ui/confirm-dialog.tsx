import { useEffect, useRef, type ReactNode } from "react"

import { cn } from "@/lib/utils"

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
