"use client";

import { useState, useEffect, useCallback } from "react";
import { BookOpen, Clock, CheckCircle, Trash2, Send, RefreshCw, ChevronRight } from "lucide-react";

interface Gap {
  id: string;
  question: string;
  client_phone?: string;
  session_id?: string;
  created_at: string;
  answer?: string;
  answered_at?: string;
  answered_by?: string;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `il y a ${mins}min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `il y a ${hrs}h`;
  return `il y a ${Math.floor(hrs / 24)}j`;
}

export default function KnowledgePage() {
  const [tab, setTab] = useState<"pending" | "answered">("pending");
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [selected, setSelected] = useState<Gap | null>(null);
  const [answer, setAnswer] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "ok" | "err"; msg: string } | null>(null);

  const token = typeof window !== "undefined" ? sessionStorage.getItem("token") : null;

  const fetchGaps = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/dashboard/knowledge-gaps?status=${tab === "pending" ? "pending" : "answered"}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setGaps(data.gaps || []);
      setSelected(null);
      setAnswer("");
    } finally {
      setLoading(false);
    }
  }, [tab, token]);

  useEffect(() => {
    fetchGaps();
  }, [fetchGaps]);

  async function submitAnswer() {
    if (!selected || !answer.trim()) return;
    setSaving(true);
    setFeedback(null);
    try {
      const res = await fetch(`/api/dashboard/knowledge-gaps/${selected.id}/answer`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ answer: answer.trim() }),
      });
      if (!res.ok) throw new Error();
      setFeedback({ type: "ok", msg: "Réponse enregistrée — le bot l'utilisera dès maintenant." });
      setTimeout(() => { setFeedback(null); fetchGaps(); }, 2000);
    } catch {
      setFeedback({ type: "err", msg: "Erreur lors de l'enregistrement." });
    } finally {
      setSaving(false);
    }
  }

  async function dismiss(id: string) {
    await fetch(`/api/dashboard/knowledge-gaps/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    fetchGaps();
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-6 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BookOpen className="text-blue-600" size={22} />
          <div>
            <h1 className="text-lg font-semibold text-gray-900">Base de connaissances</h1>
            <p className="text-sm text-gray-500">Questions sans réponse détectées par le bot — répondez pour l'enrichir</p>
          </div>
        </div>
        <button type="button" onClick={fetchGaps} className="p-2 rounded-lg hover:bg-gray-100 text-gray-500" title="Actualiser">
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-100 px-6">
        {(["pending", "answered"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`py-3 px-4 text-sm font-medium border-b-2 transition-colors ${
              tab === t
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t === "pending" ? (
              <span className="flex items-center gap-2">
                <Clock size={14} />
                En attente{gaps.length > 0 && tab === "pending" ? ` (${gaps.length})` : ""}
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <CheckCircle size={14} />
                Répondues
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Body: two panels */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: list */}
        <div className="w-80 border-r border-gray-100 overflow-y-auto flex-shrink-0">
          {loading ? (
            <div className="flex items-center justify-center h-32 text-gray-400 text-sm">Chargement…</div>
          ) : gaps.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-gray-400 gap-2">
              <BookOpen size={28} className="opacity-30" />
              <p className="text-sm">
                {tab === "pending" ? "Aucune question en attente" : "Aucune réponse enregistrée"}
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-gray-50">
              {gaps.map((g) => (
                <li
                  key={g.id}
                  onClick={() => { setSelected(g); setAnswer(g.answer || ""); setFeedback(null); }}
                  className={`px-4 py-3 cursor-pointer hover:bg-blue-50 transition-colors ${
                    selected?.id === g.id ? "bg-blue-50 border-l-2 border-blue-500" : ""
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-800 line-clamp-2 font-medium">{g.question}</p>
                      <p className="text-xs text-gray-400 mt-1">
                        {g.client_phone && <span className="mr-2">📱 {g.client_phone}</span>}
                        {timeAgo(g.created_at)}
                      </p>
                    </div>
                    <ChevronRight size={14} className="text-gray-300 flex-shrink-0 mt-0.5" />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Right: detail + answer form */}
        <div className="flex-1 overflow-y-auto p-6">
          {!selected ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-300 gap-3">
              <BookOpen size={40} className="opacity-30" />
              <p className="text-sm">Sélectionnez une question à gauche</p>
            </div>
          ) : (
            <div className="max-w-2xl space-y-6">
              {/* Question card */}
              <div className="bg-gray-50 rounded-xl p-5 border border-gray-100">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Question du client</p>
                <p className="text-gray-800 text-base font-medium">{selected.question}</p>
                <div className="flex items-center gap-4 mt-3 text-xs text-gray-400">
                  {selected.client_phone && <span>Téléphone: {selected.client_phone}</span>}
                  <span>{timeAgo(selected.created_at)}</span>
                </div>
              </div>

              {/* Answer area */}
              {tab === "pending" ? (
                <div className="space-y-3">
                  <label className="block text-sm font-semibold text-gray-700">
                    Votre réponse (sera injectée dans la mémoire du bot)
                  </label>
                  <textarea
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    placeholder="Rédigez la réponse que le bot devra donner à cette question la prochaine fois…"
                    rows={6}
                    className="w-full border border-gray-200 rounded-lg p-3 text-sm text-gray-800 resize-y focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={submitAnswer}
                      disabled={saving || !answer.trim()}
                      className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      <Send size={14} />
                      {saving ? "Enregistrement…" : "Enregistrer et enseigner au bot"}
                    </button>
                    <button
                      type="button"
                      onClick={() => dismiss(selected.id)}
                      className="flex items-center gap-2 px-3 py-2 text-sm text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                    >
                      <Trash2 size={14} />
                      Ignorer
                    </button>
                  </div>
                  {feedback && (
                    <p className={`text-sm px-3 py-2 rounded-lg ${feedback.type === "ok" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"}`}>
                      {feedback.msg}
                    </p>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm font-semibold text-gray-700">Réponse enregistrée</p>
                  <div className="bg-green-50 border border-green-100 rounded-xl p-4 text-sm text-gray-800 whitespace-pre-wrap">
                    {selected.answer}
                  </div>
                  <p className="text-xs text-gray-400">
                    Répondu par {selected.answered_by} · {selected.answered_at ? timeAgo(selected.answered_at) : ""}
                  </p>
                  <button
                    type="button"
                    onClick={() => dismiss(selected.id)}
                    className="flex items-center gap-2 px-3 py-2 text-sm text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    <Trash2 size={14} />
                    Supprimer de la base
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
