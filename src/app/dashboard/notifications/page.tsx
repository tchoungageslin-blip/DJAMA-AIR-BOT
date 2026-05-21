"use client";

import { useEffect, useState } from "react";
import { Bell, AlertTriangle, Package, MessageSquare, Check } from "lucide-react";

interface Notification {
  id: string;
  session_id: string | null;
  channel: string;
  type: string;
  content: string;
  sent: boolean;
  created_at: string;
}

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    fetchNotifications();
  }, [showAll]);

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const url = showAll
        ? "/api/dashboard/notifications?unread_only=false"
        : "/api/dashboard/notifications";
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setNotifications(data.notifications || []);
      }
    } catch {
      // Silent fail
    } finally {
      setLoading(false);
    }
  };

  const getIcon = (type: string) => {
    if (type === "handoff" || type === "urgent") return <AlertTriangle className="w-4 h-4 text-orange-500" />;
    if (type === "order") return <Package className="w-4 h-4 text-green-500" />;
    return <MessageSquare className="w-4 h-4 text-blue-500" />;
  };

  const getTimeSince = (dateStr: string) => {
    const diff = Date.now() - new Date(dateStr).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return "A l'instant";
    if (minutes < 60) return `Il y a ${minutes}min`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `Il y a ${hours}h`;
    const days = Math.floor(hours / 24);
    return `Il y a ${days}j`;
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Notifications</h1>
          <p className="text-sm text-gray-500 mt-1">Alertes et mises a jour</p>
        </div>
        <button
          onClick={() => setShowAll(!showAll)}
          className={`px-3 py-1.5 text-xs font-medium rounded-lg transition ${
            showAll
              ? "bg-blue-100 text-blue-700"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
        >
          {showAll ? "Recentes uniquement" : "Voir tout"}
        </button>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-sm text-gray-500">Chargement...</div>
        ) : notifications.length === 0 ? (
          <div className="p-8 text-center">
            <Bell className="w-10 h-10 text-gray-300 mx-auto mb-2" />
            <p className="text-sm text-gray-500">Aucune notification</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-50">
            {notifications.map((notif) => (
              <div
                key={notif.id}
                className="p-4 flex items-start gap-3 hover:bg-gray-50 transition"
              >
                <div className="flex-shrink-0 mt-0.5">{getIcon(notif.type)}</div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-900">{notif.content}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[10px] text-gray-400">
                      {getTimeSince(notif.created_at)}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded">
                      {notif.channel}
                    </span>
                    {notif.sent && (
                      <span className="flex items-center gap-0.5 text-[10px] text-green-600">
                        <Check className="w-3 h-3" /> Envoyee
                      </span>
                    )}
                  </div>
                </div>
                {notif.session_id && (
                  <a
                    href={`/dashboard/inbox?session=${notif.session_id}`}
                    className="flex-shrink-0 text-xs text-blue-600 hover:underline"
                  >
                    Voir
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
