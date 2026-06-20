"use client";

import { useEffect, useState } from "react";
import { Power, PowerOff, AlertCircle, Activity } from "lucide-react";

export default function SupervisionPage() {
  const [botEnabled, setBotEnabled] = useState(true);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchBotStatus();
  }, []);

  const fetchBotStatus = async () => {
    try {
      const res = await fetch("/api/dashboard/health");
      if (res.ok) {
        const data = await res.json();
        setBotEnabled(data.bot_enabled);
      }
    } catch {
      // Silent fail
    }
  };

  const toggleBot = async () => {
    setLoading(true);
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
      if (res.ok) {
        setBotEnabled(!botEnabled);
      }
    } catch {
      // Silent fail
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Supervision IA</h1>
        <p className="text-sm text-gray-500 mt-1">Contrôle et monitoring du bot</p>
      </div>

      {/* Bot Status Card */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
              botEnabled ? "bg-green-100" : "bg-red-100"
            }`}>
              {botEnabled ? (
                <Activity className="w-6 h-6 text-green-600" />
              ) : (
                <PowerOff className="w-6 h-6 text-red-600" />
              )}
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
            disabled={loading}
            className={`px-6 py-3 rounded-lg font-medium text-sm transition flex items-center gap-2 ${
              botEnabled
                ? "bg-red-50 text-red-700 hover:bg-red-100 border border-red-200"
                : "bg-green-50 text-green-700 hover:bg-green-100 border border-green-200"
            }`}
          >
            {botEnabled ? (
              <>
                <PowerOff className="w-4 h-4" />
                Désactiver (Kill-Switch)
              </>
            ) : (
              <>
                <Power className="w-4 h-4" />
                Réactiver le Bot
              </>
            )}
          </button>
        </div>
      </div>

      {/* Warning */}
      {!botEnabled && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 mt-0.5" />
          <div>
            <h4 className="font-medium text-red-800">Mode urgence activé</h4>
            <p className="text-sm text-red-600 mt-1">
              Le bot est entièrement désactivé. Tous les messages entrants nécessitent une réponse manuelle.
              Pensez à le réactiver une fois le problème résolu.
            </p>
          </div>
        </div>
      )}

      {/* Info */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4">Fonctionnalités de contrôle</h3>
        <div className="space-y-4">
          <div className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
            <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
              <span className="text-sm font-bold text-blue-600">1</span>
            </div>
            <div>
              <p className="font-medium text-sm text-gray-900">Kill-Switch Global</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Désactive le bot sur l&apos;ensemble du canal WhatsApp immédiatement.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
            <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
              <span className="text-sm font-bold text-blue-600">2</span>
            </div>
            <div>
              <p className="font-medium text-sm text-gray-900">Silent Takeover</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Depuis l&apos;Inbox, prenez le contrôle d&apos;une conversation spécifique sans que le client ne le sache.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
            <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
              <span className="text-sm font-bold text-blue-600">3</span>
            </div>
            <div>
              <p className="font-medium text-sm text-gray-900">Audit des erreurs</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Consultez les sessions où l&apos;IA a échoué, tourné en boucle, ou rencontré un timeout.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
