import { createContext, useContext } from "react";

import type { Degradation } from "@/lib/cockpit";

/** Degraded mode (silent stream, failing health), computed once by the shell, read by the screens. */
const Context = createContext<Degradation>({ degraded: false, causes: [] });
export const DegradationProvider = Context.Provider;
export const useDegradation = (): Degradation => useContext(Context);
