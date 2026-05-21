"use client";

import { useEffect, useState } from "react";
import { Package, Plane, ShoppingBag } from "lucide-react";

interface Order {
  id: string;
  order_number: string;
  phone_number: string;
  first_name: string | null;
  last_name: string | null;
  order_type: string;
  status: string;
  data: Record<string, unknown>;
  estimated_price: number | null;
  final_price: number | null;
  created_at: string;
}

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [activeTab, setActiveTab] = useState("FRET");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchOrders();
  }, [activeTab]);

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/dashboard/orders?order_type=${activeTab}`);
      if (res.ok) {
        const data = await res.json();
        setOrders(data.orders || []);
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

  const getStatusBadge = (status: string) => {
    const styles: Record<string, string> = {
      NOUVEAU: "bg-yellow-100 text-yellow-700",
      PRIS_EN_CHARGE: "bg-blue-100 text-blue-700",
      EN_COURS: "bg-purple-100 text-purple-700",
      LIVRE: "bg-green-100 text-green-700",
      ANNULE: "bg-gray-100 text-gray-600",
      HANDOFF: "bg-red-100 text-red-700",
    };
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${styles[status] || "bg-gray-100"}`}>
        {status.replace("_", " ")}
      </span>
    );
  };

  const tabs = [
    { key: "FRET", label: "Fret & Expédition", icon: Package },
    { key: "BILLETTERIE", label: "Billetterie", icon: Plane },
    { key: "PACK", label: "Packs Importation", icon: ShoppingBag },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Commandes</h1>
        <p className="text-sm text-gray-500 mt-1">Gestion des commandes pré-qualifiées par l&apos;IA</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 overflow-x-auto">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition ${
                activeTab === tab.key
                  ? "bg-blue-600 text-white"
                  : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Orders Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-sm text-gray-500">Chargement...</div>
        ) : orders.length === 0 ? (
          <div className="p-8 text-center text-sm text-gray-500">Aucune commande pour cette catégorie</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">N° Commande</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Client</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Détails</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Estimation</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Statut</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {orders.map((order) => (
                  <tr key={order.id} className="hover:bg-gray-50 transition">
                    <td className="px-4 py-3 font-mono text-xs font-medium text-blue-600">
                      {order.order_number}
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900">
                        {order.first_name || "Inconnu"}
                      </p>
                      <p className="text-xs text-gray-500">{order.phone_number}</p>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600 max-w-[200px] truncate">
                      {JSON.stringify(order.data).substring(0, 60)}...
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {order.estimated_price ? formatFCFA(order.estimated_price) : "—"}
                    </td>
                    <td className="px-4 py-3">{getStatusBadge(order.status)}</td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {new Date(order.created_at).toLocaleDateString("fr-FR")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
