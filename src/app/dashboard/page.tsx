"use client";

import { useEffect, useState } from "react";
import { MessageSquare, Package, AlertTriangle, TrendingUp } from "lucide-react";

interface Stats {
  sessions_today: number;
  pending_handoffs: number;
  resolved_today: number;
  orders_today: number;
  estimated_revenue_today: number;
}

export default function DashboardOverview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const fetchStats = async () => {
    try {
      const res = await fetch("/api/dashboard/stats");
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch {
      // Silent fail
    } finally {
      setLoading(false);
    }
  };

  const formatFCFA = (amount: number) => {
    return new Intl.NumberFormat("fr-FR").format(amount) + " FCFA";
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Vue d&apos;ensemble</h1>
        <p className="text-sm text-gray-500 mt-1">Performance du jour</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Sessions aujourd'hui"
          value={stats?.sessions_today || 0}
          icon={<MessageSquare className="w-5 h-5 text-blue-600" />}
          bgColor="bg-blue-50"
        />
        <StatCard
          title="Handoffs en attente"
          value={stats?.pending_handoffs || 0}
          icon={<AlertTriangle className="w-5 h-5 text-orange-600" />}
          bgColor="bg-orange-50"
          highlight={true}
        />
        <StatCard
          title="Commandes du jour"
          value={stats?.orders_today || 0}
          icon={<Package className="w-5 h-5 text-green-600" />}
          bgColor="bg-green-50"
        />
        <StatCard
          title="CA estimé (IA)"
          value={formatFCFA(stats?.estimated_revenue_today || 0)}
          icon={<TrendingUp className="w-5 h-5 text-purple-600" />}
          bgColor="bg-purple-50"
          isText={true}
        />
      </div>

      {/* Quick Actions */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="font-semibold text-gray-900 mb-4">Actions rapides</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <a
            href="/dashboard/inbox?status=HUMAN_HANDOFF"
            className="flex items-center gap-3 p-4 rounded-lg border border-gray-200 hover:border-blue-300 hover:bg-blue-50 transition"
          >
            <AlertTriangle className="w-5 h-5 text-orange-500" />
            <div>
              <p className="font-medium text-sm">Traiter les handoffs</p>
              <p className="text-xs text-gray-500">{stats?.pending_handoffs || 0} en attente</p>
            </div>
          </a>
          <a
            href="/dashboard/orders"
            className="flex items-center gap-3 p-4 rounded-lg border border-gray-200 hover:border-blue-300 hover:bg-blue-50 transition"
          >
            <Package className="w-5 h-5 text-green-500" />
            <div>
              <p className="font-medium text-sm">Nouvelles commandes</p>
              <p className="text-xs text-gray-500">Voir le tableau</p>
            </div>
          </a>
          <a
            href="/dashboard/supervision"
            className="flex items-center gap-3 p-4 rounded-lg border border-gray-200 hover:border-blue-300 hover:bg-blue-50 transition"
          >
            <MessageSquare className="w-5 h-5 text-blue-500" />
            <div>
              <p className="font-medium text-sm">Supervision Bot</p>
              <p className="text-xs text-gray-500">Contrôle en temps réel</p>
            </div>
          </a>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  icon,
  bgColor,
  highlight = false,
  isText = false,
}: {
  title: string;
  value: number | string;
  icon: React.ReactNode;
  bgColor: string;
  highlight?: boolean;
  isText?: boolean;
}) {
  return (
    <div
      className={`bg-white rounded-xl border p-4 ${
        highlight ? "border-orange-200 ring-1 ring-orange-100" : "border-gray-200"
      }`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className={`p-2 rounded-lg ${bgColor}`}>{icon}</div>
      </div>
      <p className={`font-bold ${isText ? "text-lg" : "text-2xl"} text-gray-900`}>
        {value}
      </p>
      <p className="text-xs text-gray-500 mt-1">{title}</p>
    </div>
  );
}
