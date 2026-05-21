from typing import Optional, Dict, Tuple
from api.db.connection import execute_query


class PricingEngine:
    """Calculates shipping prices based on the current pricing grid."""

    # Default grids (used if database grids are not available)
    DEFAULT_GRIDS = {
        "aerien_chine": [
            {"min_weight": 0, "max_weight": 25, "price_per_kg": 10000},
            {"min_weight": 25, "max_weight": 100, "price_per_kg": 7500},
            {"min_weight": 100, "max_weight": 999999, "price_per_kg": 6000},
        ],
        "aerien_international": [
            {"min_weight": 0, "max_weight": 100, "price_per_kg": 10500},
            {"min_weight": 100, "max_weight": 999999, "price_per_kg": 8000},
        ],
        "maritime": [
            {"min_weight": 0, "max_weight": 300, "price_per_cbm": 330000},
            {"min_weight": 300, "max_weight": 500, "price_per_cbm": 350000},
            {"min_weight": 500, "max_weight": 800, "price_per_cbm": 370000},
            {"min_weight": 800, "max_weight": 1000, "price_per_cbm": 390000},
            {"min_weight": 1000, "max_weight": 999999, "price_per_tonne": 400000},
        ],
        "dhl_express": {
            "france_europe": [
                {"min_weight": 0, "max_weight": 2, "price_fixed": 55000},
                {"min_weight": 2, "max_weight": 5, "price_fixed": 85000},
            ],
            "usa_canada": [
                {"min_weight": 0, "max_weight": 2, "price_fixed": 65000},
                {"min_weight": 2, "max_weight": 5, "price_fixed": 95000},
            ],
            "inde": [
                {"min_weight": 0, "max_weight": 2, "price_fixed": 95000},
                {"min_weight": 2, "max_weight": 5, "price_fixed": 105000},
            ],
        },
        "gros_volumes_export": [
            {"min_weight": 50, "max_weight": 100, "price_per_kg": 9000},
            {"min_weight": 100, "max_weight": 250, "price_per_kg": 8500},
            {"min_weight": 250, "max_weight": 500, "price_per_kg": 8300},
        ],
        "gros_volumes_500plus": {
            "europe": 6500,
            "afrique": 5500,
            "chine": 8000,
            "usa_canada": 8000,
        }
    }

    @staticmethod
    def calculate_volumetric_weight(length_cm: float, width_cm: float, height_cm: float) -> float:
        """Calculate volumetric weight: L * l * h / 5000 (for air freight)."""
        return (length_cm * width_cm * height_cm) / 5000

    @staticmethod
    def calculate_cbm(length_cm: float, width_cm: float, height_cm: float) -> float:
        """Calculate cubic meters from dimensions in cm."""
        return (length_cm * width_cm * height_cm) / 1000000

    @staticmethod
    def get_billable_weight(real_weight: float, length_cm: float = None,
                            width_cm: float = None, height_cm: float = None) -> Tuple[float, str]:
        """
        Get the billable weight (max of real and volumetric).
        Returns (billable_weight, basis) where basis is 'real' or 'volumetric'.
        """
        if length_cm and width_cm and height_cm:
            vol_weight = PricingEngine.calculate_volumetric_weight(length_cm, width_cm, height_cm)
            if vol_weight > real_weight:
                return vol_weight, "volumetric"
        return real_weight, "real"

    @staticmethod
    def get_grid_from_db(mode: str, origin: str = None) -> Optional[list]:
        """Try to fetch current pricing grid from database."""
        query = """SELECT rules FROM pricing_grids
                   WHERE mode = %s AND (valid_until IS NULL OR valid_until > NOW())
                   ORDER BY valid_from DESC LIMIT 1"""
        params = (mode,)

        if origin:
            query = """SELECT rules FROM pricing_grids
                       WHERE mode = %s AND origin = %s AND (valid_until IS NULL OR valid_until > NOW())
                       ORDER BY valid_from DESC LIMIT 1"""
            params = (mode, origin)

        result = execute_query(query, params, fetch_one=True)
        if result and result.get("rules"):
            return result["rules"]
        return None

    def estimate_aerien(self, weight: float, origin: str = "chine",
                        length_cm: float = None, width_cm: float = None,
                        height_cm: float = None) -> Dict:
        """
        Estimate air freight cost.
        Returns dict with price, billable_weight, basis, rate_per_kg.
        """
        # Calculate billable weight
        billable_weight, basis = self.get_billable_weight(
            weight, length_cm, width_cm, height_cm
        )

        # Determine which grid to use
        if origin.lower() in ["chine", "china", "cn"]:
            grid_key = "aerien_chine"
        else:
            grid_key = "aerien_international"

        # Try DB grid first, fallback to defaults
        grid = self.get_grid_from_db(grid_key, origin) or self.DEFAULT_GRIDS.get(grid_key, [])

        # Find applicable rate
        rate_per_kg = 0
        for tier in grid:
            if tier["min_weight"] <= billable_weight < tier["max_weight"]:
                rate_per_kg = tier["price_per_kg"]
                break
            elif billable_weight >= tier.get("max_weight", 0):
                rate_per_kg = tier["price_per_kg"]

        total_price = int(billable_weight * rate_per_kg)

        return {
            "mode": "aerien",
            "origin": origin,
            "billable_weight": round(billable_weight, 2),
            "basis": basis,
            "rate_per_kg": rate_per_kg,
            "total_price": total_price,
            "currency": "FCFA",
            "volumetric_weight": round(self.calculate_volumetric_weight(length_cm, width_cm, height_cm), 2) if all([length_cm, width_cm, height_cm]) else None,
            "needs_pickup": billable_weight >= 25,
        }

    def estimate_maritime(self, weight: float, length_cm: float = None,
                          width_cm: float = None, height_cm: float = None) -> Dict:
        """Estimate maritime freight cost."""
        cbm = None
        if all([length_cm, width_cm, height_cm]):
            cbm = self.calculate_cbm(length_cm, width_cm, height_cm)

        grid = self.get_grid_from_db("maritime") or self.DEFAULT_GRIDS["maritime"]

        # Maritime pricing by weight range and CBM
        price_per_unit = 0
        unit = "CBM"
        for tier in grid:
            if tier["min_weight"] <= weight < tier["max_weight"]:
                if "price_per_cbm" in tier:
                    price_per_unit = tier["price_per_cbm"]
                    unit = "CBM"
                elif "price_per_tonne" in tier:
                    price_per_unit = tier["price_per_tonne"]
                    unit = "tonne"
                break

        total_price = None
        if cbm and unit == "CBM":
            total_price = int(cbm * price_per_unit)
        elif unit == "tonne":
            total_price = int((weight / 1000) * price_per_unit)

        return {
            "mode": "maritime",
            "weight": weight,
            "cbm": round(cbm, 4) if cbm else None,
            "price_per_unit": price_per_unit,
            "unit": unit,
            "total_price": total_price,
            "currency": "FCFA",
        }

    def estimate(self, mode: str, weight: float, origin: str = "chine",
                 length_cm: float = None, width_cm: float = None,
                 height_cm: float = None) -> Dict:
        """Main estimation method dispatching to the correct calculator."""
        if mode == "aerien":
            return self.estimate_aerien(weight, origin, length_cm, width_cm, height_cm)
        elif mode == "maritime":
            return self.estimate_maritime(weight, length_cm, width_cm, height_cm)
        else:
            return {"error": "Mode non supporté", "supported": ["aerien", "maritime"]}


pricing_engine = PricingEngine()
