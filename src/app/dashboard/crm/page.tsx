"use client";

import { useCallback, useEffect, useState } from "react";
import { Search, Users, Phone, Package, Calendar, TrendingUp, X, ExternalLink, ChevronRight } from "lucide-react";

interface Client {
  id: string;
  phone_number: string;
  first_name: string | null;
  last_name: string | null;
  client_type: string;
  first_contact: string;
  session_count: number;
  order_count: number;
  last_activity: string | null;
  last_summary: string | null;
  last_order_type: string | null;
  last_order_status: string | null;
  total_revenue: number;
}

interface Order {
  id: string;
  order_number: string;
  order_type: string;
  status: string;
  estimated_price: number | null;
  created_at: string;
  data: Record<string, unknown>;
}

const ORDER_TYPE_LABELS: Record<string, string> = {
  FRET_AERIEN: "Fret Aérien",
  FRET_MARITIME: "Fret Maritime",
  FRET: "Fret",
  BILLETTERIE: "Billetterie",
  PAIEMENT_FOURNISSEUR: "Paiement Fournisseur",
  SOURCING: "Sourcing",
  AUTRE: "Autre",
};

const STATUS_STYLES: Record<string, string> = {
  NOUVEAU: "bg-blue-100 text-blue-700",
  PRIS_EN_CHARGE: "bg-yellow-100 text-yellow-700",
  EN_COURS: "bg-indigo-100 text-indigo-700",
  LIVRE: "bg-green-100 text-green-700",
  ANNULE: "bg-red-100 text-red-700",
};

const STATUS_LABELS: Record<string, string> = {
  NOUVEAU: "Nouveau",
  PRIS_EN_CHARGE: "Pris en charge",
  EN_COURS: "En cours",
  LIVRE: "Terminé",
  ANNULE: "Annulé",
};

function formatDate(dateStr: string | null) {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function formatRelative(dateStr: string | null) {
  if (!dateStr) return "—";
  const diffMs = Date.now() - new Date(dateStr).getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays === 0) return "Aujourd'hui";
  if (diffDays === 1) return "Hier";
  if (diffDays < 7) return `Il y a ${diffDays}j`;
  if (diffDays < 30) return `Il y a ${Math.floor(diffDays / 7)}sem`;
  return `Il y a ${Math.floor(diffDays / 30)}mois`;
}

function formatFCFA(amount: number) {
  if (!amount) return "—";
  return new Intl.NumberFormat("fr-FR").format(amount) + " FCFA";
}

function clientInitials(c: Client) {
  const name = c.first_name || c.phone_number;
  return name.slice(0, 2).toUpperCase();
}

function clientDisplayName(c: Client) {
  if (c.first_name) return `${c.first_name}${c.last_name ? " " + c.last_name : ""}`;
  return c.phone_number;
}

