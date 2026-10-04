"""
WrapStreet synthetic data generator (Step 3)
--------------------------------------------
Builds 104 weeks (Apr 2024 - Mar 2026) of store x product x week sales for a
fictional 8-outlet Mumbai QSR chain, using a log-log demand model with
PLANTED price elasticities. The planted truth is written to a separate file
so it never leaks into the modelling data.

Outputs (in ./output):
  stores.csv, products.csv, weekly_sales.csv   -> modelling data
  planted_truth.csv                            -> hidden answers (validation only)
"""
import os
import numpy as np
import pandas as pd

SEED = 42
rng = np.random.default_rng(SEED)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- assumptions
N_WEEKS = 104
START = pd.Timestamp("2024-04-01")          # Monday, start of FY24-25
BASELINE_WEEKS = 8                          # last 8 weeks = "current state"
COMMISSION = 0.25                           # aggregator commission on delivery orders
GST = 0.05                                  # excluded from revenue (pass-through)
NOISE_SD = 0.08                             # ~8% week-to-week random variation
ANNUAL_GROWTH = 0.03                        # organic growth
PROMO_BOOST = 0.05                          # visibility uplift in discount weeks
PRICE_REVISION = 0.06                       # FY24-25 prices ~6% below today
COMP_DRIFT = 0.05                           # competitor prices rise ~5%/yr
MONSOON_DELIVERY_SHIFT = 0.10               # +10pp delivery share in monsoon
COMP_SENS = {"High": 0.5, "Medium": 0.3}

# ---------------------------------------------------------------- stores
stores = pd.DataFrame([
    # id, name, area, type, income, competition, footfall, delivery, true_e, comp_ratio
    ("S01", "WrapStreet BKC",          "Bandra Kurla Complex", "Office",              "High",    "Medium", 1.20, 0.40, -0.7, 1.08),
    ("S02", "WrapStreet Lower Parel",  "Lower Parel",          "Office",              "High",    "High",   1.30, 0.45, -1.1, 1.00),
    ("S03", "WrapStreet Colaba",       "Colaba",               "Tourist/Premium",     "High",    "Medium", 0.90, 0.35, -0.8, 1.05),
    ("S04", "WrapStreet Powai",        "Powai",                "IT/Residential",      "Mid-High","Medium", 1.10, 0.55, -1.1, 0.98),
    ("S05", "WrapStreet Andheri West", "Andheri West",         "Young Professionals", "Mid",     "High",   1.25, 0.55, -1.5, 0.93),
    ("S06", "WrapStreet Vile Parle",   "Vile Parle",           "College",             "Low-Mid", "High",   1.15, 0.45, -2.1, 0.78),
    ("S07", "WrapStreet Ghatkopar",    "Ghatkopar",            "Residential",         "Mid",     "Medium", 0.95, 0.50, -1.3, 0.95),
    ("S08", "WrapStreet Thane",        "Thane",                "Suburban/Value",      "Mid",     "Medium", 0.85, 0.50, -1.7, 0.90),
], columns=["store_id", "store_name", "area", "store_type", "income_tier",
            "competition_intensity", "footfall_index", "delivery_share",
            "true_elasticity_base", "competitor_price_ratio"])

# ---------------------------------------------------------------- products
products = pd.DataFrame([
    # id, name, category, current price, unit cost, base weekly orders, modifier
    ("P01", "Paneer Tikka Wrap",   "Wrap",     199, 70, 320, 1.00),
    ("P02", "Chicken Tikka Wrap",  "Wrap",     229, 85, 350, 1.00),
    ("P03", "Rajma Rice Bowl",     "Bowl",     179, 55, 220, 0.90),
    ("P04", "Butter Chicken Bowl", "Bowl",     259, 95, 260, 0.90),
    ("P05", "Masala Fries",        "Side",      99, 28, 400, 1.20),
    ("P06", "Cold Coffee",         "Beverage", 129, 35, 300, 1.15),
], columns=["product_id", "product_name", "category", "current_price",
            "unit_cost", "base_weekly_orders", "elasticity_modifier"])


def menu_round(p):
    """Round to Indian menu-style endings (..9): 216 -> 219, 187.7 -> 189."""
    return int(np.floor((p + 1) / 10 + 0.5) * 10 - 1)


# ---------------------------------------------------------------- calendar
weeks = pd.DataFrame({"week_no": np.arange(1, N_WEEKS + 1)})
weeks["week_start"] = START + pd.to_timedelta((weeks.week_no - 1) * 7, unit="D")
weeks["fy"] = np.where(weeks.week_start < pd.Timestamp("2025-04-01"), "FY24-25", "FY25-26")

# Approximate festival dates (Mumbai-relevant)
FESTIVALS = {
    "Ganesh Chaturthi": [("2024-09-07", "2024-09-17"), ("2025-08-27", "2025-09-06")],
    "Navratri":         [("2024-10-03", "2024-10-12"), ("2025-09-22", "2025-10-02")],
    "Diwali":           [("2024-10-29", "2024-11-03"), ("2025-10-18", "2025-10-23")],
    "Year End":         [("2024-12-22", "2025-01-01"), ("2025-12-22", "2026-01-01")],
}


def week_events(ws):
    we = ws + pd.Timedelta(days=6)
    hits = set()
    for name, ranges in FESTIVALS.items():
        for a, b in ranges:
            if ws <= pd.Timestamp(b) and we >= pd.Timestamp(a):
                hits.add(name)
    return hits


