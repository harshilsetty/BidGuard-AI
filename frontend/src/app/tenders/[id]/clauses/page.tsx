"use client";

import { useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import {
  fetchTenderDetail,
  updateClause,
  deleteClause,
  addManualClause,
  confirmTenderClauses,
} from "@/lib/api-client";
import { Tender, TenderClause, ClauseCreateInput } from "@/lib/types";
import { TenderDocumentsPanel } from "@/components/TenderDocumentsPanel";
import {
  CheckCircle2,
  AlertCircle,
  FileText,
  Plus,
  Trash2,
  Edit2,
  Lock,
  Search,
  BookOpen,
  ArrowLeft,
  ArrowRight,
  SlidersHorizontal,
  X,
} from "lucide-react";

export default function TenderClausesPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const resolvedParams = use(params);
  const tenderId = resolvedParams.id;
  const router = useRouter();

  const [tender, setTender] = useState<Tender | null>(null);
  const [clauses, setClauses] = useState<TenderClause[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Filters
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Modals & Panels
  const [evidenceModalClause, setEvidenceModalClause] = useState<TenderClause | null>(null);
  const [editModalClause, setEditModalClause] = useState<TenderClause | null>(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);

  // New Clause Form State
  const [newCategory, setNewCategory] = useState("TECHNICAL");
  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newMandatory, setNewMandatory] = useState(true);
  const [newSourceText, setNewSourceText] = useState("");
  const [newPageNum, setNewPageNum] = useState(1);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchTenderDetail(tenderId);
      setTender(data);
      setClauses(data.clauses || []);
    } catch (err: any) {
      setError(err.message || "Failed to load tender requirements");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [tenderId]);

  const handleToggleMandatory = async (clause: TenderClause) => {
    try {
      const updated = await updateClause(tenderId, clause.id, {
        is_mandatory: !clause.is_mandatory,
      });
      setClauses((prev) => prev.map((c) => (c.id === clause.id ? updated : c)));
    } catch (err: any) {
      setError(err.message || "Failed to update clause");
    }
  };

  const handleDeleteClause = async (clauseId: string) => {
    if (!confirm("Are you sure you want to remove this requirement?")) return;
    try {
      await deleteClause(tenderId, clauseId);
      setClauses((prev) => prev.filter((c) => c.id !== clauseId));
    } catch (err: any) {
      setError(err.message || "Failed to delete clause");
    }
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editModalClause) return;
    try {
      const updated = await updateClause(tenderId, editModalClause.id, {
        title: editModalClause.title,
        description: editModalClause.description,
        is_mandatory: editModalClause.is_mandatory,
        category: editModalClause.category,
        page_number: editModalClause.page_number,
        source_text: editModalClause.source_text,
      });
      setClauses((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
      setEditModalClause(null);
      setSuccessMsg("Clause updated successfully.");
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err: any) {
      setError(err.message || "Failed to save edit");
    }
  };

  const handleAddClause = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const input: ClauseCreateInput = {
        category: newCategory,
        title: newTitle.trim(),
        description: newDesc.trim(),
        is_mandatory: newMandatory,
        source_text: newSourceText.trim() || "Manually specified by procurement officer",
        page_number: newPageNum,
      };
      const created = await addManualClause(tenderId, input);
      setClauses((prev) => [...prev, created]);
      setIsAddModalOpen(false);
      // Reset form
      setNewTitle("");
      setNewDesc("");
      setNewSourceText("");
      setSuccessMsg("Custom requirement added.");
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err: any) {
      setError(err.message || "Failed to add requirement");
    }
  };

  const handleConfirmAll = async () => {
    if (
      !confirm(
        "Confirm and lock these requirements? Once confirmed, this tender will be marked READY for bidder compliance evaluations."
      )
    ) {
      return;
    }

    try {
      const updatedTender = await confirmTenderClauses(tenderId);
      setTender(updatedTender);
      setClauses(updatedTender.clauses || []);
      setSuccessMsg(
        "Tender requirements locked and confirmed! Status is now READY for Bidder Proposals."
      );
    } catch (err: any) {
      setError(err.message || "Failed to confirm requirements");
    }
  };

  // Categories count
  const categories = [
    { id: "ALL", label: "All Requirements", count: clauses.length },
    { id: "TECHNICAL", label: "Technical", count: clauses.filter((c) => c.category === "TECHNICAL").length },
    { id: "FINANCIAL", label: "Financial", count: clauses.filter((c) => c.category === "FINANCIAL").length },
    { id: "STATUTORY", label: "Statutory & GeM", count: clauses.filter((c) => c.category === "STATUTORY").length },
    { id: "EXPERIENCE", label: "Experience", count: clauses.filter((c) => c.category === "EXPERIENCE").length },
    { id: "DELIVERY_SLA", label: "Delivery & SLA", count: clauses.filter((c) => c.category === "DELIVERY_SLA").length },
  ];

  const filteredClauses = clauses.filter((c) => {
    const matchesCategory = selectedCategory === "ALL" || c.category === selectedCategory;
    const matchesQuery =
      searchQuery === "" ||
      c.clause_code.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.description.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesQuery;
  });

  if (loading) {
    return (
      <div className="py-20 text-center space-y-3">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-blue-500 border-t-transparent"></div>
        <p className="text-sm text-slate-400">Loading tender requirements and evidence provenance...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Info */}
      <div className="bg-white border border-[#E9EEF5] rounded-xl p-6 shadow-xs">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1">
            <button
              onClick={() => router.push("/")}
              className="inline-flex items-center text-xs text-[#6B7C93] hover:text-[#0F2D5B] transition mb-2"
            >
              <ArrowLeft className="w-3.5 h-3.5 mr-1" /> Back to Dashboard
            </button>
            <div className="flex items-center space-x-3">
              <h2 className="text-xl font-bold text-[#0F2D5B]">{tender?.title}</h2>
              {tender?.extraction_status === "READY" ? (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-[#28A745] border border-emerald-200">
                  <CheckCircle2 className="w-3 h-3 mr-1" /> READY
                </span>
              ) : (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-300">
                  <SlidersHorizontal className="w-3 h-3 mr-1" /> REVIEW MODE
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-4 text-xs text-[#6B7C93] pt-1">
              {tender?.gem_tender_id && (
                <span>
                  <strong className="text-[#2B3A55]">GeM Ref:</strong> {tender.gem_tender_id}
                </span>
              )}
              <span>
                <strong className="text-[#2B3A55]">Total Pages:</strong> {tender?.total_pages}
              </span>
              <span>
                <strong className="text-[#2B3A55]">Extracted Requirements:</strong> {clauses.length}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => setIsAddModalOpen(true)}
              className="inline-flex items-center space-x-1.5 px-3.5 py-2 bg-white hover:bg-[#F5F8FB] border border-[#E9EEF5] text-[#2B3A55] rounded-lg text-xs font-semibold transition shadow-2xs"
            >
              <Plus className="w-3.5 h-3.5 text-[#1F4E9E]" />
              <span>Add Custom Requirement</span>
            </button>
            <button
              onClick={handleConfirmAll}
              className="inline-flex items-center space-x-2 px-4 py-2 bg-[#28A745] hover:bg-emerald-600 text-white rounded-lg text-xs font-semibold transition shadow-xs"
            >
              <Lock className="w-3.5 h-3.5" />
              <span>Confirm & Lock Requirements</span>
            </button>
            <button
              onClick={() => router.push(`/tenders/${tenderId}/bidders`)}
              className="inline-flex items-center space-x-2 px-4 py-2 bg-[#1F4E9E] hover:bg-[#2E73D6] text-white rounded-lg text-xs font-semibold transition shadow-xs"
            >
              <span>Proceed to Bidders & Evaluation</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Phase 2.0A Multi-Document Attachments */}
      <TenderDocumentsPanel tenderId={tenderId} />

      {successMsg && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center space-x-3 text-[#28A745] text-sm">
          <CheckCircle2 className="w-5 h-5 text-[#28A745] flex-shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl flex items-center space-x-3 text-[#DC3545] text-sm">
          <AlertCircle className="w-5 h-5 text-[#DC3545] flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Category Tabs & Search Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Category Pills */}
        <div className="flex flex-wrap gap-2">
          {categories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center space-x-2 ${
                selectedCategory === cat.id
                  ? "bg-[#1F4E9E] text-white shadow-xs"
                  : "bg-white border border-[#E9EEF5] text-[#2B3A55] hover:bg-[#F5F8FB]"
              }`}
            >
              <span>{cat.label}</span>
              <span
                className={`px-1.5 py-0.2 rounded text-[10px] ${
                  selectedCategory === cat.id
                    ? "bg-[#0F2D5B] text-white"
                    : "bg-slate-100 text-[#6B7C93]"
                }`}
              >
                {cat.count}
              </span>
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative w-full md:w-64">
          <Search className="w-4 h-4 text-[#6B7C93] absolute left-3 top-2.5" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search requirements..."
            className="w-full bg-white border border-[#E9EEF5] rounded-lg pl-9 pr-3 py-1.5 text-xs text-[#2B3A55] placeholder-slate-400 focus:outline-none focus:border-[#1F4E9E]"
          />
        </div>
      </div>

      {/* Clauses Table */}
      <div className="bg-white border border-[#E9EEF5] rounded-xl overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-[#2B3A55]">
            <thead className="bg-[#F5F8FB] text-[#2B3A55] uppercase tracking-wider font-bold border-b border-[#E9EEF5]">
              <tr>
                <th className="px-4 py-3.5 w-28">Code</th>
                <th className="px-4 py-3.5 w-32">Category</th>
                <th className="px-4 py-3.5">Requirement & Specifications</th>
                <th className="px-4 py-3.5 w-28 text-center">Mandatory</th>
                <th className="px-4 py-3.5 w-32">Evidence</th>
                <th className="px-4 py-3.5 w-24 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E9EEF5]">
              {filteredClauses.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-[#6B7C93]">
                    No requirements found for the selected filter.
                  </td>
                </tr>
              ) : (
                filteredClauses.map((clause) => (
                  <tr key={clause.id} className="hover:bg-[#F5F8FB] transition">
                    <td className="px-4 py-3.5 font-mono font-bold text-[#1F4E9E]">
                      {clause.clause_code}
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-[#2B3A55] border border-[#E9EEF5]">
                        {clause.category}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 space-y-1">
                      <p className="font-bold text-[#0F2D5B]">{clause.title}</p>
                      <p className="text-[#6B7C93] line-clamp-2">{clause.description}</p>
                      {clause.rule_config && (
                        <div className="pt-1">
                          <span className="inline-block px-2 py-0.5 rounded text-[10px] font-mono bg-blue-50 text-[#1F4E9E] border border-blue-200">
                            Rule: {JSON.stringify(clause.rule_config)}
                          </span>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3.5 text-center">
                      <button
                        onClick={() => handleToggleMandatory(clause)}
                        className={`px-2.5 py-1 rounded-full text-[10px] font-bold transition ${
                          clause.is_mandatory
                            ? "bg-red-50 text-[#DC3545] border border-red-200 hover:bg-red-100"
                            : "bg-slate-100 text-[#6B7C93] border border-[#E9EEF5] hover:bg-slate-200"
                        }`}
                      >
                        {clause.is_mandatory ? "MANDATORY" : "OPTIONAL"}
                      </button>
                    </td>
                    <td className="px-4 py-3.5">
                      <button
                        onClick={() => setEvidenceModalClause(clause)}
                        className="inline-flex items-center space-x-1 px-2.5 py-1 rounded bg-white hover:bg-[#F5F8FB] text-[#1F4E9E] border border-[#E9EEF5] text-[11px] font-semibold transition shadow-2xs"
                      >
                        <BookOpen className="w-3 h-3 text-[#1F4E9E]" />
                        <span>Page {clause.page_number}</span>
                      </button>
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <div className="flex items-center justify-end space-x-2">
                        <button
                          onClick={() => setEditModalClause({ ...clause })}
                          className="p-1.5 rounded hover:bg-slate-100 text-[#6B7C93] hover:text-[#0F2D5B] transition"
                          title="Edit Requirement"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleDeleteClause(clause.id)}
                          className="p-1.5 rounded hover:bg-red-50 text-[#6B7C93] hover:text-[#DC3545] transition"
                          title="Delete Requirement"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Evidence Provenance Modal */}
      {evidenceModalClause && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4 backdrop-blur-xs">
          <div className="bg-white border border-[#E9EEF5] rounded-xl max-w-lg w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-[#E9EEF5] pb-3">
              <div className="flex items-center space-x-2">
                <FileText className="w-4 h-4 text-[#1F4E9E]" />
                <h3 className="font-bold text-sm text-[#0F2D5B]">
                  Verbatim Source Evidence Provenance
                </h3>
              </div>
              <button
                onClick={() => setEvidenceModalClause(null)}
                className="text-[#6B7C93] hover:text-[#2B3A55]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div className="flex justify-between text-[#6B7C93]">
                <span>Clause Code: <strong className="text-[#1F4E9E] font-mono">{evidenceModalClause.clause_code}</strong></span>
                <span>Page in Tender: <strong className="text-[#2B3A55]">Page {evidenceModalClause.page_number}</strong></span>
              </div>
              <div>
                <p className="text-[#6B7C93] font-medium mb-1">Requirement Title:</p>
                <p className="text-[#0F2D5B] font-bold">{evidenceModalClause.title}</p>
              </div>
              <div>
                <p className="text-[#6B7C93] font-medium mb-1">Ground Truth Snippet from Document:</p>
                <div className="p-3 bg-[#F5F8FB] border border-[#E9EEF5] rounded-lg text-[#2B3A55] font-serif leading-relaxed italic">
                  "{evidenceModalClause.source_text}"
                </div>
              </div>
            </div>
            <div className="flex justify-end pt-2">
              <button
                onClick={() => setEvidenceModalClause(null)}
                className="px-4 py-1.5 bg-white hover:bg-[#F5F8FB] text-[#2B3A55] border border-[#E9EEF5] rounded-lg text-xs font-semibold transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Clause Modal */}
      {editModalClause && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4 backdrop-blur-xs">
          <form
            onSubmit={handleSaveEdit}
            className="bg-white border border-[#E9EEF5] rounded-xl max-w-xl w-full p-6 space-y-4 shadow-xl"
          >
            <div className="flex items-center justify-between border-b border-[#E9EEF5] pb-3">
              <h3 className="font-bold text-sm text-[#0F2D5B]">
                Edit Requirement ({editModalClause.clause_code})
              </h3>
              <button
                type="button"
                onClick={() => setEditModalClause(null)}
                className="text-[#6B7C93] hover:text-[#2B3A55]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-[#2B3A55] font-semibold mb-1">Category</label>
                <select
                  value={editModalClause.category}
                  onChange={(e) =>
                    setEditModalClause({ ...editModalClause, category: e.target.value })
                  }
                  className="w-full bg-white border border-[#E9EEF5] rounded-lg px-3 py-2 text-[#2B3A55]"
                >
                  <option value="TECHNICAL">TECHNICAL</option>
                  <option value="FINANCIAL">FINANCIAL</option>
                  <option value="STATUTORY">STATUTORY</option>
                  <option value="EXPERIENCE">EXPERIENCE</option>
                  <option value="DELIVERY_SLA">DELIVERY_SLA</option>
                </select>
              </div>
              <div>
                <label className="block text-[#2B3A55] font-semibold mb-1">Title</label>
                <input
                  type="text"
                  required
                  value={editModalClause.title}
                  onChange={(e) =>
                    setEditModalClause({ ...editModalClause, title: e.target.value })
                  }
                  className="w-full bg-white border border-[#E9EEF5] rounded-lg px-3 py-2 text-[#2B3A55]"
                />
              </div>
              <div>
                <label className="block text-[#2B3A55] font-semibold mb-1">Description</label>
                <textarea
                  rows={3}
                  required
                  value={editModalClause.description}
                  onChange={(e) =>
                    setEditModalClause({ ...editModalClause, description: e.target.value })
                  }
                  className="w-full bg-white border border-[#E9EEF5] rounded-lg px-3 py-2 text-[#2B3A55]"
                />
              </div>
              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="editMandatory"
                  checked={editModalClause.is_mandatory}
                  onChange={(e) =>
                    setEditModalClause({
                      ...editModalClause,
                      is_mandatory: e.target.checked,
                    })
                  }
                  className="rounded border-[#E9EEF5] text-[#1F4E9E] focus:ring-0"
                />
                <label htmlFor="editMandatory" className="text-[#2B3A55] font-medium cursor-pointer">
                  Mandatory criteria (Non-compliance disqualifies bid)
                </label>
              </div>
            </div>
            <div className="flex justify-end space-x-2 pt-2">
              <button
                type="button"
                onClick={() => setEditModalClause(null)}
                className="px-4 py-1.5 bg-white border border-[#E9EEF5] text-[#6B7C93] hover:text-[#2B3A55] rounded-lg text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 bg-[#1F4E9E] hover:bg-[#2E73D6] text-white rounded-lg text-xs font-semibold"
              >
                Save Changes
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Add Custom Requirement Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4 backdrop-blur-xs">
          <form
            onSubmit={handleAddClause}
            className="bg-white border border-[#E9EEF5] rounded-xl max-w-xl w-full p-6 space-y-4 shadow-xl"
          >
            <div className="flex items-center justify-between border-b border-[#E9EEF5] pb-3">
              <h3 className="font-bold text-sm text-[#0F2D5B]">
                Add Custom Tender Requirement
              </h3>
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="text-[#6B7C93] hover:text-[#2B3A55]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[#2B3A55] font-semibold mb-1">Category</label>
                  <select
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value)}
                    className="w-full bg-white border border-[#E9EEF5] rounded-lg px-3 py-2 text-[#2B3A55]"
                  >
                    <option value="TECHNICAL">TECHNICAL</option>
                    <option value="FINANCIAL">FINANCIAL</option>
                    <option value="STATUTORY">STATUTORY</option>
                    <option value="EXPERIENCE">EXPERIENCE</option>
                    <option value="DELIVERY_SLA">DELIVERY_SLA</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[#2B3A55] font-semibold mb-1">Source Page</label>
                  <input
                    type="number"
                    min={1}
                    value={newPageNum}
                    onChange={(e) => setNewPageNum(parseInt(e.target.value) || 1)}
                    className="w-full bg-white border border-[#E9EEF5] rounded-lg px-3 py-2 text-[#2B3A55]"
                  />
                </div>
              </div>
              <div>
                <label className="block text-[#2B3A55] font-semibold mb-1">Requirement Title *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. OEM Authorized Partner Certification"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full bg-white border border-[#E9EEF5] rounded-lg px-3 py-2 text-[#2B3A55]"
                />
              </div>
              <div>
                <label className="block text-[#2B3A55] font-semibold mb-1">Description *</label>
                <textarea
                  rows={3}
                  required
                  placeholder="Detailed criteria for evaluation..."
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="w-full bg-white border border-[#E9EEF5] rounded-lg px-3 py-2 text-[#2B3A55]"
                />
              </div>
              <div>
                <label className="block text-[#2B3A55] font-semibold mb-1">Source Quote from PDF (Optional)</label>
                <textarea
                  rows={2}
                  placeholder="Verbatim text reference..."
                  value={newSourceText}
                  onChange={(e) => setNewSourceText(e.target.value)}
                  className="w-full bg-white border border-[#E9EEF5] rounded-lg px-3 py-2 text-[#2B3A55]"
                />
              </div>
              <div className="flex items-center space-x-2 pt-1">
                <input
                  type="checkbox"
                  id="newMandatory"
                  checked={newMandatory}
                  onChange={(e) => setNewMandatory(e.target.checked)}
                  className="rounded border-[#E9EEF5] text-[#1F4E9E] focus:ring-0"
                />
                <label htmlFor="newMandatory" className="text-[#2B3A55] font-medium cursor-pointer">
                  Mandatory criteria (Disqualifies bid if not satisfied)
                </label>
              </div>
            </div>
            <div className="flex justify-end space-x-2 pt-2">
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="px-4 py-1.5 bg-white border border-[#E9EEF5] text-[#6B7C93] hover:text-[#2B3A55] rounded-lg text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 bg-[#1F4E9E] hover:bg-[#2E73D6] text-white rounded-lg text-xs font-semibold"
              >
                Add Requirement
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
