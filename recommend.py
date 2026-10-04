"""
WrapStreet Step 6 - Recommendation logic
----------------------------------------
Turns the Step 5 simulations into a pricing decision for one store-product:

1. Candidate prices = Indian menu endings (..9) within the max move (default +/-15%)
2. Drop candidates that break a guardrail:
     - more than X% above the local competitor (default 15%)
     - orders fall by more than the volume floor (default 10%)
     - contribution per order turns negative
3. Pick the candidate with the highest projected weekly contribution
4. If the gain over today is below the hold threshold (default 2%) -> HOLD
5. Rollout advice: if the pessimistic case (elasticity at the risky end of its
   95% range) still beats today -> ROLL OUT; otherwise -> PILOT for 4 weeks
6. Discount check: does a 10% discount pay for itself here?

Imported by the Streamlit app; run directly for the chain-wide view.
"""
import numpy as np
import pandas as pd
from pricing_engine import (load_data, baseline, project, unit_margin,
                            discount_scenarios, chain_promo_uplift, OUT)

DEFAULTS = {
    "max_move": 0.15,          # largest single price change
    "max_vs_competitor": 0.15, # stay within 15% above competitor
    "volume_floor": -0.10,     # accept at most a 10% drop in orders
    "hold_threshold": 0.02,    # minimum contribution gain worth acting on
}


def menu_prices(current, max_move):
    """All ..9-ending prices within +/- max_move of today's price."""
    lo, hi = current * (1 - max_move), current * (1 + max_move)
    start = int(np.ceil((lo + 1) / 10) * 10 - 1)
    return [p for p in range(start, int(hi) + 1, 10) if lo <= p <= hi] or [int(current)]


def evaluate_candidates(base, rules):
    _, _, cm0 = project(base, base["price"])
    rows = []
    for p in sorted(set(menu_prices(base["price"], rules["max_move"]) + [int(base["price"])])):
        q, rev, cm = project(base, p)
        cms = [project(base, p, elasticity=e)[2] for e in (base["e_low"], base["e_high"])]
        reasons = []
        if p > base["competitor_price"] * (1 + rules["max_vs_competitor"]):
            reasons.append("too far above competitor")
        if q / base["orders"] - 1 < rules["volume_floor"]:
            reasons.append("breaks volume floor")
        if unit_margin(p, base) <= 0:
            reasons.append("negative unit margin")
        rows.append({"price": p, "orders": q, "net_revenue": rev, "contribution": cm,
                     "contribution_pessimistic": min(cms), "contribution_optimistic": max(cms),
                     "orders_change_pct": q / base["orders"] - 1,
                     "contribution_change_pct": cm / cm0 - 1,
                     "allowed": not reasons, "blocked_by": ", ".join(reasons)})
    return pd.DataFrame(rows), cm0


def recommend(base, rules=None, promo_uplift=0.07, product_name="", store_name=""):
    rules = {**DEFAULTS, **(rules or {})}
    cand, cm0 = evaluate_candidates(base, rules)
    _, rev0, _ = project(base, base["price"])
    ok = cand[cand.allowed]
    comp_relaxed = False
    if ok.empty:
        # competitor gap can't be closed within the max move: keep the other rules
        ok = cand[cand.blocked_by.isin(["", "too far above competitor"])]
        comp_relaxed = not ok.empty
    best = ok.loc[ok.contribution.idxmax()] if len(ok) else cand[cand.price == base["price"]].iloc[0]
    unconstrained = cand.loc[cand.contribution.idxmax()]

    gain = best.contribution / cm0 - 1
    current_row = cand[cand.price == base["price"]].iloc[0]
    current_ok = bool(current_row.allowed)
    # hold threshold applies only when today's price itself respects the guardrails
    if best.price == base["price"] or (current_ok and gain < rules["hold_threshold"]):
        action, rec = "HOLD", cand[cand.price == base["price"]].iloc[0]
    else:
        action, rec = ("RAISE" if best.price > base["price"] else "LOWER"), best

    pess_gain = rec.contribution_pessimistic / cm0 - 1
    rollout = ("No change" if action == "HOLD"
               else "Roll out" if pess_gain >= 0 and base["confidence"] != "Low"
               else "Pilot for 4 weeks first")

    disc = discount_scenarios(base, promo_uplift, discounts=[0.10])
    disc_ok = bool(disc.contribution_change_pct.iloc[0] >= 0)

    # ---- plain-English rationale
    e = base["elasticity"]
    sens = ("low" if e > -1 else "moderate" if e > -1.5 else "high")
    if action == "HOLD":
        why = (f"Customers here show {sens} price sensitivity (elasticity {e:.2f}). "
               f"The best allowed price would change weekly contribution by only "
               f"{gain:+.1%}, below the {rules['hold_threshold']:.0%} threshold - not worth "
               f"the menu change and the risk.")
    else:
        why = (f"Customers here show {sens} price sensitivity (elasticity {e:.2f}). "
               f"Moving to ₹{rec.price:.0f} changes orders by {rec.orders_change_pct:+.1%} "
               f"but weekly contribution by {rec.contribution_change_pct:+.1%} "
               f"({'+' if rec.contribution >= cm0 else '−'}₹{abs(rec.contribution - cm0):,.0f}/week).")
    if not current_ok:
        gap = base["price"] / base["competitor_price"] - 1
        why += (f" Today's ₹{base['price']:.0f} is {gap:.0%} above the local competitor "
                f"(₹{base['competitor_price']:.0f}), beyond the {rules['max_vs_competitor']:.0%} guardrail.")
    if comp_relaxed:
        why += (" No price within the allowed move closes that gap, so the competitor rule "
                "was relaxed for this item - review positioning separately.")
    if unconstrained.price != best.price and not unconstrained.allowed:
        why += (f" The model's unconstrained best (₹{unconstrained.price:.0f}) was blocked: "
                f"{unconstrained.blocked_by}.")
    if rollout == "Pilot for 4 weeks first":
        why += (" In the pessimistic case the change could lose money, so test it "
                "in-store before a full rollout.")
    why += (" A 10% discount would " + ("pay for itself here." if disc_ok
            else "lift orders but reduce contribution - avoid it."))

    return {
        "store_id": base["store_id"], "store_name": store_name,
        "product_id": base["product_id"], "product_name": product_name,
        "current_price": base["price"], "recommended_price": float(rec.price),
        "price_change_pct": rec.price / base["price"] - 1, "action": action,
        "rollout": rollout, "confidence": base["confidence"], "elasticity": e,
        "orders_now": base["orders"], "orders_new": rec.orders,
        "orders_change_pct": rec.orders_change_pct,
        "revenue_now": rev0, "revenue_new": rec.net_revenue,
        "contribution_now": cm0, "contribution_new": rec.contribution,
        "contribution_change_pct": rec.contribution / cm0 - 1,
        "contribution_change_weekly": rec.contribution - cm0,
        "contribution_change_pessimistic_pct": pess_gain,
        "contribution_change_optimistic_pct": rec.contribution_optimistic / cm0 - 1,
        "discount_10_pays": disc_ok, "rationale": why,
    }, cand


