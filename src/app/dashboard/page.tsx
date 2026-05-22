"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  MessageSquare,
  Package,
  TrendingUp,
  Users,
  Zap,
} from "lucide-react";

type MetricKey = "sessions" | "handoffs" | "messages" | "orders" | "revenue";

interface DailyMetric {
  day: string;
  label: string;
  sessions: number;
  handoffs: number;
  messages: number;
  orders: number;
  revenue: number;
}

interface DistributionItem {
  [key: string]: string | number;
}

interface Stats {
  sessions_today: number;
  pending_handoffs: number;
  resolved_today: number;
  active_sessions: number;
  orders_today: number;
  estimated_revenue_today: number;
  messages_today: number;
  client_messages_today: number;
  bot_messages_today: number;
  agent_messages_today: number;
  total_clients: number;
  handoff_rate: number;
  resolution_rate: number;
  automation_rate: number;
  daily_metrics: DailyMetric[];
  session_status: DistributionItem[];
  message_sources: DistributionItem[];
  order_types: DistributionItem[];
}

const statusLabels: Record<string, string> = {
  BOT_ACTIVE: "Bot actif",
  HUMAN_HANDOFF: "Transfert humain",
  HUMAN_ACTIVE: "Agent actif",
  RESOLVED: "Résolu",
  CLOSED: "Fermé",
};

const sourceLabels: Record<string, string> = {
  client: "Clients",
  bot: "Bot IA",
  agent: "Agents",
};

const orderTypeLabels: Record<string, string> = {
  FRET: "Fret",
  BILLETTERIE: "Billetterie",
  PACK: "Pack",
};

