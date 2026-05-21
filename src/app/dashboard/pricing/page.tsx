"use client";

import { useEffect, useState } from "react";
import { Save, Plus, Trash2, DollarSign } from "lucide-react";

interface PricingGrid {
  id: string;
  mode: string;
  origin: string;
  rules: PricingRule[];
  currency: string;
  valid_from: string;
  updated_by: string | null;
}

interface PricingRule {
  min_weight: number;
  max_weight: number;
  price_per_kg?: number;
  price_per_cbm?: number;
  price_fixed?: number;
  price_per_tonne?: number;
}

const MODE_LABELS: Record<string, string> = {
  aerien_chine: "Aerien - Chine",
  aerien_international: "Aerien - International",
  maritime: "Maritime",
  dhl_express: "DHL Express",
  gros_volumes_export: "Gros Volumes Export",
};

export default function PricingPage() {
  const [grids, setGrids] = useState<PricingGrid[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingGrid, setEditingGrid] = useState<PricingGrid | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  useEffect(() => {
    fetchGrids();
  }, []);

  const fetchGrids = async () => {
    try {
      const res = await fetch("/api/dashboard/pricing");
      if (res.ok) {
        const data = await res.json();
        setGrids(data.grids || []);
      }
    } catch {
      // Silent fail
    } finally {
      setLoading(false);
    }
  };

  const openEditor = (grid: PricingGrid) => {
    setEditingGrid(JSON.parse(JSON.stringify(grid)));
    setSaveMsg("");
  };

  const updateRule = (index: number, field: string, value: string) => {
    if (!editingGrid) return;
    const rules = [...editingGrid.rules];
    (rules[index] as unknown as Record<string, unknown>)[field] = parseFloat(value) || 0;
    setEditingGrid({ ...editingGrid, rules });
  };

  const addRule = () => {
    if (!editingGrid) return;
    const rules = [...editingGrid.rules];
    const lastMax = rules.length > 0 ? rules[rules.length - 1].max_weight : 0;
    rules.push({ min_weight: lastMax, max_weight: lastMax + 100, price_per_kg: 0 });
    setEditingGrid({ ...editingGrid, rules });
  };

  const removeRule = (index: number) => {
    if (!editingGrid) return;
    const rules = editingGrid.rules.filter((_, i) => i !== index);
    setEditingGrid({ ...editingGrid, rules });
  };

  const saveGrid = async () => {
    if (!editingGrid) return;
    setSaving(true);
    try {
      const res = await fetch("/api/dashboard/pricing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: editingGrid.mode,
          origin: editingGrid.origin,
          rules: editingGrid.rules,
          updated_by: "dashboard",
        }),
      });
      if (res.ok) {
        setSaveMsg("Grille mise a jour avec succes");
        fetchGrids();
        setTimeout(() => {
          setEditingGrid(null);
          setSaveMsg("");
        }, 1500);
      }
    } catch {
      setSaveMsg("Erreur lors de la sauvegarde");
    } finally {
      setSaving(false);
    }
  };

  const getPriceField = (rule: PricingRule): { field: string; label: string } => {
    if (rule.price_per_kg !== undefined && rule.price_per_kg > 0) return { field: "price_per_kg", label: "Prix/kg" };
    if (rule.price_per_cbm !== undefined && rule.price_per_cbm > 0) return { field: "price_per_cbm", label: "Prix/m3" };
    if (rule.price_fixed !== undefined && rule.price_fixed > 0) return { field: "price_fixed", label: "Prix fixe" };
    if (rule.price_per_tonne !== undefined && rule.price_per_tonne > 0) return { field: "price_per_tonne", label: "Prix/tonne" };
    return { field: "price_per_kg", label: "Prix/kg" };
  };

  const formatFCFA = (amount: number) => new Intl.NumberFormat("fr-FR").format(amount) + " FCFA";

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
        <h1 className="text-2xl font-bold text-gray-900">Grilles Tarifaires</h1>
        <p className="text-sm text-gray-500 mt-1">
          Gestion des tarifs par mode de transport. Mises a jour mensuelles.
        </p>
      </div>

      {/* Grids List */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {grids.map((grid) => (
          <div
            key={grid.id}
            className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md transition cursor-pointer"
            onClick={() => openEditor(grid)}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center">
                  <DollarSign className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900 text-sm">
                    {MODE_LABELS[grid.mode] || grid.mode}
                  </h3>
                  <p className="text-xs text-gray-500">
                    Origine: {grid.origin || "N/A"}
                  </p>
                </div>
              </div>
              <span className="text-[10px] bg-green-50 text-green-700 px-2 py-0.5 rounded-full font-medium">
                Actif
              </span>
            </div>

            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-1 text-gray-500 font-medium">Tranche</th>
                  <th className="text-right py-1 text-gray-500 font-medium">Prix</th>
                </tr>
              </thead>
              <tbody>
                {(Array.isArray(grid.rules) ? grid.rules : []).slice(0, 4).map((rule, i) => {
                  const { label } = getPriceField(rule);
                  const priceValue = rule.price_per_kg || rule.price_per_cbm || rule.price_fixed || rule.price_per_tonne || 0;
                  return (
                    <tr key={i} className="border-b border-gray-50">
                      <td className="py-1.5 text-gray-700">
                        {rule.min_weight} - {rule.max_weight >= 999999 ? "+" : rule.max_weight} kg
                      </td>
                      <td className="py-1.5 text-right font-medium text-gray-900">
                        {formatFCFA(priceValue)} <span className="text-gray-400">({label})</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            <p className="text-[10px] text-gray-400 mt-2">
              Mis a jour: {new Date(grid.valid_from).toLocaleDateString("fr-FR")}
            </p>
          </div>
        ))}
      </div>

      {/* Editor Modal */}
      {editingGrid && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl w-full max-w-lg max-h-[90vh] overflow-auto">
            <div className="p-5 border-b border-gray-100">
              <h2 className="font-semibold text-gray-900">
                Modifier: {MODE_LABELS[editingGrid.mode] || editingGrid.mode}
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Origine: {editingGrid.origin}
              </p>
            </div>

            <div className="p-5 space-y-3">
              {editingGrid.rules.map((rule, i) => {
                const { field, label } = getPriceField(rule);
                const priceValue = (rule as unknown as Record<string, unknown>)[field] as number || 0;
                return (
                  <div key={i} className="flex items-center gap-2 bg-gray-50 p-3 rounded-lg">
                    <div className="flex-1 grid grid-cols-3 gap-2">
                      <div>
                        <label className="text-[10px] text-gray-500 block">Min (kg)</label>
                        <input
                          type="number"
                          value={rule.min_weight}
                          onChange={(e) => updateRule(i, "min_weight", e.target.value)}
                          className="w-full px-2 py-1.5 border border-gray-200 rounded text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] text-gray-500 block">Max (kg)</label>
                        <input
                          type="number"
                          value={rule.max_weight}
                          onChange={(e) => updateRule(i, "max_weight", e.target.value)}
                          className="w-full px-2 py-1.5 border border-gray-200 rounded text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] text-gray-500 block">{label}</label>
                        <input
                          type="number"
                          value={priceValue}
                          onChange={(e) => updateRule(i, field, e.target.value)}
                          className="w-full px-2 py-1.5 border border-gray-200 rounded text-sm"
                        />
                      </div>
                    </div>
                    <button
                      onClick={() => removeRule(i)}
                      className="p-1.5 text-red-400 hover:text-red-600 hover:bg-red-50 rounded"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                );
              })}

              <button
                onClick={addRule}
                className="w-full py-2 border border-dashed border-gray-300 rounded-lg text-sm text-gray-500 hover:border-blue-400 hover:text-blue-600 flex items-center justify-center gap-1 transition"
              >
                <Plus className="w-4 h-4" />
                Ajouter une tranche
              </button>
            </div>

            {saveMsg && (
              <div className={`mx-5 p-2 rounded text-xs text-center ${saveMsg.includes("succes") ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
                {saveMsg}
              </div>
            )}

            <div className="p-5 border-t border-gray-100 flex justify-end gap-2">
              <button
                onClick={() => setEditingGrid(null)}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition"
              >
                Annuler
              </button>
              <button
                onClick={saveGrid}
                disabled={saving}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1.5 transition"
              >
                <Save className="w-4 h-4" />
                {saving ? "Sauvegarde..." : "Sauvegarder"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
