"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  MessageSquare,
  Package,
  BarChart3,
  Settings,
  Bot,
  LogOut,
  Menu,
  Bell,
  DollarSign,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";

// ============================================================
// SOUND SYNTHESIS — Web Audio API (no audio files needed)
// ============================================================

/** Son "Ding" professionnel — nouvelle commande */
function playDing(ctx: AudioContext) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.type = "sine";
  osc.frequency.setValueAtTime(880, ctx.currentTime);
  osc.frequency.exponentialRampToValueAtTime(660, ctx.currentTime + 0.4);
  gain.gain.setValueAtTime(0.35, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.7);
  osc.start(ctx.currentTime);
  osc.stop(ctx.currentTime + 0.7);
}

/** Alarme répétitive — handoff urgent / cas sensible */
function playAlarm(ctx: AudioContext) {
  [0, 0.32, 0.64, 0.96].forEach((delay) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "sawtooth";
    osc.frequency.setValueAtTime(523, ctx.currentTime + delay);
    osc.frequency.setValueAtTime(659, ctx.currentTime + delay + 0.16);
    gain.gain.setValueAtTime(0.22, ctx.currentTime + delay);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + 0.3);
    osc.start(ctx.currentTime + delay);
    osc.stop(ctx.currentTime + delay + 0.32);
  });
}

// ============================================================
// TYPES
// ============================================================

type EventType = "new_order" | "handoff" | "sensitive";

interface AlertToast {
  id: number;
  message: string;
  type: EventType;
}

// ============================================================
// NAV
// ============================================================

const navItems = [
  { href: "/dashboard", label: "Vue d'ensemble", icon: BarChart3, exact: true },
  { href: "/dashboard/inbox", label: "Inbox", icon: MessageSquare, exact: false },
  { href: "/dashboard/orders", label: "Commandes", icon: Package, exact: false },
  { href: "/dashboard/pricing", label: "Grilles Tarifaires", icon: DollarSign, exact: false },
  { href: "/dashboard/supervision", label: "Supervision IA", icon: Bot, exact: false },
  { href: "/dashboard/settings", label: "Paramètres", icon: Settings, exact: false },
];