export default function DashboardOverview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 30000);
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
    } finally {
      setLoading(false);
    }
  };

  const dailyMetrics = stats?.daily_metrics || [];
  const peakActivity = useMemo(() => {
    return dailyMetrics.reduce((max, item) => Math.max(max, Number(item.messages || 0)), 0);
  }, [dailyMetrics]);

  const formatFCFA = (amount: number) => {
    return new Intl.NumberFormat("fr-FR").format(Number(amount || 0)) + " FCFA";
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
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Vue d&apos;ensemble</h1>
          <p className="text-sm text-gray-500 mt-1">
            Performance générale, activité clients et contrôle opérationnel
          </p>
        </div>
        <div className="rounded-full bg-green-50 px-3 py-1 text-xs font-medium text-green-700">
          Mise à jour automatique toutes les 30s
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          title="Sessions aujourd'hui"
          value={stats?.sessions_today || 0}
          icon={<MessageSquare className="w-5 h-5 text-blue-600" />}
          bgColor="bg-blue-50"
          subtitle={`${stats?.active_sessions || 0} actives maintenant`}
        />
        <StatCard
          title="Handoffs en attente"
          value={stats?.pending_handoffs || 0}
          icon={<AlertTriangle className="w-5 h-5 text-orange-600" />}
          bgColor="bg-orange-50"
          subtitle={`${stats?.handoff_rate || 0}% sur 30 jours`}
          highlight={true}
        />
        <StatCard
          title="Commandes du jour"
          value={stats?.orders_today || 0}
          icon={<Package className="w-5 h-5 text-green-600" />}
          bgColor="bg-green-50"
          subtitle={`${stats?.resolved_today || 0} sessions résolues`}
        />
        <StatCard
          title="CA estimé (IA)"
          value={formatFCFA(stats?.estimated_revenue_today || 0)}
          icon={<TrendingUp className="w-5 h-5 text-purple-600" />}
          bgColor="bg-purple-50"
          subtitle="Basé sur les devis détectés"
          isText={true}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          title="Messages aujourd'hui"
          value={stats?.messages_today || 0}
          icon={<Activity className="w-5 h-5 text-cyan-600" />}
          bgColor="bg-cyan-50"
          subtitle={`Pic 14j : ${peakActivity} messages`}
        />
        <StatCard
          title="Taux d'automatisation"
          value={`${stats?.automation_rate || 0}%`}
          icon={<Bot className="w-5 h-5 text-indigo-600" />}
          bgColor="bg-indigo-50"
          subtitle={`${stats?.bot_messages_today || 0} réponses bot aujourd'hui`}
          isText={true}
        />
        <StatCard
          title="Taux de résolution"
          value={`${stats?.resolution_rate || 0}%`}
          icon={<CheckCircle2 className="w-5 h-5 text-emerald-600" />}
          bgColor="bg-emerald-50"
          subtitle="Sur les 30 derniers jours"
          isText={true}
        />
        <StatCard
          title="Clients enregistrés"
          value={stats?.total_clients || 0}
          icon={<Users className="w-5 h-5 text-slate-600" />}
          bgColor="bg-slate-100"
          subtitle={`${stats?.client_messages_today || 0} messages clients aujourd'hui`}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <LineChart
          title="Activité conversations / messages"
          subtitle="Évolution des 14 derniers jours"
          data={dailyMetrics}
          series={[
            { key: "sessions", label: "Sessions", color: "#2563eb" },
            { key: "messages", label: "Messages", color: "#0891b2" },
          ]}
        />
        <BarChart
          title="Commandes & transferts humains"
          subtitle="Détection des pics opérationnels"
          data={dailyMetrics}
          series={[
            { key: "orders", label: "Commandes", color: "bg-green-500" },
            { key: "handoffs", label: "Handoffs", color: "bg-orange-500" },
          ]}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <DistributionCard
          title="Statuts des sessions"
          items={stats?.session_status || []}
          labelKey="status"
          valueKey="sessions"
          labels={statusLabels}
          color="bg-blue-500"
        />
        <DistributionCard
          title="Sources des messages"
          items={stats?.message_sources || []}
          labelKey="sender"
          valueKey="messages"
          labels={sourceLabels}
          color="bg-purple-500"
        />
        <DistributionCard
          title="Types de commandes"
          items={stats?.order_types || []}
          labelKey="order_type"
          valueKey="orders"
          labels={orderTypeLabels}
          color="bg-green-500"
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
            <Zap className="w-5 h-5 text-blue-500" />
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
  subtitle,
  highlight = false,
  isText = false,
}: {
  title: string;
  value: number | string;
  icon: ReactNode;
  bgColor: string;
  subtitle?: string;
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
      {subtitle && <p className="text-xs text-gray-400 mt-2">{subtitle}</p>}
    </div>
  );
}

