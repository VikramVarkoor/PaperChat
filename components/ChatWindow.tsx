"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, FileText, Sparkles, Trash2, ChevronRight } from "lucide-react";
import { streamChat } from "@/lib/api";
import { Message, Document, SourceChunk } from "@/lib/types";
import MessageBubble from "./MessageBubble";

interface ChatWindowProps {
  document: Document;
  onClearDocument: () => void;
}

function generateId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

export default function ChatWindow({ document, onClearDocument }: ChatWindowProps) {

  const [messages, setMessages] = useState<Message[]>([
    {
      id: generateId(),
      role: "assistant",
      content: `I've read **${document.name}** and I'm ready to answer your questions.\n\nThe document has ${document.pageCount} pages and was split into ${document.chunkCount} searchable chunks. Ask me anything about its contents!`,
      timestamp: new Date().toISOString(),
      sources: [],
    },
  ]);

  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleTextareaInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const sendMessage = useCallback(async () => {
    const question = inputText.trim();
    if (!question || isLoading) return;

    setInputText("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setIsLoading(true);

    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: question,
      timestamp: new Date().toISOString(),
    };

    const assistantMessageId = generateId();
    const assistantPlaceholder: Message = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
      isStreaming: true,
      sources: [],
    };

    setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);

    await streamChat(
      {
        question,
        documentId: document.id,
        history: messages.filter((m) => !m.isStreaming).slice(-6).map((m) => ({ role: m.role, content: m.content })),
      },
      (token: string) => {
        setMessages((prev) =>
          prev.map((m) => m.id === assistantMessageId ? { ...m, content: m.content + token } : m)
        );
      },
      (sources: SourceChunk[]) => {
        setMessages((prev) =>
          prev.map((m) => m.id === assistantMessageId ? { ...m, sources } : m)
        );
      },
      () => {
        setMessages((prev) =>
          prev.map((m) => m.id === assistantMessageId ? { ...m, isStreaming: false } : m)
        );
        setIsLoading(false);
      },
      (error: Error) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessageId
              ? { ...m, content: `Sorry, something went wrong: ${error.message}`, isStreaming: false }
              : m
          )
        );
        setIsLoading(false);
      }
    );
  }, [inputText, isLoading, document.id, messages]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  return (
    <div className="flex flex-col h-screen">

      {/* ── Top Bar ── */}
      {/* Glassmorphism: semi-transparent background + backdrop blur + bottom border with gradient */}
      <div className="flex-shrink-0 flex items-center justify-between px-5 h-14 border-b border-gray-800/60 bg-[#0a0a12]/80 backdrop-blur-xl relative">
        {/* Very subtle violet glow at bottom edge of top bar */}
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-1/3 h-px bg-gradient-to-r from-transparent via-violet-500/30 to-transparent" />

        <div className="flex items-center gap-3 min-w-0">
          {/* Logo */}
          <div className="flex-shrink-0 w-7 h-7 rounded-lg bg-violet-600 flex items-center justify-center shadow-md shadow-violet-600/40">
            <Sparkles className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="text-sm font-semibold text-white tracking-tight hidden sm:block">PaperChat</span>

          <div className="w-px h-4 bg-gray-800 flex-shrink-0" />

          {/* Doc name */}
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex-shrink-0 w-6 h-6 rounded-md bg-red-500/10 border border-red-500/20 flex items-center justify-center">
              <FileText className="w-3 h-3 text-red-400" />
            </div>
            <p className="text-sm text-gray-400 truncate">{document.name}</p>
            <span className="flex-shrink-0 text-xs text-gray-600 hidden sm:block">
              · {document.pageCount}p · {document.chunkCount} chunks
            </span>
          </div>
        </div>

        <button
          onClick={onClearDocument}
          className="flex-shrink-0 flex items-center gap-1.5 text-xs text-gray-600 hover:text-gray-300 transition-colors ml-4 py-1.5 px-3 rounded-lg hover:bg-white/5 border border-transparent hover:border-gray-700/50"
        >
          <Trash2 className="w-3 h-3" />
          <span>New doc</span>
        </button>
      </div>

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto px-4 py-8">
        <div className="max-w-2xl mx-auto">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* ── Input Area ── */}
      <div className="flex-shrink-0 border-t border-gray-800/50 bg-[#0a0a12]/80 backdrop-blur-xl px-4 py-4">
        <div className="max-w-2xl mx-auto">

          {/* Suggestion chips */}
          {messages.length === 1 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {["What is the main topic?", "Summarize the key points", "What conclusions does it draw?"].map((s) => (
                <button
                  key={s}
                  onClick={() => { setInputText(s); textareaRef.current?.focus(); }}
                  className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-200 bg-white/3 hover:bg-white/6 border border-gray-800 hover:border-gray-600 rounded-full px-3 py-1.5 transition-all"
                >
                  <ChevronRight className="w-3 h-3 text-violet-500/60" />
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Input box */}
          <div className="relative flex items-end gap-2 bg-[#13131e] border border-gray-700/50 focus-within:border-violet-500/50 rounded-2xl px-4 py-3 transition-all duration-200 shadow-lg shadow-black/20">
            {/* Subtle inner glow on focus */}
            <div className="absolute inset-0 rounded-2xl bg-violet-500/0 focus-within:bg-violet-500/[0.02] transition-all pointer-events-none" />

            <textarea
              ref={textareaRef}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onInput={handleTextareaInput}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything about your document..."
              disabled={isLoading}
              rows={1}
              className="relative flex-1 bg-transparent text-sm text-gray-200 placeholder-gray-600 resize-none outline-none min-h-[22px] max-h-[160px] overflow-y-auto disabled:opacity-40"
            />

            <button
              onClick={sendMessage}
              disabled={!inputText.trim() || isLoading}
              className="relative flex-shrink-0 w-8 h-8 rounded-xl bg-violet-600 hover:bg-violet-500 active:bg-violet-700 disabled:bg-gray-800 disabled:cursor-not-allowed flex items-center justify-center transition-all shadow-md shadow-violet-600/30 disabled:shadow-none"
            >
              <Send className="w-3.5 h-3.5 text-white" />
            </button>
          </div>

          <p className="text-center text-[11px] text-gray-700/60 mt-2.5 tracking-wide">
            Groq Llama 3.3 · sentence-transformers · Chroma — answers grounded in your document
          </p>
        </div>
      </div>

    </div>
  );
}
