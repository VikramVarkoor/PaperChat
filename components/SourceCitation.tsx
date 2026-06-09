"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, BookOpen } from "lucide-react";
import { SourceChunk } from "@/lib/types";

interface SourceCitationProps {
  sources: SourceChunk[];
}

function getScoreStyle(score: number) {
  if (score >= 0.85) return { dot: "bg-emerald-400", text: "text-emerald-400", label: "Strong" };
  if (score >= 0.70) return { dot: "bg-yellow-400",  text: "text-yellow-400",  label: "Good" };
  return                { dot: "bg-orange-400",  text: "text-orange-400",  label: "Weak" };
}

export default function SourceCitation({ sources }: SourceCitationProps) {
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [expandedIndices, setExpandedIndices] = useState<Set<number>>(new Set());

  if (sources.length === 0) return null;

  const toggleSource = (index: number) => {
    const next = new Set(expandedIndices);
    next.has(index) ? next.delete(index) : next.add(index);
    setExpandedIndices(next);
  };

  return (
    <div className="rounded-xl overflow-hidden border border-gray-700/30 bg-[#0f0f1a]">

      {/* Header toggle */}
      <button
        onClick={() => setIsPanelOpen(!isPanelOpen)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-white/3 transition-colors text-left group"
      >
        <div className="flex items-center gap-2">
          <BookOpen className="w-3.5 h-3.5 text-violet-400/60" />
          <span className="text-xs text-gray-500 group-hover:text-gray-400 transition-colors">
            {sources.length} source{sources.length !== 1 ? "s" : ""} retrieved
          </span>
          {/* Score dots preview */}
          <div className="flex items-center gap-1">
            {sources.map((s, i) => {
              const style = getScoreStyle(s.score);
              return <span key={i} className={`w-1.5 h-1.5 rounded-full ${style.dot} opacity-60`} />;
            })}
          </div>
        </div>
        {isPanelOpen
          ? <ChevronUp className="w-3.5 h-3.5 text-gray-600" />
          : <ChevronDown className="w-3.5 h-3.5 text-gray-600" />
        }
      </button>

      {/* Source list */}
      {isPanelOpen && (
        <div className="border-t border-gray-700/30">
          {sources.map((source, index) => {
            const isExpanded = expandedIndices.has(index);
            const style = getScoreStyle(source.score);

            return (
              <div key={index} className="border-b border-gray-800/40 last:border-b-0">

                {/* Source row */}
                <button
                  onClick={() => toggleSource(index)}
                  className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-white/3 transition-colors text-left"
                >
                  {/* Score indicator dot */}
                  <span className={`flex-shrink-0 w-1.5 h-1.5 rounded-full ${style.dot}`} />

                  {/* Page badge */}
                  <span className="flex-shrink-0 text-[11px] font-mono font-medium text-gray-500 bg-gray-800/60 px-1.5 py-0.5 rounded">
                    p.{source.page}
                  </span>

                  {/* Score */}
                  <span className={`flex-shrink-0 text-[11px] font-medium ${style.text}`}>
                    {(source.score * 100).toFixed(0)}% {style.label}
                  </span>

                  {/* Text preview */}
                  <span className="text-xs text-gray-600 truncate flex-1">
                    {source.content.slice(0, 55)}...
                  </span>

                  {isExpanded
                    ? <ChevronUp className="w-3 h-3 text-gray-700 flex-shrink-0" />
                    : <ChevronDown className="w-3 h-3 text-gray-700 flex-shrink-0" />
                  }
                </button>

                {/* Expanded chunk text */}
                {isExpanded && (
                  <div className="px-3 pb-3">
                    <div className="bg-[#0a0a12] border border-gray-800/60 rounded-lg p-3">
                      <p className="text-xs text-gray-400 font-mono leading-relaxed whitespace-pre-wrap">
                        {source.content}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
