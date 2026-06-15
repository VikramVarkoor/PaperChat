/*
  app/page.tsx — The Main Page (route: "/")

  In Next.js App Router, every `page.tsx` inside `app/` maps to a URL.
  This file at `app/page.tsx` is served at the root URL "/".
  If you had `app/about/page.tsx`, it would be served at "/about". Simple.

  This page is what I call the "view controller" — it doesn't render much
  UI itself, but it decides WHICH component to show based on app state.

  The two states:
    1. No document loaded → show <FileUpload />
    2. Document loaded    → show <ChatWindow />

  This pattern (lifting state up to a parent, then passing it down as props)
  is fundamental to React. "Lift state up" means: put shared state in the
  closest common ancestor of all components that need it.

  IMPORTANT: This is also a Client Component because it uses useState.
  In Next.js, the rule is: if a component needs interactivity/hooks,
  add "use client". Otherwise, leave it out (default = Server Component).
*/

"use client";

import { useState } from "react";
import FileUpload from "@/components/FileUpload";
import ChatWindow from "@/components/ChatWindow";
import { Document } from "@/lib/types";
import { deleteDocument } from "@/lib/api";

export default function HomePage() {
  // The currently loaded document.
  // `null` means no document is loaded → show FileUpload.
  // A Document object means one is loaded → show ChatWindow.
  const [activeDocument, setActiveDocument] = useState<Document | null>(null);

  // ── Handlers ───────────────────────────────────────────────────────────────

  /**
   * Called by FileUpload when the document is processed and ready.
   * Switches the UI from upload view to chat view.
   */
  const handleDocumentReady = (document: Document) => {
    setActiveDocument(document);
  };

  /**
   * Called by ChatWindow when the user clicks "New doc".
   * Clears the current document from the backend (frees Chroma memory)
   * and returns to the upload screen.
   */
  const handleClearDocument = async () => {
    if (activeDocument) {
      // Fire and forget — if deletion fails on the backend it's not critical
      // (Chroma will just have a stale collection until the server restarts).
      deleteDocument(activeDocument.id).catch(console.error);
    }
    setActiveDocument(null);
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  //
  // This is a very clean pattern: a single conditional determines the entire
  // page content. React calls this "conditional rendering."
  // The `? :` ternary is the most common way to do it in JSX.

  return (
    <main>
      {activeDocument === null ? (
        <FileUpload onDocumentReady={handleDocumentReady} />
      ) : (
        <ChatWindow
          document={activeDocument}
          onClearDocument={handleClearDocument}
        />
      )}
    </main>
  );
}
