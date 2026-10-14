import { Component, type ErrorInfo, type ReactNode } from "react";

import { fr } from "@/i18n/fr";
import { Button } from "@/ui/ui";

/** A screen that throws while rendering shows a sober error, never a blank page. Reload is the only way out. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="empty">
        <strong>{fr.crash.title}</strong>
        <p style={{ margin: 0, maxWidth: 420 }}>{fr.crash.body}</p>
        <Button onClick={() => window.location.reload()}>{fr.crash.reload}</Button>
      </div>
    );
  }
}
