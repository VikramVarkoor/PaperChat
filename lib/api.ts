/*
  lib/api.ts — API Client

  This file is the ONLY place in the frontend that talks to the backend.
  All fetch() calls live here. Components import functions from this file
  and never call fetch() directly.

  WHY centralise API calls?
    - One place to change if a URL changes
    - Easy to add auth headers, error handling, logging in one spot
    - Components stay clean — they just call `uploadDocument(file)` and
      get back a nice typed result, they don't care about HTTP

  HOW streaming works (important for the chat feature):
    Normal fetch: send request → wait → get full response → display.
    Streaming fetch: send request → start receiving chunks of text
    one-by-one → display each chunk as it arrives.

    The AI generates text token-by-token. Without streaming, the user
    stares at a blank screen for 5-10 seconds then the full answer appears.
    With streaming, words appear one-by-one as the AI writes them — much
    better UX and feels "alive."

    The backend sends responses as SSE (Server-Sent Events) — a simple
    protocol where the server keeps the connection open and sends lines like:
      data: {"token": "The"}
      data: {"token": " answer"}
      data: {"token": " is..."}
      data: [DONE]
*/

import {
  ChatRequest,
  Document,
  SourceChunk,
  UploadResponse,
} from "./types";

// The base URL for all API calls. Because next.config.js rewrites
// /api/py/* → http://localhost:8000/*, we use this prefix everywhere.
// In production you'd set this via an environment variable.
const API_BASE = "/api/py";

// ── Document Upload ───────────────────────────────────────────────────────

/**
 * Uploads a PDF file to the backend for processing.
 *
 * We use FormData to send binary file data over HTTP.
 * FormData is the same mechanism as a browser <form> with enctype="multipart/form-data".
 * The backend reads the file from request.files["file"].
 *
 * @param file - The File object from the browser's file picker
 * @param onProgress - Optional callback to report upload progress 0–100
 * @returns The Document object created by the backend
 */
export async function uploadDocument(
  file: File,
  onProgress?: (percent: number) => void
): Promise<UploadResponse> {
  // FormData lets us attach a file to a POST request.
  // Think of it as filling out an HTML form and hitting submit.
  const formData = new FormData();
  formData.append("file", file); // "file" must match what FastAPI expects

  // We use XMLHttpRequest instead of fetch here ONLY because we want
  // upload progress events. The native fetch() API doesn't support
  // upload progress (as of 2024). For everything else we use fetch.
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    // Track upload progress (bytes sent / total bytes)
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && onProgress) {
        const percent = Math.round((event.loaded / event.total) * 100);
        onProgress(percent);
      }
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data: UploadResponse = JSON.parse(xhr.responseText);
          resolve(data);
        } catch {
          reject(new Error("Invalid JSON response from server"));
        }
      } else {
        // Try to parse error message from response body
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || "Upload failed"));
        } catch {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      }
    });

    xhr.addEventListener("error", () => reject(new Error("Network error during upload")));
    xhr.addEventListener("abort", () => reject(new Error("Upload aborted")));

    xhr.open("POST", `${API_BASE}/upload`);
    xhr.send(formData);
  });
}

// ── Chat with Streaming ───────────────────────────────────────────────────

/**
 * Sends a question to the backend and streams the AI's response.
 *
 * This function uses the Fetch API with a ReadableStream to process
 * the response incrementally as it arrives.
 *
 * @param request - The chat request (question + documentId)
 * @param onToken - Called with each new token as it streams in
 * @param onSources - Called once with the source chunks when streaming ends
 * @param onDone - Called when the full response is complete
 * @param onError - Called if something goes wrong
 */
export async function streamChat(
  request: ChatRequest,
  onToken: (token: string) => void,
  onSources: (sources: SourceChunk[]) => void,
  onDone: () => void,
  onError: (error: Error) => void
): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: {
        // Tell the server we're sending JSON
        "Content-Type": "application/json",
        // Tell the server we can handle a streaming text response
        Accept: "text/event-stream",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Server error: ${response.status}`);
    }

    // `response.body` is a ReadableStream<Uint8Array>.
    // The data arrives as raw bytes (Uint8Array), so we need a
    // TextDecoder to convert bytes → string.
    const reader = response.body?.getReader();
    const decoder = new TextDecoder("utf-8");

    if (!reader) {
      throw new Error("No response body");
    }

    // This loop reads chunks from the stream until it's done.
    // Each chunk may contain one or more SSE lines.
    while (true) {
      // `done` = true when the stream is finished
      // `value` = a Uint8Array of bytes for this chunk
      const { done, value } = await reader.read();

      if (done) {
        onDone();
        break;
      }

      // Decode bytes to text
      const chunk = decoder.decode(value, { stream: true });

      // SSE format: each event is "data: {json}\n\n"
      // Split by newlines and process each line
      const lines = chunk.split("\n");

      for (const line of lines) {
        // Skip empty lines and comment lines (SSE uses ": comment" syntax)
        if (!line.trim() || line.startsWith(":")) continue;

        // All SSE data lines start with "data: "
        if (line.startsWith("data: ")) {
          const data = line.slice(6); // Remove "data: " prefix

          // The special [DONE] signal means the stream is finished
          if (data === "[DONE]") {
            onDone();
            return;
          }

          try {
            const parsed = JSON.parse(data);

            // Token events carry the next word/piece of text
            if (parsed.token !== undefined) {
              onToken(parsed.token);
            }

            // Sources event carries the retrieved document chunks
            if (parsed.sources) {
              onSources(parsed.sources);
            }

            // Error events from the backend
            if (parsed.error) {
              throw new Error(parsed.error);
            }
          } catch (parseError) {
            // If JSON parse fails, it might just be a partial chunk —
            // safe to skip, the next chunk will have complete data
            if (parseError instanceof SyntaxError) continue;
            throw parseError;
          }
        }
      }
    }
  } catch (error) {
    onError(error instanceof Error ? error : new Error("Unknown error"));
  }
}

// ── Utilities ─────────────────────────────────────────────────────────────

/**
 * Deletes a document from the backend (clears it from Chroma vector DB).
 * Called when user clicks "Upload new document".
 */
export async function deleteDocument(documentId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/documents/${documentId}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error(`Failed to delete document: ${response.status}`);
  }
}

/**
 * Health check — ping the backend to see if it's running.
 * Useful for showing a "backend offline" warning in the UI.
 */
export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/health`, {
      // Short timeout so we fail fast if the backend is down
      signal: AbortSignal.timeout(3000),
    });
    return response.ok;
  } catch {
    return false;
  }
}
