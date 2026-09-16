"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { uploadTenderPdf, triggerClauseExtraction } from "@/lib/api-client";
import { UploadCloud, FileText, CheckCircle2, AlertCircle, ArrowRight, Loader2 } from "lucide-react";

export default function NewTenderPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [gemTenderId, setGemTenderId] = useState("");
  const [step, setStep] = useState<"IDLE" | "UPLOADING" | "EXTRACTING" | "DONE">("IDLE");
  const [progressMsg, setProgressMsg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      if (!selected.name.toLowerCase().endsWith(".pdf")) {
        setError("Please select a valid PDF file.");
        return;
      }
      setFile(selected);
      setError(null);
      if (!title) {
        setTitle(selected.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " "));
      }
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const dropped = e.dataTransfer.files[0];
      if (!dropped.name.toLowerCase().endsWith(".pdf")) {
        setError("Please drop a valid PDF file.");
        return;
      }
      setFile(dropped);
      setError(null);
      if (!title) {
        setTitle(dropped.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " "));
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("Please select a Tender PDF file.");
      return;
    }
    if (!title.trim()) {
      setError("Please enter a Tender title.");
      return;
    }

    setError(null);
    try {
      // Step 1: Upload and parse pages with PyMuPDF
      setStep("UPLOADING");
      setProgressMsg("Uploading tender PDF and parsing page text with PyMuPDF...");
      const uploadedTender = await uploadTenderPdf(file, title.trim(), gemTenderId.trim() || undefined);

      // Step 2: Trigger AI clause extraction with NVIDIA NIM
      setStep("EXTRACTING");
      setProgressMsg(
        `Analyzing ${uploadedTender.total_pages} pages using NVIDIA NIM GPT-OSS 20B (3-page sliding windows with 1-page overlap)...`
      );
      await triggerClauseExtraction(uploadedTender.id);

      setStep("DONE");
      setProgressMsg("Clauses extracted successfully! Redirecting to Human Review...");
      setTimeout(() => {
        router.push(`/tenders/${uploadedTender.id}/clauses`);
      }, 1000);
    } catch (err: any) {
      setError(err.message || "Failed to process tender PDF.");
      setStep("IDLE");
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-[#0F2D5B]">Upload GeM Tender Document</h2>
        <p className="text-sm text-[#6B7C93] mt-1">
          Upload an official GeM Notice Inviting Tender (NIT) or RFP PDF. The platform will extract text using PyMuPDF and analyze compliance clauses using NVIDIA NIM GPT-OSS 20B.
        </p>
      </div>

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl flex items-start space-x-3 text-[#DC3545] text-sm">
          <AlertCircle className="w-5 h-5 mt-0.5 text-[#DC3545] flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {step !== "IDLE" ? (
        <div className="bg-white border border-[#E9EEF5] rounded-xl p-8 text-center space-y-4 shadow-xs">
          <div className="flex justify-center">
            {step === "DONE" ? (
              <CheckCircle2 className="w-12 h-12 text-[#28A745] animate-bounce" />
            ) : (
              <Loader2 className="w-12 h-12 text-[#1F4E9E] animate-spin" />
            )}
          </div>
          <h3 className="text-lg font-bold text-[#0F2D5B]">
            {step === "UPLOADING" && "Ingesting Tender Document"}
            {step === "EXTRACTING" && "AI Clause Extraction in Progress"}
            {step === "DONE" && "Extraction Complete!"}
          </h3>
          <p className="text-sm text-[#6B7C93] max-w-md mx-auto">{progressMsg}</p>
          <div className="w-full bg-[#E9EEF5] rounded-full h-2 max-w-md mx-auto overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${
                step === "UPLOADING"
                  ? "w-1/3 bg-[#1F4E9E]"
                  : step === "EXTRACTING"
                  ? "w-4/5 bg-[#2E73D6]"
                  : "w-full bg-[#28A745]"
              }`}
            />
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="bg-white border border-[#E9EEF5] rounded-xl p-6 sm:p-8 space-y-5 shadow-xs">
            {/* Title Input */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-[#2B3A55] mb-1.5">
                Tender Title *
              </label>
              <input
                type="text"
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Procurement of Server Infrastructure and High-Performance Storage"
                className="w-full bg-white border border-[#E9EEF5] focus:border-[#1F4E9E] rounded-lg px-3.5 py-2.5 text-sm text-[#2B3A55] placeholder-slate-400 focus:outline-none transition shadow-2xs"
              />
            </div>

            {/* GeM Tender ID Input */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-[#2B3A55] mb-1.5">
                GeM Bid / NIT Reference Number (Optional)
              </label>
              <input
                type="text"
                value={gemTenderId}
                onChange={(e) => setGemTenderId(e.target.value)}
                placeholder="e.g. GEM/2026/B/492104"
                className="w-full bg-white border border-[#E9EEF5] focus:border-[#1F4E9E] rounded-lg px-3.5 py-2.5 text-sm text-[#2B3A55] placeholder-slate-400 focus:outline-none transition shadow-2xs"
              />
            </div>

            {/* Drag and Drop Zone */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-[#2B3A55] mb-2">
                Tender PDF File *
              </label>
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-[#2E73D6]/40 hover:border-[#1F4E9E] bg-[#F5F8FB] rounded-xl p-8 text-center cursor-pointer transition flex flex-col items-center justify-center space-y-3"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf"
                  onChange={handleFileChange}
                  className="hidden"
                />
                <div className="h-12 w-12 rounded-full bg-blue-50 border border-blue-200 flex items-center justify-center text-[#1F4E9E]">
                  <UploadCloud className="w-6 h-6" />
                </div>
                {file ? (
                  <div className="flex items-center space-x-2 text-sm text-[#28A745] font-semibold">
                    <FileText className="w-4 h-4" />
                    <span>{file.name}</span>
                    <span className="text-[#6B7C93] text-xs">
                      ({(file.size / (1024 * 1024)).toFixed(2)} MB)
                    </span>
                  </div>
                ) : (
                  <>
                    <p className="text-sm text-[#2B3A55] font-medium">
                      Click to upload or drag & drop Tender PDF
                    </p>
                    <p className="text-xs text-[#6B7C93]">
                      Standard GeM NIT / Technical Specification document (PDF up to 50MB)
                    </p>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex justify-end space-x-3">
            <button
              type="button"
              onClick={() => router.push("/")}
              className="px-4 py-2 rounded-lg text-sm text-[#6B7C93] hover:text-[#2B3A55] transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!file || !title.trim()}
              className="inline-flex items-center space-x-2 px-6 py-2.5 bg-[#1F4E9E] hover:bg-[#2E73D6] text-white rounded-lg text-sm font-semibold transition shadow-xs disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span>Ingest & Extract Clauses</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
