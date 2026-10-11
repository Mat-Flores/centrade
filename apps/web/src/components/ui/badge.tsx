import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"
import { Slot } from "radix-ui"

const badgeVariants = cva(
  "inline-flex h-7 w-fit shrink-0 items-center justify-center gap-1 rounded-md border border-transparent px-2.5 text-sm font-semibold whitespace-nowrap [&>svg]:pointer-events-none [&>svg]:size-3.5",
  {
    variants: {
      variant: {
        // Neutre : PAPER, états ordinaires.
        default: "border-border bg-card text-card-foreground",
        // Réservé au mode LIVE (jeton --live).
        live: "bg-live text-live-foreground",
        // Danger (MODE INCOHÉRENT) : rouge réservé aux états dangereux, contour et texte.
        danger: "border-live bg-background text-live",
        // État non observé : contour pointillé, jamais une valeur.
        unknown: "border-dashed border-input text-muted-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
