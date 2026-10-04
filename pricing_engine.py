"""
WrapStreet Step 5 - Pricing simulation engine
---------------------------------------------
Answers: "If we change the price of product P at store S, what happens to
weekly orders, revenue and contribution?" - and the same for a discount.

Demand response (constant-elasticity, from Step 4):
    orders_new = orders_base * (price_new / price_base) ** elasticity

Contribution per week (Step 1 definition, ex-GST):
    net revenue   = orders * effective price
    variable cost = orders * unit cost + delivery orders * effective price * commission
    contribution  = net revenue - variable cost

Every projection carries a low / high band from the elasticity's 95% CI.
Imported by the Streamlit app in Step 7; run directly to export scenario tables.
"""
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data")

COMMISSION = 0.25          # aggregator commission on delivery orders (Step 2)
BASELINE_WEEKS = 8         # last 8 weeks = current state
GRID = np.round(np.arange(-0.20, 0.2001, 0.01), 2)   # -20% .. +20%
DISCOUNTS = [0.05, 0.10, 0.15, 0.20]


# ------------------------------------------------------------------ data
def load_data(out_dir=OUT):
    sales = pd.read_csv(f"{out_dir}/weekly_sales.csv", keep_default_na=False)
    stores = pd.read_csv(f"{out_dir}/stores.csv")
    products = pd.read_csv(f"{out_dir}/products.csv")
    est = pd.read_csv(f"{out_dir}/elasticity_estimates.csv")
    return sales, stores, products, est


def chain_promo_uplift(est):
    """Visibility uplift of a discount beyond its price effect (median across items).
    Item-level estimates are too noisy to use one by one."""
    return float(np.clip(est.promo_uplift_est.median(), 0, 0.15))


def baseline(sales, products, est, store_id, product_id, weeks=BASELINE_WEEKS):
    """Current state: average of the last `weeks` weeks (no tests or discounts)."""
    g = sales[(sales.store_id == store_id) & (sales.product_id == product_id)]
    b = g[g.week_no > g.week_no.max() - weeks]
    p = products.set_index("product_id").loc[product_id]
    e = est.set_index(["store_id", "product_id"]).loc[(store_id, product_id)]
    return {
        "store_id": store_id, "product_id": product_id,
        "price": float(b.menu_price.iloc[-1]),
        "orders": float(b.orders.mean()),
        "delivery_share": float(b.delivery_orders.sum() / b.orders.sum()),
        "unit_cost": float(p.unit_cost),
        "competitor_price": float(b.competitor_price.mean()),
        "elasticity": float(e.elasticity),
        "e_low": float(e.ci_low),     # more price-sensitive end
        "e_high": float(e.ci_high),   # less price-sensitive end
        "confidence": str(e.confidence),
    }


# ------------------------------------------------------------------ economics
def economics(orders, price, base):
    """Weekly P&L lines for a given order volume and effective price."""
    revenue = orders * price
    var_cost = orders * base["unit_cost"] + orders * base["delivery_share"] * price * COMMISSION
    return revenue, var_cost, revenue - var_cost


def unit_margin(price, base):
    """Contribution per order at a given effective price."""
    return price * (1 - base["delivery_share"] * COMMISSION) - base["unit_cost"]


def project(base, new_price, extra_uplift=0.0, elasticity=None):
    """Orders, revenue and contribution at a new effective price."""
    e = base["elasticity"] if elasticity is None else elasticity
    orders = base["orders"] * (new_price / base["price"]) ** e * (1 + extra_uplift)
    rev, vc, cm = economics(orders, new_price, base)
    return orders, rev, cm


def breakeven_volume_change(base, new_price):
    """% change in orders needed to keep contribution flat at the new price."""
    m0, m1 = unit_margin(base["price"], base), unit_margin(new_price, base)
    return m0 / m1 - 1 if m1 > 0 else np.inf


# ------------------------------------------------------------------ scenarios
def price_grid(base, grid=GRID):
    """Simulate a menu-price change across the grid, with uncertainty band."""
    _, rev0, cm0 = project(base, base["price"])
    rows = []
    for pct in grid:
        price = base["price"] * (1 + pct)
        q, rev, cm = project(base, price)
        _, _, cm_lo = project(base, price, elasticity=base["e_low"])
        _, _, cm_hi = project(base, price, elasticity=base["e_high"])
        rows.append({
            "store_id": base["store_id"], "product_id": base["product_id"],
            "price_change_pct": pct, "price": round(price, 2),
            "orders": q, "orders_change_pct": q / base["orders"] - 1,
            "net_revenue": rev, "revenue_change_pct": rev / rev0 - 1,
            "contribution": cm, "contribution_change_pct": cm / cm0 - 1,
            # pessimistic / optimistic contribution from the elasticity CI
            "contribution_low": min(cm_lo, cm_hi), "contribution_high": max(cm_lo, cm_hi),
            "breakeven_orders_change_pct": breakeven_volume_change(base, price),
            "vs_competitor_pct": price / base["competitor_price"] - 1,
        })
    return pd.DataFrame(rows)


def discount_scenarios(base, promo_uplift, discounts=DISCOUNTS):
    """A temporary discount = lower effective price + visibility uplift."""
    _, rev0, cm0 = project(base, base["price"])
    rows = []
    for d in discounts:
        price = base["price"] * (1 - d)
        q, rev, cm = project(base, price, extra_uplift=promo_uplift)
        rows.append({
            "store_id": base["store_id"], "product_id": base["product_id"],
            "discount_pct": d, "effective_price": round(price, 2),
            "orders": q, "orders_change_pct": q / base["orders"] - 1,
            "net_revenue": rev, "revenue_change_pct": rev / rev0 - 1,
            "contribution": cm, "contribution_change_pct": cm / cm0 - 1,
            "breakeven_orders_change_pct": breakeven_volume_change(base, price),
            "verdict": "Pays for itself" if cm >= cm0 else "Destroys contribution",
        })
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ batch run
if __name__ == "__main__":
    sales, stores, products, est = load_data()
    uplift = chain_promo_uplift(est)
    print(f"Chain promo visibility uplift used: {uplift:.1%}")

    bases, grids, discs = [], [], []
    for sid in stores.store_id:
        for pid in products.product_id:
            b = baseline(sales, products, est, sid, pid)
            bases.append(b)
            grids.append(price_grid(b))
            discs.append(discount_scenarios(b, uplift))
    base_df = pd.DataFrame(bases)
    grid_df = pd.concat(grids)
    disc_df = pd.concat(discs)

    base_df.round(3).to_csv(f"{OUT}/baseline_state.csv", index=False)
    grid_df.round(4).to_csv(f"{OUT}/simulation_price_grid.csv", index=False)
    disc_df.round(4).to_csv(f"{OUT}/simulation_discounts.csv", index=False)
    print(f"baseline rows: {len(base_df)} | price-grid rows: {len(grid_df):,} | discount rows: {len(disc_df)}")