// ============================================================
// LAYOUT
// ============================================================

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  // UI state
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [ready, setReady] = useState(false);

  // Notification state
  const [badgeCount, setBadgeCount] = useState(0);
  const [soundEnabled, setSoundEnabled] = useState<boolean | null>(null);
  const [notifPermission, setNotifPermission] = useState<NotificationPermission | "unsupported">("default");
  const [toasts, setToasts] = useState<AlertToast[]>([]);

  // Refs
  const audioCtxRef = useRef<AudioContext | null>(null);
  const lastTimestampRef = useRef<string | null>(null);
  const isFirstPollRef = useRef(true);
  const toastIdRef = useRef(0);

  // ── Auth check ──────────────────────────────────────────
  useEffect(() => {
    const token = sessionStorage.getItem("token");
    if (!token) {
      router.replace("/login");
      return;
    }
    setReady(true);

    // Load sound preference
    const pref = sessionStorage.getItem("sound_enabled");
    if (pref === "true") {
      setSoundEnabled(true);
      // Lazy AudioContext creation on first click (browser autoplay policy)
      const initCtx = () => {
        if (!audioCtxRef.current) {
          try {
            audioCtxRef.current = new (
              window.AudioContext ||
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              (window as any).webkitAudioContext
            )();
          } catch {}
        }
        document.removeEventListener("click", initCtx, { capture: true });
      };
      document.addEventListener("click", initCtx, { capture: true });
    } else if (pref === "false") {
      setSoundEnabled(false);
    }
    // pref === null → show permission banner

    // Read current browser notification permission
    if (!("Notification" in window)) {
      setNotifPermission("unsupported");
    } else {
      setNotifPermission(Notification.permission);
    }
  }, [router]);

  // ── Sound controls ───────────────────────────────────────
  const enableSounds = useCallback(async () => {
    try {
      audioCtxRef.current = new (
        window.AudioContext ||
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (window as any).webkitAudioContext
      )();
      setSoundEnabled(true);
      sessionStorage.setItem("sound_enabled", "true");
    } catch {}

    // Request browser desktop notification permission at the same time
    if ("Notification" in window && Notification.permission === "default") {
      try {
        const result = await Notification.requestPermission();
        setNotifPermission(result);
      } catch {}
    } else if ("Notification" in window) {
      setNotifPermission(Notification.permission);
    }
  }, []);

  const disableSounds = useCallback(() => {
    setSoundEnabled(false);
    sessionStorage.setItem("sound_enabled", "false");
  }, []);

  const triggerSound = useCallback((type: EventType) => {
    if (!soundEnabled) return;
    const ctx = audioCtxRef.current;
    if (!ctx) return;
    try {
      if (ctx.state === "suspended") ctx.resume();
      if (type === "new_order") playDing(ctx);
      else playAlarm(ctx);
    } catch {}
  }, [soundEnabled]);

  // ── Browser desktop notifications ────────────────────────
  const sendBrowserNotif = useCallback((title: string, body: string, type: EventType) => {
    if (!("Notification" in window)) return;
    if (Notification.permission !== "granted") return;
    try {
      const isUrgent = type !== "new_order";
      const n = new Notification(title, {
        body,
        icon: "/favicon.ico",
        tag: type,                      // Replaces previous notif of same type (no spam)
        requireInteraction: isUrgent,   // Urgent alerts stay until dismissed
      });
      n.onclick = () => {
        window.focus();
        n.close();
      };
    } catch {}
  }, []);

  // ── Toast management ─────────────────────────────────────
  const addToast = useCallback((message: string, type: EventType) => {
    const id = ++toastIdRef.current;
    setToasts((prev) => [...prev.slice(-2), { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 6000);
  }, []);

  // ── Polling every 5 seconds ──────────────────────────────
  const poll = useCallback(async () => {
    const token = sessionStorage.getItem("token");
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    try {
      const [notifRes, badgeRes] = await Promise.all([
        fetch("/api/dashboard/notifications?unread_only=true", { headers }),
        fetch("/api/dashboard/orders/badges", { headers }),
      ]);

      // Notifications → sounds, toasts & browser push
      if (notifRes.ok) {
        const data = await notifRes.json();
        const notifs: Array<{ type: string; created_at: string }> = data.notifications || [];

        if (isFirstPollRef.current) {
          // Baseline: record current latest timestamp without triggering alerts
          if (notifs.length > 0) lastTimestampRef.current = notifs[0].created_at;
          isFirstPollRef.current = false;
        } else if (notifs.length > 0) {
          const latestTs = notifs[0].created_at;
          const prev = lastTimestampRef.current;

          if (prev === null || latestTs > prev) {
            const newOnes = notifs.filter((n) => prev === null || n.created_at > prev);

            const hasSensitive = newOnes.some((n) => n.type === "sensitive");
            const hasHandoff = newOnes.some((n) => n.type === "handoff");
            const hasNewOrder = newOnes.some((n) => n.type === "new_order");

            if (hasSensitive) {
              triggerSound("sensitive");
              addToast("Cas sensible détecté — action requise", "sensitive");
              sendBrowserNotif(
                "🚨 Cas Sensible — Action Requise",
                "Un cas sensible a été détecté. Connectez-vous au dashboard immédiatement.",
                "sensitive"
              );
            } else if (hasHandoff) {
              triggerSound("handoff");
              addToast("Handoff urgent — client en attente", "handoff");
              sendBrowserNotif(
                "⚡ Handoff Urgent",
                "Un client attend une prise en charge manuelle.",
                "handoff"
              );
            } else if (hasNewOrder) {
              triggerSound("new_order");
              addToast("Nouvelle commande reçue", "new_order");
              sendBrowserNotif(
                "📦 Nouvelle Commande",
                "Une nouvelle demande de fret vient d'être enregistrée.",
                "new_order"
              );
            }

            lastTimestampRef.current = latestTs;
          }
        }
      }

      // Badge count
      if (badgeRes.ok) {
        const data = await badgeRes.json();
        setBadgeCount(data.badges?.TOTAL ?? 0);
      }
    } catch {
      // Silent fail — keep polling
    }
  }, [triggerSound, addToast, sendBrowserNotif]);

  useEffect(() => {
    if (!ready) return;
    poll();
    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, [ready, poll]);

  // ── Handlers ─────────────────────────────────────────────
  const handleLogout = () => {
    sessionStorage.removeItem("token");
    sessionStorage.removeItem("agent");
    window.location.href = "/login";
  };

  // Banner visibility: show if sounds not yet chosen OR notifications not yet granted
  const showBanner = soundEnabled === null || (
    notifPermission !== "unsupported" &&
    notifPermission !== "granted" &&
    notifPermission !== "denied"
  );

  // ── Loading state ─────────────────────────────────────────
  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  // ============================================================
  // RENDER
  // ============================================================
  return (
    <div className="min-h-screen bg-gray-50 flex">

      {/* Mobile sidebar backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Sidebar ── */}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-64 bg-white border-r border-gray-200 transform transition-transform lg:transform-none ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        }`}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="p-4 border-b border-gray-100">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-sm">DA</span>
              </div>
              <div>
                <h2 className="font-semibold text-sm text-gray-900">Djama Air</h2>
                <p className="text-xs text-gray-500">Logistics Dashboard</p>
              </div>
            </div>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
            {navItems.map((item) => {
              const isActive = item.exact
                ? pathname === item.href
                : pathname.startsWith(item.href) && pathname !== "/dashboard";
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setSidebarOpen(false)}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition ${
                    isActive
                      ? "bg-blue-50 text-blue-700"
                      : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                  }`}
                >
                  <Icon className="w-5 h-5 flex-shrink-0" />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          {/* Logout */}
          <div className="p-3 border-t border-gray-100">
            <button
              onClick={handleLogout}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-gray-600 hover:bg-red-50 hover:text-red-600 w-full transition"
            >
              <LogOut className="w-5 h-5" />
              Déconnexion
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main content ── */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* Top bar */}
        <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between lg:justify-end sticky top-0 z-10">
          {/* Mobile hamburger */}
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden p-2 rounded-lg hover:bg-gray-100"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div className="flex items-center gap-2">
            {/* Sound toggle */}
            <button
              onClick={soundEnabled ? disableSounds : enableSounds}
              title={soundEnabled ? "Désactiver les sons" : "Activer les alertes sonores"}
              className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition"
            >
              {soundEnabled
                ? <Volume2 className="w-5 h-5 text-blue-600" />
                : <VolumeX className="w-5 h-5" />
              }
            </button>

            {/* Notification bell + badge */}
            <Link
              href="/dashboard"
              className="relative p-2 rounded-lg hover:bg-gray-100 text-gray-600 transition"
            >
              <Bell className="w-5 h-5" />
              {badgeCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] bg-red-500 rounded-full flex items-center justify-center text-white text-[10px] font-bold px-1 animate-pulse">
                  {badgeCount > 99 ? "99+" : badgeCount}
                </span>
              )}
            </Link>
          </div>
        </header>

        {/* ── Combined permission banner (sounds + desktop notifications) ── */}
        {showBanner && (
          <div className="bg-blue-50 border-b border-blue-100 px-4 lg:px-6 py-2.5 flex flex-wrap items-center gap-3">
            <Bell className="w-4 h-4 text-blue-500 flex-shrink-0" />
            <p className="text-sm text-blue-800 flex-1 min-w-0">
              Activer les alertes pour être notifié en temps réel — sons et notifications bureau, même onglet en arrière-plan.
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={enableSounds}
                className="px-3 py-1.5 bg-blue-600 text-white text-xs font-semibold rounded-lg hover:bg-blue-700 transition"
              >
                Activer
              </button>
              <button
                onClick={disableSounds}
                className="px-3 py-1.5 text-blue-700 text-xs font-medium rounded-lg hover:bg-blue-100 transition"
              >
                Non merci
              </button>
            </div>
          </div>
        )}

        {/* Page content */}
        <main className="flex-1 p-4 lg:p-6 overflow-auto">
          {children}
        </main>
      </div>

      {/* ── Toast notifications (bottom-right) ── */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 items-end pointer-events-none">
        {toasts.map((toast) => {
          const isUrgent = toast.type !== "new_order";
          return (
            <div
              key={toast.id}
              className={`pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-xl shadow-xl text-sm font-medium max-w-sm
                ${isUrgent ? "bg-red-600 text-white" : "bg-gray-900 text-white"}`}
            >
              <Bell className={`w-4 h-4 flex-shrink-0 ${isUrgent ? "text-red-200" : "text-yellow-400"}`} />
              <span className="flex-1">{toast.message}</span>
              <button
                onClick={() => setToasts((prev) => prev.filter((t) => t.id !== toast.id))}
                className="opacity-60 hover:opacity-100 transition-opacity flex-shrink-0 ml-1"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
      </div>

    </div>
  );
}