export default function CRMPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Client | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(false);

  const fetchClients = useCallback(async (q = "") => {
    try {
      const params = q.trim() ? `?search=${encodeURIComponent(q.trim())}` : "";
      const res = await fetch(`/api/dashboard/clients${params}`);
      if (res.ok) {
        const data = await res.json();
        setClients(data.clients || []);
      }
    } catch {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    fetchClients();
  }, [fetchClients]);

  useEffect(() => {
    const t = setTimeout(() => fetchClients(search), 350);
    return () => clearTimeout(t);
  }, [search, fetchClients]);

  const openClient = async (client: Client) => {
    setSelected(client);
    setOrders([]);
    setOrdersLoading(true);
    try {
      const res = await fetch(`/api/dashboard/clients/${client.id}/orders`);
      if (res.ok) {
        const data = await res.json();
        setOrders(data.orders || []);
      }
    } catch {}
    finally { setOrdersLoading(false); }
  };

  const totalClients = clients.length;
  const totalOrders = clients.reduce((s, c) => s + c.order_count, 0);
  const totalRevenue = clients.reduce((s, c) => s + c.total_revenue, 0);
  const activeClients = clients.filter(c => c.last_activity && Date.now() - new Date(c.last_activity).getTime() < 30 * 86400000).length;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">CRM Clients</h1>
          <p className="text-sm text-gray-500 mt-1">Vue d'ensemble de tous les clients et leur historique</p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {[
          { label: "Total clients", value: totalClients, icon: <Users className="w-5 h-5 text-blue-600" />, bg: "bg-blue-50" },
          { label: "Actifs (30 jours)", value: activeClients, icon: <TrendingUp className="w-5 h-5 text-green-600" />, bg: "bg-green-50" },
          { label: "Commandes totales", value: totalOrders, icon: <Package className="w-5 h-5 text-purple-600" />, bg: "bg-purple-50" },
          { label: "CA estimé total", value: formatFCFA(totalRevenue), icon: <TrendingUp className="w-5 h-5 text-orange-600" />, bg: "bg-orange-50", isText: true },
        ].map((s) => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-200 p-4">
            <div className={`w-9 h-9 ${s.bg} rounded-lg flex items-center justify-center mb-3`}>{s.icon}</div>
            <p className={`font-bold ${s.isText ? "text-base" : "text-2xl"} text-gray-900`}>{s.value}</p>
            <p className="text-xs text-gray-500 mt-1">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Rechercher par nom ou numéro..."
          className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none bg-white"
        />
      </div>

      {/* Client list */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-48">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" />
          </div>
        ) : clients.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-gray-400">
            <Users className="w-10 h-10 mb-2 opacity-30" />
            <p className="text-sm">Aucun client trouvé</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Client</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide hidden md:table-cell">1er contact</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide hidden sm:table-cell">Sessions</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Commandes</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide hidden lg:table-cell">Dernière activité</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide hidden xl:table-cell">Résumé</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {clients.map((client) => (
                  <tr
                    key={client.id}
                    onClick={() => openClient(client)}
                    className="hover:bg-gray-50 cursor-pointer transition"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
                          <span className="text-xs font-bold text-blue-700">{clientInitials(client)}</span>
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">{clientDisplayName(client)}</p>
                          <p className="text-xs text-gray-400 flex items-center gap-1">
                            <Phone className="w-3 h-3" />{client.phone_number}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell">
                      <div className="flex items-center gap-1 text-xs text-gray-500">
                        <Calendar className="w-3 h-3" />
                        {formatDate(client.first_contact)}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center hidden sm:table-cell">
                      <span className="text-sm font-medium text-gray-700">{client.session_count}</span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-sm font-bold ${
                        client.order_count > 0 ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-400"
                      }`}>
                        {client.order_count}
                      </span>
                    </td>
                    <td className="px-4 py-3 hidden lg:table-cell">
                      <span className="text-xs text-gray-500">{formatRelative(client.last_activity)}</span>
                    </td>
                    <td className="px-4 py-3 hidden xl:table-cell max-w-xs">
                      <p className="text-xs text-gray-500 truncate">{client.last_summary || "—"}</p>
                    </td>
                    <td className="px-4 py-3">
                      <ChevronRight className="w-4 h-4 text-gray-300" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Side panel */}
      {selected && (
        <div className="fixed inset-0 z-50 flex justify-end" onClick={() => setSelected(null)}>
          <div
            className="w-full max-w-lg bg-white shadow-2xl h-full overflow-y-auto flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="p-5 border-b border-gray-100 flex items-start justify-between sticky top-0 bg-white z-10">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center">
                  <span className="text-base font-bold text-blue-700">{clientInitials(selected)}</span>
                </div>
                <div>
                  <h2 className="font-semibold text-gray-900">{clientDisplayName(selected)}</h2>
                  <p className="text-sm text-gray-500 flex items-center gap-1">
                    <Phone className="w-3 h-3" />{selected.phone_number}
                  </p>
                </div>
              </div>
              <button onClick={() => setSelected(null)} className="p-1.5 hover:bg-gray-100 rounded-lg transition">
                <X className="w-4 h-4 text-gray-400" />
              </button>
            </div>

            <div className="p-5 space-y-5 flex-1">
              {/* Key stats */}
              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: "Sessions", value: selected.session_count },
                  { label: "Commandes", value: selected.order_count },
                  { label: "CA estimé", value: selected.total_revenue ? formatFCFA(selected.total_revenue) : "—", small: true },
                ].map((s) => (
                  <div key={s.label} className="bg-gray-50 rounded-xl p-3 text-center">
                    <p className={`font-bold text-gray-900 ${s.small ? "text-sm" : "text-xl"}`}>{s.value}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{s.label}</p>
                  </div>
                ))}
              </div>

              {/* Info */}
              <div className="space-y-2">
                <div className="flex items-center justify-between py-2 border-b border-gray-50">
                  <span className="text-xs text-gray-500">Premier contact</span>
                  <span className="text-sm font-medium text-gray-900">{formatDate(selected.first_contact)}</span>
                </div>
                <div className="flex items-center justify-between py-2 border-b border-gray-50">
                  <span className="text-xs text-gray-500">Dernière activité</span>
                  <span className="text-sm font-medium text-gray-900">{formatRelative(selected.last_activity)}</span>
                </div>
                <div className="flex items-center justify-between py-2 border-b border-gray-50">
                  <span className="text-xs text-gray-500">Type client</span>
                  <span className="text-sm font-medium text-gray-900">{selected.client_type || "NEW"}</span>
                </div>
              </div>

              {/* Last summary */}
              {selected.last_summary && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Dernier résumé IA</p>
                  <div className="bg-amber-50 border border-amber-100 rounded-lg p-3 text-sm text-amber-800 leading-relaxed">
                    {selected.last_summary}
                  </div>
                </div>
              )}

              {/* Orders */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Historique commandes</p>
                {ordersLoading ? (
                  <div className="flex justify-center py-6">
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600" />
                  </div>
                ) : orders.length === 0 ? (
                  <div className="text-center py-6 text-sm text-gray-400">
                    <Package className="w-8 h-8 mx-auto mb-2 opacity-30" />
                    Aucune commande
                  </div>
                ) : (
                  <div className="space-y-2">
                    {orders.map((order) => {
                      const data = typeof order.data === "string" ? JSON.parse(order.data) : order.data || {};
                      return (
                        <div key={order.id} className="border border-gray-100 rounded-xl p-3 bg-gray-50">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-xs font-semibold text-gray-700">{order.order_number}</span>
                                <span className="text-xs text-gray-500">{ORDER_TYPE_LABELS[order.order_type] || order.order_type}</span>
                              </div>
                              {(data.origin || data.destination) && (
                                <p className="text-xs text-gray-500 mt-0.5">
                                  {[data.origin, data.destination].filter(Boolean).join(" → ")}
                                </p>
                              )}
                              {data.notes && (
                                <p className="text-xs text-gray-400 mt-1 line-clamp-2">{data.notes}</p>
                              )}
                            </div>
                            <div className="flex flex-col items-end gap-1 flex-shrink-0">
                              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${STATUS_STYLES[order.status] || "bg-gray-100 text-gray-500"}`}>
                                {STATUS_LABELS[order.status] || order.status}
                              </span>
                              {order.estimated_price && (
                                <span className="text-xs font-semibold text-blue-600">{formatFCFA(order.estimated_price)}</span>
                              )}
                            </div>
                          </div>
                          <p className="text-[10px] text-gray-400 mt-2">{formatDate(order.created_at)}</p>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-gray-100 bg-gray-50 flex gap-2">
              <a
                href={`/dashboard/inbox?phone=${selected.phone_number.replace("+", "")}`}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition"
              >
                <ExternalLink className="w-4 h-4" />
                Voir dans l'Inbox
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
