import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { queryClient } from "@/lib/session";

// Placeholder shell: the next batch replaces it with the real application.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <div>Centrade</div>
    </QueryClientProvider>
  </StrictMode>,
);
