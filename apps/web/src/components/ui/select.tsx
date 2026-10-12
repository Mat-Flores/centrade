import * as React from "react"
import { cn } from "@/lib/utils"

/** Liste déroulante native : clavier, lecteur d'écran et tablette gratuits. Même gabarit qu'`Input`. */
function Select({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="select"
      className={cn(
        "h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 py-1 text-base transition-colors outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-60",
        className
      )}
      {...props}
    />
  )
}

export { Select }
