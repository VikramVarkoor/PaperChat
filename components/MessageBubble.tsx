"use client";

import { Message } from "@/lib/types";
import SourceCitation from "./SourceCitation";

interface MessageBubbleProps {
  message: Message;
}

// ── Typing Indicator ──────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 py-1">
      {[0, 160, 320].map((delay) => (
        <span
          key={delay}
          className="w-1.5 h-1.5 rounded-full bg-gray-500 animate-dot-bounce"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  );
}

// ── Markdown Renderer ─────────────────────────────────────────────────────────
// Splits on double-newlines first (paragraph breaks → visible gap between blocks)
// then handles single newlines within a paragraph as soft line breaks.

function renderInline(line: string): React.ReactNode[] {
  const segments: React.ReactNode[] = [];
  const pattern = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(line)) !== null) {
    if (match.index > lastIndex) segments.push(line.slice(lastIndex, match.index));
    if (match[2] !== undefined) {
      segments.push(<strong key={match.index} className="font-semibold text-white">{match[2]}</strong>);
    } else if (match[3] !== undefined) {
      segments.push(<em key={match.index} className="italic text-gray-300">{match[3]}</em>);
    } else if (match[4] !== undefined) {
      segments.push(
        <code key={match.index} className="text-xs font-mono bg-violet-500/10 text-violet-300 px-1.5 py-0.5 rounded border border-violet-500/20">
          {match[4]}
        </code>
      );
    }
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < line.length) segments.push(line.slice(lastIndex));
  return segments;
}

function renderMarkdown(text: string): React.ReactNode {
  const lines = text.split("\n");

  return (
    <span className="block">
      {lines.map((line, idx) => {
        // Empty line → spacer
        if (line.trim() === "") {
          return <span key={idx} className="block h-2" />;
        }

        // Bullet line — starts with * or - followed by a space
        const bulletMatch = line.match(/^(\*|-)\s+(.+)$/);
        if (bulletMatch) {
          return (
            <span key={idx} className="flex items-start gap-2 mb-2 last:mb-0">
              {/* mt-[8px] = (line-height 22px - diamond 6px) / 2 → vertically centred on first line */}
              <span className="flex-shrink-0 mt-[8px] w-1.5 h-1.5 rounded-sm bg-violet-500/70 rotate-45" />
              <span className="flex-1">{renderInline(bulletMatch[2])}</span>
            </span>
          );
        }

        // Numbered reference line — e.g. [1] Author...
        const refMatch = line.match(/^(\[\d+\])\s+(.+)$/);
        if (refMatch) {
          return (
            <span key={idx} className="flex items-start gap-2 mb-2 last:mb-0">
              <span className="flex-shrink-0 text-[11px] font-mono text-violet-400/70 bg-violet-500/10 border border-violet-500/20 px-1 py-0.5 rounded leading-none mt-0.5">
                {refMatch[1]}
              </span>
              <span className="flex-1 text-gray-300">{renderInline(refMatch[2])}</span>
            </span>
          );
        }

        // Regular line
        return (
          <span key={idx} className="block mb-1.5 last:mb-0">
            {renderInline(line)}
          </span>
        );
      })}
    </span>
  );
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isStreaming = message.isStreaming;

  return (
    <div className={`flex flex-col mb-6 ${isUser ? "items-end" : "items-start"}`}>

      {/* Role label */}
      <span className={`text-[11px] font-semibold mb-1.5 px-1 tracking-widest uppercase ${isUser ? "text-violet-400/60" : "text-gray-600"}`}>
        {isUser ? "You" : "PaperChat"}
      </span>

      {/* Bubble */}
      {isUser ? (
        /* User bubble — violet gradient */
        <div className="relative max-w-[80%] rounded-2xl rounded-tr-sm px-4 py-3 bg-gradient-to-br from-violet-600 to-violet-700 text-white shadow-lg shadow-violet-900/40">
          <p className="text-sm leading-relaxed">{message.content}</p>
        </div>
      ) : (
        /* AI bubble — dark card with left violet accent + subtle inner gradient */
        <div className="relative max-w-[80%] rounded-2xl rounded-tl-sm overflow-hidden shadow-lg shadow-black/30">
          {/* Left accent border */}
          <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-gradient-to-b from-violet-500/80 via-violet-500/30 to-transparent" />
          {/* Card body */}
          <div className="bg-gradient-to-br from-[#1a1a27] to-[#14141f] border border-gray-700/40 rounded-2xl rounded-tl-sm pl-4 pr-4 py-3">
            {isStreaming && message.content === "" ? (
              <TypingIndicator />
            ) : (
              <div className="text-sm leading-relaxed text-gray-200">
                {renderMarkdown(message.content)}
                {isStreaming && (
                  <span className="inline-block w-0.5 h-[14px] bg-violet-400 ml-0.5 align-middle animate-pulse rounded-full" />
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Source citations */}
      {!isUser && !isStreaming && message.sources && message.sources.length > 0 && (
        <div className="mt-2 w-full max-w-[80%]">
          <SourceCitation sources={message.sources} />
        </div>
      )}

      {/* Timestamp */}
      <span className="text-[11px] text-gray-700 mt-1.5 px-1">
        {formatTime(message.timestamp)}
      </span>

    </div>
  );
}
