import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/app/App";
import { applyTheme } from "@/app/theme/theme";
import "@/app/theme/tokens.css";
import { queryClient } from "@/lib/session";
import { installScrollbars } from "@/ui/scrollbars";
import { installTips } from "@/ui/tips";

applyTheme();
installTips();
installScrollbars();
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
