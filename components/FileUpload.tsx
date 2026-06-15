"use client";

import { useState, useRef, useCallback } from "react";
import { UploadCloud, FileText, X, CheckCircle, Loader2, AlertCircle, Sparkles } from "lucide-react";
import { uploadDocument } from "@/lib/api";
import { Document, IngestionStatus } from "@/lib/types";

interface FileUploadProps {
  onDocumentReady: (document: Document) => void;
}

const PIPELINE_STEPS = [
  { id: "upload",  label: "Uploading file",              detail: "Sending to server" },
  { id: "extract", label: "Extracting text",             detail: "Reading PDF pages" },
  { id: "chunk",   label: "Splitting into chunks",       detail: "Creating ~500 token segments" },
  { id: "embed",   label: "Generating embeddings",       detail: "Converting text to vectors" },
  { id: "store",   label: "Indexing vector database",    detail: "Storing in Chroma" },
] as const;

export default function FileUpload({ onDocumentReady }: FileUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState(-1);
  const [status, setStatus] = useState<IngestionStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = (f: File): string | null => {
    if (f.type !== "application/pdf") return "Only PDF files are supported.";
    if (f.size > 20 * 1024 * 1024) return "File is too large. Maximum size is 20MB.";
    return null;
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setIsDragging(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) handleFileSelected(droppedFile);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFileSelected = (selectedFile: File) => {
    setErrorMessage(null);
    const err = validateFile(selectedFile);
    if (err) { setErrorMessage(err); return; }
    setFile(selectedFile);
  };

  const handleUpload = async () => {
    if (!file) return;
    setStatus("uploading");
    setCurrentStep(0);
    setErrorMessage(null);

    try {
      const response = await uploadDocument(file, (percent) => {
        setUploadProgress(percent);
        if (percent === 100) {
          setStatus("processing");
          setCurrentStep(1);
          setTimeout(() => setCurrentStep(2), 1000);
          setTimeout(() => setCurrentStep(3), 2200);
          setTimeout(() => setCurrentStep(4), 3400);
        }
      });
      await new Promise((r) => setTimeout(r, 600));
      setStatus("ready");
      onDocumentReady(response.document);
    } catch (error) {
      setStatus("error");
      setErrorMessage(error instanceof Error ? error.message : "Upload failed. Please try again.");
    }
  };

  const handleReset = () => {
    setFile(null); setStatus("idle"); setUploadProgress(0);
    setCurrentStep(-1); setErrorMessage(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-[#0a0a12] px-6">
      {/* Subtle background glow */}
      <div className="pointer-events-none fixed inset-0 flex items-center justify-center overflow-hidden">
        <div className="w-[700px] h-[700px] rounded-full bg-violet-600/5 blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">

        {/* ── Logo & Header ── */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 mb-6">
            <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center shadow-lg shadow-violet-600/30">
              <Sparkles className="w-4 h-4 text-white" />
            </div>
            <span className="text-white font-semibold text-lg tracking-tight">PaperChat</span>
          </div>
          <h1 className="text-3xl font-bold text-white mb-3 tracking-tight">
            Chat with any document
          </h1>
          <p className="text-gray-500 text-sm leading-relaxed">
            Upload a PDF and ask questions. Answers are sourced directly from your document.
          </p>
        </div>

        {/* ── IDLE: no file ── */}
        {status === "idle" && !file && (
          <>
            <div
              onClick={() => fileInputRef.current?.click()}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`
                relative rounded-2xl border-2 border-dashed p-10 text-center cursor-pointer
                transition-all duration-200 group
                ${isDragging
                  ? "border-violet-500 bg-violet-500/8"
                  : "border-gray-800 bg-gray-900/30 hover:border-gray-700 hover:bg-gray-900/50"
                }
              `}
            >
              <div className={`
                inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-4
                transition-all duration-200
                ${isDragging ? "bg-violet-500/15 scale-110" : "bg-gray-800/60 group-hover:bg-gray-800"}
              `}>
                <UploadCloud className={`w-6 h-6 transition-colors ${isDragging ? "text-violet-400" : "text-gray-500 group-hover:text-gray-400"}`} />
              </div>
              <p className="text-gray-300 font-medium text-sm mb-1">
                {isDragging ? "Drop it here" : "Drop your PDF here"}
              </p>
              <p className="text-gray-600 text-xs mb-5">or click to browse your files</p>
              <span className="inline-flex items-center gap-1.5 text-xs text-gray-600 bg-gray-800/60 border border-gray-700/50 px-3 py-1.5 rounded-full">
                <FileText className="w-3 h-3" />
                PDF only · Max 20MB
              </span>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileSelected(f); }}
              />
            </div>
            {errorMessage && (
              <div className="mt-3 flex items-center gap-2 text-red-400/80 text-xs px-1">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                <span>{errorMessage}</span>
              </div>
            )}
          </>
        )}

        {/* ── IDLE: file selected ── */}
        {status === "idle" && file && (
          <div className="rounded-2xl border border-gray-800 bg-gray-900/40 overflow-hidden">
            <div className="p-5 flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-red-500/10 border border-red-500/20 flex items-center justify-center flex-shrink-0">
                <FileText className="w-5 h-5 text-red-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-white text-sm font-medium truncate">{file.name}</p>
                <p className="text-gray-500 text-xs">{(file.size / (1024 * 1024)).toFixed(1)} MB · PDF</p>
              </div>
              <button onClick={handleReset} className="w-7 h-7 rounded-lg bg-gray-800 hover:bg-gray-700 flex items-center justify-center transition-colors flex-shrink-0">
                <X className="w-3.5 h-3.5 text-gray-400" />
              </button>
            </div>
            <div className="px-5 pb-5">
              <button
                onClick={handleUpload}
                className="w-full py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold transition-colors shadow-lg shadow-violet-600/20"
              >
                Process document
              </button>
            </div>
          </div>
        )}

        {/* ── UPLOADING / PROCESSING ── */}
        {(status === "uploading" || status === "processing") && (
          <div className="rounded-2xl border border-gray-800 bg-gray-900/40 overflow-hidden">
            <div className="p-5 flex items-center gap-3 border-b border-gray-800/60">
              <div className="w-10 h-10 rounded-xl bg-red-500/10 border border-red-500/20 flex items-center justify-center flex-shrink-0">
                <FileText className="w-5 h-5 text-red-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-white text-sm font-medium truncate">{file?.name}</p>
                <p className="text-gray-500 text-xs">
                  {status === "uploading" ? `Uploading... ${uploadProgress}%` : "Processing document..."}
                </p>
              </div>
            </div>

            {/* Progress bar */}
            <div className="px-5 pt-4 pb-1">
              <div className="w-full h-0.5 bg-gray-800 rounded-full overflow-hidden">
                {status === "uploading" ? (
                  <div className="h-full bg-violet-500 rounded-full transition-all duration-300" style={{ width: `${uploadProgress}%` }} />
                ) : (
                  <div className="h-full bg-violet-500 rounded-full animate-pulse w-full" />
                )}
              </div>
            </div>

            {/* Steps */}
            <div className="px-5 pt-4 pb-5 space-y-3.5">
              {PIPELINE_STEPS.map((step, index) => {
                const isDone    = index < currentStep;
                const isActive  = index === currentStep;
                const isPending = index > currentStep;

                return (
                  <div key={step.id} className={`flex items-start gap-3 transition-all duration-300 ${isPending ? "opacity-25" : "opacity-100"}`}>
                    <div className="w-4 h-4 flex items-center justify-center flex-shrink-0 mt-0.5">
                      {isDone   && <CheckCircle className="w-4 h-4 text-emerald-400" />}
                      {isActive && <Loader2 className="w-4 h-4 text-violet-400 animate-spin" />}
                      {isPending && <div className="w-1.5 h-1.5 rounded-full bg-gray-700 mt-1" />}
                    </div>
                    <div>
                      <p className={`text-xs font-medium leading-none ${isDone ? "text-emerald-400" : isActive ? "text-gray-200" : "text-gray-600"}`}>
                        {step.label}
                      </p>
                      {isActive && (
                        <p className="text-xs text-gray-600 mt-1">{step.detail}</p>
                      )}
                    </div>
                    {isDone && <span className="ml-auto text-xs text-emerald-600/70 font-mono">done</span>}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── ERROR ── */}
        {status === "error" && (
          <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-5">
            <div className="flex items-start gap-3 mb-4">
              <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-red-300 mb-0.5">Upload failed</p>
                <p className="text-xs text-red-400/60">{errorMessage}</p>
              </div>
            </div>
            <button onClick={handleReset} className="w-full py-2.5 rounded-xl border border-gray-800 hover:bg-gray-800/60 text-gray-400 text-sm transition-colors">
              Try again
            </button>
          </div>
        )}

        <p className="text-center text-xs text-gray-700 mt-8">
          Powered by Groq Llama 3.3 · fastembed · numpy
        </p>

      </div>
    </div>
  );
}
