"use client";

import { useEffect, useState } from "react";
import { Package, Plane, ShoppingBag, X } from "lucide-react";

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
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);

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

  const getClientName = (order: Order) => {
    if (order.first_name || order.last_name) {
      return `${order.first_name || ""} ${order.last_name || ""}`.trim();
    }
    // Fallback if the bot saved the name in the JSON but not in the clients table yet
    const dataName = (order.data as Record<string, string>)?.client_name;
    if (dataName && dataName !== "null") return dataName;
    return "Inconnu";
  };

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
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Marchandise / Service</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Estimation</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Statut</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {orders.map((order) => {
                  const data = order.data as Record<string, string>;
                  const summaryText = data?.goods_nature || data?.notes || "Détails non spécifiés";

                  return (
                    <tr 
                      key={order.id} 
                      onClick={() => setSelectedOrder(order)}
                      className="hover:bg-blue-50 cursor-pointer transition"
                    >
                      <td className="px-4 py-3 font-mono text-xs font-medium text-blue-600">
                        {order.order_number}
                      </td>
                      <td className="px-4 py-3">
                        <p className="font-medium text-gray-900">
                          {getClientName(order)}
                        </p>
                        <p className="text-xs text-gray-500">{order.phone_number}</p>
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-600 max-w-[250px] truncate">
                        {summaryText}
                      </td>
                      <td className="px-4 py-3 font-medium text-gray-900">
                        {order.estimated_price ? formatFCFA(order.estimated_price) : "—"}
                      </td>
                      <td className="px-4 py-3">{getStatusBadge(order.status)}</td>
                      <td className="px-4 py-3 text-xs text-gray-500">
                        {new Date(order.created_at).toLocaleString("fr-FR", {
                          dateStyle: "short",
                          timeStyle: "short"
                        })}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {selectedOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-gray-100">
              <div>
                <div className="flex items-center gap-3 mb-1">
                  <h2 className="text-xl font-bold text-gray-900">Commande {selectedOrder.order_number}</h2>
                  {getStatusBadge(selectedOrder.status)}
                </div>
                <p className="text-sm text-gray-500">
                  Par {getClientName(selectedOrder)} ({selectedOrder.phone_number}) le {new Date(selectedOrder.created_at).toLocaleString("fr-FR")}
                </p>
              </div>
              <button 
                onClick={() => setSelectedOrder(null)}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Body */}
            <div className="p-6 overflow-y-auto">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                
                <div className="space-y-4">
                  <h3 className="font-semibold text-gray-900 border-b pb-2">Informations Principales</h3>
                  
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Type de service</p>
                    <p className="text-sm font-medium">{selectedOrder.order_type}</p>
                  </div>
                  
                  {activeTab === "FRET" ? (
                    <>
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Trajet (Origine ➔ Destination)</p>
                        <p className="text-sm font-medium">
                          {String((selectedOrder.data as any)?.origin || "—")} ➔ {String((selectedOrder.data as any)?.destination || "—")}
                        </p>
                      </div>
                      
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Nature de la marchandise</p>
                        <p className="text-sm font-medium">{String((selectedOrder.data as any)?.goods_nature || "—")}</p>
                      </div>

                      <div className="flex gap-6">
                        <div>
                          <p className="text-xs text-gray-500 mb-1">Poids estimé</p>
                          <p className="text-sm font-medium">
                            {(selectedOrder.data as any)?.weight_kg ? `${(selectedOrder.data as any).weight_kg} kg` : "—"}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-gray-500 mb-1">Dimensions</p>
                          <p className="text-sm font-medium">
                            {(selectedOrder.data as any)?.dimensions || "—"}
                          </p>
                        </div>
                      </div>
                    </>
                  ) : activeTab === "BILLETTERIE" ? (
                    <>
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Détails de Vol (Passagers, Dates, Classe)</p>
                        <p className="text-sm font-medium whitespace-pre-wrap">{String((selectedOrder.data as any)?.goods_nature || "—")}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Destination</p>
                        <p className="text-sm font-medium">{String((selectedOrder.data as any)?.destination || "—")}</p>
                      </div>
                    </>
                  ) : null}
                  
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Estimation Prix</p>
                    <p className="text-sm font-bold text-blue-600">
                      {selectedOrder.estimated_price ? formatFCFA(selectedOrder.estimated_price) : "Non définie / Sur devis"}
                    </p>
                  </div>
                </div>

                <div className="space-y-4">
                  <h3 className="font-semibold text-gray-900 border-b pb-2">Notes et Résumé IA</h3>
                  <div className="bg-gray-50 p-4 rounded-xl text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                    {String((selectedOrder.data as any)?.notes || "Aucun résumé disponible.")}
                  </div>
                  
                  {(selectedOrder.data as any)?.is_sensitive && (
                    <div className="mt-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm font-medium flex items-center gap-2">
                      <span className="flex-shrink-0 w-2 h-2 rounded-full bg-red-600"></span>
                      Cette demande a été marquée comme sensible ou nécessitant une attention particulière.
                    </div>
                  )}
                </div>

              </div>
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-gray-100 bg-gray-50 flex justify-end gap-3">
              <button 
                onClick={() => setSelectedOrder(null)}
                className="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 transition"
              >
                Fermer
              </button>
              {/* Future: Edit Status Button */}
              <button className="px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition shadow-sm">
                Traiter le dossier
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
