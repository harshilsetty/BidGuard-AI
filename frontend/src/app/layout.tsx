import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "GeM Bid Compliance Verification Platform • SIH26100",
  description: "AI-Powered Integrated Bid Compliance Verification Platform for GeM Procurement",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-[#F5F8FB] text-[#2B3A55] antialiased min-h-screen flex flex-col font-sans">
        {/* Government Top Bar */}
        <div className="bg-[#0F2D5B] text-slate-200 text-[11px] px-4 py-1.5 border-b border-[#0a2042]">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <span className="font-semibold tracking-wide text-slate-100">
                GOVERNMENT OF INDIA • GeM PROCUREMENT VERIFICATION
              </span>
            </div>
            <div className="flex items-center space-x-4 text-slate-300">
              <span>SIH 2026 Problem ID: SIH26100</span>
              <span>•</span>
              <span className="text-emerald-400 font-medium flex items-center">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 inline-block" />
                Platform: Online
              </span>
            </div>
          </div>
        </div>

        {/* Main Navigation Header */}
        <header className="border-b border-[#E9EEF5] bg-white shadow-xs sticky top-0 z-40">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div className="flex items-center space-x-6">
              <Link href="/" className="flex items-center space-x-3 group">
                <div className="h-9 w-9 rounded bg-[#0F2D5B] flex items-center justify-center font-bold text-white text-sm shadow-xs tracking-wider">
                  GeM
                </div>
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="font-bold text-sm sm:text-base text-[#0F2D5B] tracking-tight">
                      BidGuard AI
                    </span>
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-blue-50 text-[#1F4E9E] border border-blue-200">
                      v1.0-RC
                    </span>
                  </div>
                  <p className="text-[11px] text-[#6B7C93] font-medium">
                    Integrated Bid Compliance Verification Platform
                  </p>
                </div>
              </Link>

              <nav className="hidden md:flex items-center space-x-1 pl-4 border-l border-[#E9EEF5]">
                <Link
                  href="/"
                  className="px-3 py-1.5 rounded text-xs font-semibold text-[#0F2D5B] hover:bg-[#F5F8FB] transition"
                >
                  Tenders
                </Link>
                <Link
                  href="/tenders/new"
                  className="px-3 py-1.5 rounded text-xs font-medium text-[#6B7C93] hover:text-[#0F2D5B] hover:bg-[#F5F8FB] transition"
                >
                  Upload Tender PDF
                </Link>
                <Link
                  href="/mock-data"
                  className="px-3 py-1.5 rounded text-xs font-medium text-[#6B7C93] hover:text-[#0F2D5B] hover:bg-[#F5F8FB] transition flex items-center space-x-1"
                >
                  <span>Mock Explorer</span>
                  <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-amber-50 text-amber-900 border border-amber-200">
                    5K
                  </span>
                </Link>
              </nav>
            </div>

            <div className="flex items-center space-x-3">
              <span className="hidden lg:inline-flex items-center px-2.5 py-1 rounded text-xs font-medium bg-[#F5F8FB] text-[#2B3A55] border border-[#E9EEF5]">
                <span className="w-2 h-2 rounded-full bg-[#28A745] mr-1.5 inline-block" />
                Hybrid Verification Active
              </span>

              <Link
                href="/tenders/new"
                className="inline-flex items-center px-3.5 py-1.5 rounded text-xs font-semibold bg-[#1F4E9E] hover:bg-[#183e80] text-white transition shadow-xs"
              >
                + Create Tender
              </Link>
            </div>
          </div>
        </header>

        {/* Main Application Area */}
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1 w-full">
          {children}
        </main>

        {/* Official Footer */}
        <footer className="border-t border-[#E9EEF5] bg-white text-[#6B7C93] text-xs py-5 mt-auto">
          <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2 text-center sm:text-left">
            <div>
              <strong className="text-[#0F2D5B] font-semibold">SIH26100: Bid Compliance Verification Platform</strong> — Designed for GeM Public Procurement
            </div>
            <div className="text-[#6B7C93] text-[11px]">
              Strictly Source-Grounded Evidence • Clause-Scoped Contradiction Detection • Deterministic Verification
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
