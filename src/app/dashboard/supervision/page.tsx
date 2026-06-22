"use client";

import { useEffect, useState } from "react";
import { Power, PowerOff, AlertCircle, Activity, Bot, RotateCcw, Save, CheckCircle, AlertTriangle } from "lucide-react";

export default function SupervisionPage() {
  const [botEnabled, setBotEnabled] = useState(true);
  const [toggleLoading, setToggleLoading] = useState(false);

  // Prompt editor state
  const [prompt, setPrompt] = useState("");
  const [originalPrompt, setOriginalPrompt] = useState("");
  const [isCustom, setIsCustom] = useState(false);
  const [promptLoading, setPromptLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "success" | "error">("idle");

  useEffect(() => {
    fetchBotStatus();
    fetchPrompt();
  }, []);

  const fetchBotStatus = async () => {
    try {
      const res = await fetch("/api/dashboard/health");
      if (res.ok) {
        const data = await res.json();
        setBotEnabled(data.bot_enabled);
      }
    } catch {}
  };

  const fetchPrompt = async () => {
    setPromptLoading(true);
    try {
      const res = await fetch("/api/dashboard/ai/prompt");
      if (res.ok) {
        const data = await res.json();
        setPrompt(data.prompt);
        setOriginalPrompt(data.prompt);
        setIsCustom(data.is_custom);
      }
    } catch {}
    finally { setPromptLoading(false); }
  };

  const toggleBot = async () => {
    setToggleLoading(true);
    try {
      const token = sessionStorage.getItem("token");
      const res = await fetch("/api/dashboard/bot/toggle", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ enabled: !botEnabled }),
      });
      if (res.ok) setBotEnabled(!botEnabled);
    } catch {}
    finally { setToggleLoading(false); }
  };

  const savePrompt = async () => {
    setSaving(true);
    setSaveStatus("idle");
    try {
      const token = sessionStorage.getItem("token");
      const res = await fetch("/api/dashboard/ai/prompt", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ prompt }),
      });
      if (res.ok) {
        setOriginalPrompt(prompt);
        setIsCustom(true);
        setSaveStatus("success");
        setTimeout(() => setSaveStatus("idle"), 3000);
      } else {
        setSaveStatus("error");
      }
    } catch {
      setSaveStatus("error");
    }
    finally { setSaving(false); }
  };

  const resetPrompt = async () => {
    if (!confirm("Réinitialiser le prompt au texte par défaut ? Cette action est irréversible.")) return;
    setSaving(true);
    try {
      const token = sessionStorage.getItem("token");
      await fetch("/api/dashboard/ai/prompt", {
        method: "DELETE",
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      });
      await fetchPrompt();
      setSaveStatus("success");
      setTimeout(() => setSaveStatus("idle"), 3000);
    } catch {
      setSaveStatus("error");
    }
    finally { setSaving(false); }
  };

  const isDirty = prompt !== originalPrompt;
  const charCount = prompt.length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Supervision IA</h1>
        <p className="text-sm text-gray-500 mt-1">Contrôle, monitoring et configuration du bot</p>
      </div>

      {/* Bot Status Card */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${botEnabled ? "bg-green-100" : "bg-red-100"}`}>
              {botEnabled
                ? <Activity className="w-6 h-6 text-green-600" />
                : <PowerOff className="w-6 h-6 text-red-600" />}
            </div>
            <div>
              <h3 className="font-semibold text-gray-900">
                Bot WhatsApp {botEnabled ? "Actif" : "Désactivé"}
              </h3>
              <p className="text-sm text-gray-500">
                {botEnabled
                  ? "Le bot répond automatiquement aux messages"
                  : "Tous les messages sont routés vers la file d'attente humaine"}
              </p>
            </div>
          </div>
          <button
            onClick={toggleBot}
            disabled={toggleLoading}
            className={`px-6 py-3 rounded-lg font-medium text-sm transition flex items-center gap-2 ${
              botEnabled
                ? "bg-red-50 text-red-700 hover:bg-red-100 border border-red-200"
                : "bg-green-50 text-green-700 hover:bg-green-100 border border-green-200"
            }`}
          >
            {botEnabled
              ? <><PowerOff className="w-4 h-4" /> Désactiver (Kill-Switch)</>
              : <><Power className="w-4 h-4" /> Réactiver le Bot</>}
          </button>
        </div>
      </div>

      {!botEnabled && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 mt-0.5" />
          <div>
            <h4 className="font-medium text-red-800">Mode urgence activé</h4>
            <p className="text-sm text-red-600 mt-1">
              Le bot est entièrement désactivé. Tous les messages entrants nécessitent une réponse manuelle.
            </p>
          </div>
        </div>
      )}

      {/* System Prompt Editor */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="p-5 border-b border-gray-100 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-indigo-50 rounded-lg flex items-center justify-center">
              <Bot className="w-5 h-5 text-indigo-600" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900">System Prompt</h3>
              <p className="text-xs text-gray-500 mt-0.5">
                Instructions envoyées à l&apos;IA à chaque message — définit son comportement et ses règles
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isCustom && (
              <span className="text-xs px-2.5 py-1 bg-indigo-50 text-indigo-700 rounded-full font-medium border border-indigo-100">
                Personnalisé
              </span>
            )}
            {!isCustom && (
              <span className="text-xs px-2.5 py-1 bg-gray-100 text-gray-500 rounded-full font-medium">
                Par défaut
              </span>
            )}
          </div>
        </div>

        <div className="p-5 space-y-3">
          {promptLoading ? (
            <div className="h-96 flex items-center justify-center">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-600" />
            </div>
          ) : (
            <>
              {saveStatus === "success" && (
                <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-2.5">
                  <CheckCircle className="w-4 h-4 flex-shrink-0" />
                  Prompt sauvegardé — le bot utilisera cette version dès le prochain message.
                </div>
              )}
              {saveStatus === "error" && (
                <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  Erreur lors de la sauvegarde. Réessayez.
                </div>
              )}

              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={24}
                className="w-full font-mono text-xs text-gray-800 border border-gray-200 rounded-lg p-4 focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none resize-y leading-relaxed bg-gray-50"
                placeholder="Entrez le system prompt ici..."
                spellCheck={false}
              />

              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">{charCount.toLocaleString()} caractères</span>
                <div className="flex items-center gap-2">
                  {isCustom && (
                    <button
                      onClick={resetPrompt}
                      disabled={saving}
                      className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-600 hover:text-gray-900 border border-gray-200 rounded-lg hover:bg-gray-50 transition"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      Réinitialiser
                    </button>
                  )}
                  <button
                    onClick={savePrompt}
                    disabled={saving || !isDirty || !prompt.trim()}
                    className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
                  >
                    <Save className="w-3.5 h-3.5" />
                    {saving ? "Sauvegarde..." : "Sauvegarder"}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Info */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4">Fonctionnalités de contrôle</h3>
        <div className="space-y-3">
          {[
            { n: "1", title: "Kill-Switch Global", desc: "Désactive le bot sur l'ensemble du canal WhatsApp immédiatement." },
            { n: "2", title: "System Prompt Dynamique", desc: "Modifiez le comportement du bot en temps réel sans redéploiement. Le changement est effectif dès le prochain message." },
            { n: "3", title: "Silent Takeover", desc: "Depuis l'Inbox, prenez le contrôle d'une conversation spécifique sans que le client ne le sache." },
          ].map((item) => (
            <div key={item.n} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
              <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                <span className="text-sm font-bold text-blue-600">{item.n}</span>
              </div>
              <div>
                <p className="font-medium text-sm text-gray-900">{item.title}</p>
                <p className="text-xs text-gray-500 mt-0.5">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
