import { createRoot } from "react-dom/client";
import "./theme/tokens.css";
import { startClock } from "./data/store";
import { App } from "./app/App";
import { installTips } from "./ui/tips";
import { installScrollbars } from "./ui/scrollbars";

startClock();
installTips();
installScrollbars();
createRoot(document.getElementById("root")!).render(<App />);