def season_factor(ws, store_type, category, store_id, events):
    m = (ws + pd.Timedelta(days=3)).month   # month of mid-week
    f = 1.0
    if m in (6, 7, 8, 9):
        f *= 0.96                            # monsoon: net -4%
        if category == "Side":
            f *= 1.10                        # fries do well in rain
    if m in (4, 5) and category == "Beverage":
        f *= 1.20                            # summer cold coffee
    # festivals
    if store_type in ("Residential", "Suburban/Value", "IT/Residential"):
        if events & {"Ganesh Chaturthi", "Navratri", "Diwali"}:
            f *= 1.12
    if store_type == "Office":
        if "Diwali" in events:
            f *= 0.80
        if "Year End" in events:
            f *= 0.85
    if store_type in ("Tourist/Premium", "Young Professionals") and "Year End" in events:
        f *= 1.10
    # Vile Parle academic calendar
    if store_id == "S06":
        d = (ws + pd.Timedelta(days=3))
        if m in (5, 6):
            f *= 0.70                        # vacations
        elif m in (11, 4) and d.day >= 10:
            f *= 0.90                        # exam weeks
    return f


# ---------------------------------------------------------------- generate
rows, truth = [], []
for _, s in stores.iterrows():
    for _, p in products.iterrows():
        e_true = round(s.true_elasticity_base * p.elasticity_modifier, 3)
        c_true = COMP_SENS[s.competition_intensity]
        truth.append({"store_id": s.store_id, "product_id": p.product_id,
                      "true_own_price_elasticity": e_true,
                      "true_competitor_sensitivity": c_true})

        p_cur = p.current_price
        p_old = menu_round(p_cur / (1 + PRICE_REVISION))
        base_menu = np.where(weeks.week_no <= 52, p_old, p_cur).astype(float)

        # --- store-level price tests (2-3 x 4 weeks, outside the baseline)
        menu = base_menu.copy()
        test_flag = np.zeros(N_WEEKS, dtype=int)
        n_tests = rng.integers(2, 4)
        eligible = N_WEEKS - BASELINE_WEEKS - 4
        placed = 0
        while placed < n_tests:
            st = rng.integers(0, eligible)
            if test_flag[max(0, st - 2): st + 6].any():
                continue
            pct = rng.choice([-0.10, -0.05, 0.05, 0.10])
            for w in range(st, st + 4):
                menu[w] = menu_round(base_menu[w] * (1 + pct))
                test_flag[w] = 1
            placed += 1

        # --- discount promotions (not during tests or baseline)
        promo_rate = 0.15 if s.competition_intensity == "High" else 0.12
        disc = np.zeros(N_WEEKS)
        for w in range(N_WEEKS - BASELINE_WEEKS):
            if test_flag[w] == 0 and rng.random() < promo_rate:
                disc[w] = rng.choice([0.10, 0.15, 0.20])
        promo_flag = (disc > 0).astype(int)
        eff = np.round(menu * (1 - disc), 2)

        # --- competitor price (drifts up ~5%/yr, occasional promos)
        comp_ref = round(p_cur * s.competitor_price_ratio)
        t = weeks.week_no.values - N_WEEKS          # 0 at final week
        comp = comp_ref * (1 + COMP_DRIFT) ** (t / 52)
        comp_promo = rng.random(N_WEEKS) < 0.06
        comp = np.round(np.where(comp_promo, comp * 0.85, comp))

        # --- demand
        base_q = p.base_weekly_orders * s.footfall_index
        for i, wk in weeks.iterrows():
            ev = week_events(wk.week_start)
            sf = season_factor(wk.week_start, s.store_type, p.category, s.store_id, ev)
            trend = (1 + ANNUAL_GROWTH) ** (t[i] / 52)
            ln_q = (np.log(base_q)
                    + e_true * np.log(eff[i] / p_cur)
                    + c_true * np.log(comp[i] / comp_ref)
                    + np.log(sf)
                    + promo_flag[i] * np.log(1 + PROMO_BOOST)
                    + np.log(trend)
                    + rng.normal(0, NOISE_SD))
            orders = int(round(np.exp(ln_q)))
            m = (wk.week_start + pd.Timedelta(days=3)).month
            dshare = min(0.85, s.delivery_share + (MONSOON_DELIVERY_SHIFT if m in (6, 7, 8, 9) else 0))
            d_orders = int(rng.binomial(orders, dshare))
            rows.append({
                "week_start": wk.week_start.date(), "fy": wk.fy, "week_no": wk.week_no,
                "store_id": s.store_id, "product_id": p.product_id,
                "menu_price": float(menu[i]), "discount_pct": float(disc[i]),
                "effective_price": float(eff[i]), "competitor_price": float(comp[i]),
                "price_test_flag": int(test_flag[i]), "promo_flag": int(promo_flag[i]),
                "festival_flag": int(len(ev) > 0),
                "festival_name": ", ".join(sorted(ev)) if ev else "",
                "season_index": round(sf, 3),
                "orders": orders, "delivery_orders": d_orders,
                "dine_in_orders": orders - d_orders,
            })

sales = pd.DataFrame(rows)
cost = sales.product_id.map(products.set_index("product_id").unit_cost)
sales["net_revenue"] = (sales.orders * sales.effective_price).round(2)
sales["variable_cost"] = (sales.orders * cost
                          + sales.delivery_orders * sales.effective_price * COMMISSION).round(2)
sales["contribution"] = (sales.net_revenue - sales.variable_cost).round(2)

# ---------------------------------------------------------------- export
stores.drop(columns=["true_elasticity_base"]).to_csv(f"{OUT}/stores.csv", index=False)
products.drop(columns=["elasticity_modifier"]).to_csv(f"{OUT}/products.csv", index=False)
sales.to_csv(f"{OUT}/weekly_sales.csv", index=False)
pd.DataFrame(truth).to_csv(f"{OUT}/planted_truth.csv", index=False)
print(f"weekly_sales: {len(sales):,} rows | stores: {len(stores)} | products: {len(products)}")