function LineChart({
  title,
  subtitle,
  data,
  series,
}: {
  title: string;
  subtitle: string;
  data: DailyMetric[];
  series: { key: MetricKey; label: string; color: string }[];
}) {
  const width = 640;
  const height = 260;
  const padding = 34;
  const chartHeight = height - padding * 2;
  const chartWidth = width - padding * 2;
  const maxValue = Math.max(1, ...data.flatMap((item) => series.map((s) => Number(item[s.key] || 0))));

  const getPoint = (item: DailyMetric, index: number, key: MetricKey) => {
    const x = padding + (data.length <= 1 ? 0 : (index / (data.length - 1)) * chartWidth);
    const y = padding + chartHeight - (Number(item[key] || 0) / maxValue) * chartHeight;
    return `${x},${y}`;
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between mb-4">
        <div>
          <h2 className="font-semibold text-gray-900">{title}</h2>
          <p className="text-xs text-gray-500">{subtitle}</p>
        </div>
        <div className="flex flex-wrap gap-3">
          {series.map((s) => (
            <span key={s.key} className="flex items-center gap-1 text-xs text-gray-500">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      </div>
      <div className="w-full overflow-hidden">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-64 w-full">
          {[0, 1, 2, 3].map((step) => {
            const y = padding + (step / 3) * chartHeight;
            return (
              <line
                key={step}
                x1={padding}
                x2={width - padding}
                y1={y}
                y2={y}
                stroke="#e5e7eb"
                strokeDasharray="4 4"
              />
            );
          })}
          {series.map((s) => (
            <polyline
              key={s.key}
              points={data.map((item, index) => getPoint(item, index, s.key)).join(" ")}
              fill="none"
              stroke={s.color}
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
          {series.map((s) =>
            data.map((item, index) => {
              const [x, y] = getPoint(item, index, s.key).split(",").map(Number);
              return <circle key={`${s.key}-${item.day}`} cx={x} cy={y} r="3" fill={s.color} />;
            })
          )}
          {data.map((item, index) => {
            const x = padding + (data.length <= 1 ? 0 : (index / (data.length - 1)) * chartWidth);
            return (
              <text key={item.day} x={x} y={height - 8} textAnchor="middle" className="fill-gray-400 text-[10px]">
                {index % 2 === 0 || data.length <= 8 ? item.label : ""}
              </text>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

function BarChart({
  title,
  subtitle,
  data,
  series,
}: {
  title: string;
  subtitle: string;
  data: DailyMetric[];
  series: { key: MetricKey; label: string; color: string }[];
}) {
  const maxValue = Math.max(1, ...data.flatMap((item) => series.map((s) => Number(item[s.key] || 0))));

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between mb-6">
        <div>
          <h2 className="font-semibold text-gray-900">{title}</h2>
          <p className="text-xs text-gray-500">{subtitle}</p>
        </div>
        <div className="flex flex-wrap gap-3">
          {series.map((s) => (
            <span key={s.key} className="flex items-center gap-1 text-xs text-gray-500">
              <span className={`h-2 w-2 rounded-full ${s.color}`} />
              {s.label}
            </span>
          ))}
        </div>
      </div>
      <div className="flex h-64 items-end gap-2 border-b border-gray-100 pb-2">
        {data.map((item) => (
          <div key={item.day} className="flex min-w-0 flex-1 flex-col items-center gap-2">
            <div className="flex h-52 w-full items-end justify-center gap-1">
              {series.map((s) => (
                <div
                  key={s.key}
                  title={`${s.label}: ${Number(item[s.key] || 0)}`}
                  className={`w-full max-w-4 rounded-t ${s.color}`}
                  style={{ height: `${Math.max(3, (Number(item[s.key] || 0) / maxValue) * 100)}%` }}
                />
              ))}
            </div>
            <span className="text-[10px] text-gray-400">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DistributionCard({
  title,
  items,
  labelKey,
  valueKey,
  labels,
  color,
}: {
  title: string;
  items: DistributionItem[];
  labelKey: string;
  valueKey: string;
  labels: Record<string, string>;
  color: string;
}) {
  const total = items.reduce((sum, item) => sum + Number(item[valueKey] || 0), 0);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h2 className="font-semibold text-gray-900 mb-1">{title}</h2>
      <p className="text-xs text-gray-500 mb-5">{total} éléments sur les 30 derniers jours</p>
      <div className="space-y-4">
        {items.length === 0 && <p className="text-sm text-gray-400">Aucune donnée disponible</p>}
        {items.map((item) => {
          const rawLabel = String(item[labelKey] || "N/A");
          const label = labels[rawLabel] || rawLabel;
          const value = Number(item[valueKey] || 0);
          const percent = total ? Math.round((value / total) * 100) : 0;

          return (
            <div key={rawLabel}>
              <div className="mb-1 flex items-center justify-between gap-3 text-sm">
                <span className="truncate text-gray-700">{label}</span>
                <span className="font-medium text-gray-900">{value}</span>
              </div>
              <div className="h-2 rounded-full bg-gray-100">
                <div className={`h-2 rounded-full ${color}`} style={{ width: `${percent}%` }} />
              </div>
              <p className="mt-1 text-[11px] text-gray-400">{percent}% du total</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
