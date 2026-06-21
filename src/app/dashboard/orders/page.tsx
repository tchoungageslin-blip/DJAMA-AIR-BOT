"use client";

import { useEffect, useState } from "react";
import { Package, Plane, ShoppingBag, X, Search, ShieldCheck, CreditCard, Ship, MoreHorizontal } from "lucide-react";

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
  is_read?: boolean;
}

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [activeTab, setActiveTab] = useState("FRET_AERIEN");
  const [loading, setLoading] = useState(true);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [badges, setBadges] = useState<Record<string, number>>({});

  useEffect(() => {
    fetchBadges();
    fetchOrders();
    const interval = setInterval(fetchBadges, 15000);
    return () => clearInterval(interval);
  }, [activeTab]);

  const fetchBadges = async () => {
    try {
      const res = await fetch("/api/dashboard/orders/badges");
      if (res.ok) {
        const data = await res.json();
        setBadges(data.badges || {});
      }
    } catch {
      // Silent
    }
  };

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

  const markAsRead = async (order: Order) => {
    setSelectedOrder(order);
    if (!order.is_read) {
      try {
        await fetch(`/api/dashboard/orders/${order.id}/read`, { method: "POST" });
        setOrders(orders.map(o => o.id === order.id ? { ...o, is_read: true } : o));
        fetchBadges();
      } catch {
        // Silent
      }
    }
  };

  const updateOrderStatus = async (status: string) => {
    if (!selectedOrder) return;
    try {
      const res = await fetch(`/api/dashboard/orders/${selectedOrder.id}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status })
      });
      if (res.ok) {
        setOrders(orders.map(o => o.id === selectedOrder.id ? { ...o, status } : o));
        setSelectedOrder({ ...selectedOrder, status });
      }
    } catch {
      // Silent fail
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
    { key: "FRET_AERIEN", label: "Fret Aérien", icon: Package },
    { key: "FRET_MARITIME", label: "Fret Maritime", icon: Ship },
    { key: "BILLETTERIE", label: "Billetterie", icon: Plane },
    { key: "PACK", label: "Packs Importation", icon: ShoppingBag },
    { key: "SOURCING", label: "Sourcing / Achat", icon: Search },
    { key: "PAIEMENT", label: "Paiement Fournisseur", icon: CreditCard },
    { key: "INSPECTION", label: "Inspection", icon: ShieldCheck },
    { key: "AUTRE", label: "Autres", icon: MoreHorizontal },
  ];

  const getClientName = (order: Order) => {
    if (order.first_name || order.last_name) {
      return `${order.first_name || ""} ${order.last_name || ""}`.trim();
    }
    const dataName = (order.data as Record<string, string>)?.client_name;
    if (dataName && dataName !== "null") return dataName;
    return "Inconnu";
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Commandes</h1>
          <p className="text-sm text-gray-500 mt-1">Gestion des commandes pré-qualifiées par l&apos;IA</p>
        </div>
        {badges.TOTAL > 0 && (
          <div className="bg-red-100 text-red-700 px-3 py-1 rounded-full text-sm font-bold flex items-center gap-2 animate-pulse">
            <span className="w-2 h-2 rounded-full bg-red-600"></span>
            {badges.TOTAL} nouvelle(s) demande(s)
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-2 overflow-x-auto pb-2 custom-scrollbar">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const badgeCount = badges[tab.key] || 0;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition ${
                activeTab === tab.key
                  ? "bg-blue-600 text-white shadow-md shadow-blue-500/20"
                  : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
              {badgeCount > 0 && (
                <span className="absolute -top-1.5 -right-1.5 bg-red-500 text-white text-[10px] font-bold w-5 h-5 flex items-center justify-center rounded-full border-2 border-white shadow-sm">
                  {badgeCount}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Orders Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-sm text-gray-500">Chargement...</div>
        ) : orders.length === 0 ? (
          <div className="p-12 text-center flex flex-col items-center justify-center">
            <Package className="w-12 h-12 text-gray-300 mb-3" />
            <p className="text-gray-500 font-medium">Aucune commande pour cette catégorie</p>
            <p className="text-sm text-gray-400 mt-1">Les nouvelles demandes apparaîtront ici.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600 w-10"></th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">N° Commande</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Client</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Résumé</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Estimation</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Statut</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {orders.map((order) => {
                  const data = order.data as Record<string, string>;
                  const summaryText = data?.notes || data?.goods_nature || "Détails non spécifiés";
                  const isNew = !order.is_read;

                  return (
                    <tr 
                      key={order.id} 
                      onClick={() => markAsRead(order)}
                      className={`cursor-pointer transition ${isNew ? 'bg-blue-50/50 hover:bg-blue-50' : 'hover:bg-gray-50'}`}
                    >
                      <td className="px-4 py-3">
                        {isNew && <div className="w-2 h-2 rounded-full bg-blue-600"></div>}
                      </td>
                      <td className={`px-4 py-3 font-mono text-xs ${isNew ? 'font-bold text-blue-700' : 'font-medium text-gray-600'}`}>
                        {order.order_number}
                      </td>
                      <td className="px-4 py-3">
                        <p className={`text-gray-900 ${isNew ? 'font-bold' : 'font-medium'}`}>
                          {getClientName(order)}
                        </p>
                        <p className="text-xs text-gray-500">{order.phone_number}</p>
                      </td>
                      <td className={`px-4 py-3 text-xs max-w-[250px] truncate ${isNew ? 'text-gray-800 font-medium' : 'text-gray-600'}`}>
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={(e) => {if(e.target===e.currentTarget) setSelectedOrder(null)}}>
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
                    <p className="text-sm font-medium">{tabs.find(t => t.key === selectedOrder.order_type)?.label || selectedOrder.order_type}</p>
                  </div>
                  
                  {selectedOrder.order_type.startsWith("FRET") ? (
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
                  ) : selectedOrder.order_type === "BILLETTERIE" ? (
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
                  ) : (
                     <>
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Détails de la demande</p>
                        <p className="text-sm font-medium whitespace-pre-wrap">{String((selectedOrder.data as any)?.goods_nature || "—")}</p>
                      </div>
                     </>
                  )}
                  
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

                {(() => {
                  const attachments: Array<{media_url: string; media_type: string}> = (selectedOrder.data as any)?.attachments || [];
                  if (attachments.length === 0) return null;
                  return (
                    <div className="space-y-3">
                      <h3 className="font-semibold text-gray-900 border-b pb-2">Pièces jointes ({attachments.length})</h3>
                      <div className="flex flex-wrap gap-3">
                        {attachments.map((att, idx) => {
                          const isImage = att.media_type?.startsWith("image/");
                          const isPdf = att.media_type === "application/pdf";
                          if (isImage) {
                            return (
                              <a key={idx} href={att.media_url} target="_blank" rel="noopener noreferrer" className="block">
                                <img
                                  src={att.media_url}
                                  alt={`Pièce jointe ${idx + 1}`}
                                  className="w-24 h-24 object-cover rounded-lg border border-gray-200 hover:opacity-80 transition"
                                />
                              </a>
                            );
                          }
                          if (isPdf) {
                            return (
                              <a key={idx} href={att.media_url} target="_blank" rel="noopener noreferrer"
                                className="flex flex-col items-center justify-center w-24 h-24 border border-gray-200 rounded-lg bg-gray-50 hover:bg-gray-100 transition text-center p-2">
                                <svg className="w-8 h-8 text-red-500 mb-1" fill="currentColor" viewBox="0 0 24 24">
                                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 1.5L18.5 9H13V3.5zM6 20V4h5v7h7v9H6z"/>
                                </svg>
                                <span className="text-xs text-gray-600">PDF {idx + 1}</span>
                              </a>
                            );
                          }
                          return (
                            <a key={idx} href={att.media_url} target="_blank" rel="noopener noreferrer"
                              className="flex flex-col items-center justify-center w-24 h-24 border border-gray-200 rounded-lg bg-gray-50 hover:bg-gray-100 transition text-center p-2">
                              <svg className="w-8 h-8 text-gray-400 mb-1" fill="currentColor" viewBox="0 0 24 24">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 1.5L18.5 9H13V3.5zM6 20V4h5v7h7v9H6z"/>
                              </svg>
                              <span className="text-xs text-gray-600">Fichier {idx + 1}</span>
                            </a>
                          );
                        })}
                      </div>
                    </div>
                  );
                })()}

              </div>
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-gray-100 bg-gray-50 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-500 font-medium">Statut :</span>
                <select
                  value={selectedOrder.status}
                  onChange={(e) => updateOrderStatus(e.target.value)}
                  className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-medium"
                >
                  <option value="NOUVEAU">Nouveau</option>
                  <option value="PRIS_EN_CHARGE">Pris en charge</option>
                  <option value="EN_COURS">En cours</option>
                  <option value="LIVRE">Terminé / Livré</option>
                  <option value="ANNULE">Annulé / Refusé</option>
                </select>
              </div>

              <div className="flex gap-2">
                <button 
                  onClick={() => setSelectedOrder(null)}
                  className="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 transition bg-white border border-gray-200 rounded-lg shadow-sm"
                >
                  Fermer
                </button>
                <a
                  href={`/dashboard/inbox?phone=${selectedOrder.phone_number.replace('+', '')}`}
                  className="px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition shadow-sm flex items-center gap-2"
                >
                  Contacter le client
                </a>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
