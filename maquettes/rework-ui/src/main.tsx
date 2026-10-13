import { createRoot } from "react-dom/client";
import "./theme/tokens.css";
import { startClock } from "./data/store";
import { App } from "./app/App";

startClock();
createRoot(document.getElementById("root")!).render(<App />);