# ------------------------------------------------------------------ chain view
def best_uniform_price(bases, product_id, current, rules):
    """Best single chain-wide price for a product: same max move and volume floor,
    applied to chain-total orders. (A per-store competitor rule cannot be met by
    one price everywhere, so it is not applied here - this flatters uniform pricing.)"""
    q0 = sum(b["orders"] for b in bases)
    best, best_cm = current, sum(project(b, current)[2] for b in bases)
    for p in menu_prices(current, rules["max_move"]):
        res = [project(b, p) for b in bases]
        if sum(r[0] for r in res) / q0 - 1 < rules["volume_floor"]:
            continue
        total = sum(r[2] for r in res)
        if total > best_cm:
            best, best_cm = p, total
    return best


if __name__ == "__main__":
    sales, stores, products, est = load_data()
    uplift = chain_promo_uplift(est)
    sname = stores.set_index("store_id").store_name.str.replace("WrapStreet ", "")
    pname = products.set_index("product_id").product_name

    recs, bases = [], {}
    for sid in stores.store_id:
        for pid in products.product_id:
            b = baseline(sales, products, est, sid, pid)
            bases[(sid, pid)] = b
            r, _ = recommend(b, promo_uplift=uplift, product_name=pname[pid], store_name=sname[sid])
            recs.append(r)
    rec = pd.DataFrame(recs)
    rec.to_csv(f"{OUT}/recommendations.csv", index=False)

    # uniform-optimised comparison
    uni = []
    for pid in products.product_id:
        bs = [bases[(s, pid)] for s in stores.store_id]
        p = best_uniform_price(bs, pid, bs[0]["price"], DEFAULTS)
        for b in bs:
            q, rev, cm = project(b, p)
            uni.append({"product_id": pid, "store_id": b["store_id"], "uniform_price": p,
                        "contribution": cm, "orders": q})
    uni = pd.DataFrame(uni)

    wk_now = rec.contribution_now.sum()
    wk_loc = rec.contribution_new.sum()
    wk_uni = uni.contribution.sum()
    summary = pd.DataFrame([
        ("Current uniform prices", wk_now, rec.orders_now.sum()),
        ("Best single chain-wide price per product", wk_uni, uni.orders.sum()),
        ("Store-level (localised) prices", wk_loc, rec.orders_new.sum()),
    ], columns=["scenario", "weekly_contribution", "weekly_orders"])
    summary["vs_current_pct"] = summary.weekly_contribution / wk_now - 1
    summary["annual_uplift_inr_lakh"] = (summary.weekly_contribution - wk_now) * 52 / 1e5
    summary.to_csv(f"{OUT}/chain_summary.csv", index=False)

    print(rec.action.value_counts().to_string())
    print(rec.rollout.value_counts().to_string())
    print(summary.round(3).to_string(index=False))
    print(uni.drop_duplicates("product_id")[["product_id", "uniform_price"]].to_string(index=False))
