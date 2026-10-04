"""
WrapStreet Step 4 - Price elasticity estimation
-----------------------------------------------
For every store x product, fit a log-log demand model on 104 weeks:

  ln(orders) = a + e * ln(effective price) + c * ln(competitor price)
               + promo + festival dummies + month dummies + trend + error

e = own-price elasticity (% change in orders for a 1% price change)
c = competitor price sensitivity

Notes
- season_index in the data is a generation artefact a real chain would not
  have, so it is deliberately NOT used. Seasonality is learned from month and
  festival dummies, as it would be with real POS data.
- Weak estimates are stabilised by shrinking towards the store's pooled
  estimate (precision-weighted), so no recommendation rests on one noisy fit.
- planted_truth.csv is read ONLY at the end, for validation.
"""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = "output"
sales = pd.read_csv(f"{OUT}/weekly_sales.csv", keep_default_na=False, parse_dates=["week_start"])
stores = pd.read_csv(f"{OUT}/stores.csv")
products = pd.read_csv(f"{OUT}/products.csv")

df = sales.copy()
df["ln_q"] = np.log(df.orders)
df["ln_p"] = np.log(df.effective_price)
df["ln_comp"] = np.log(df.competitor_price)
df["month"] = (df.week_start + pd.Timedelta(days=3)).dt.month
df["t"] = df.week_no / 52
for name, col in [("Diwali", "fest_diwali"), ("Year End", "fest_yearend"),
                  ("Navratri", "fest_navratri"), ("Ganesh Chaturthi", "fest_ganesh")]:
    df[col] = df.festival_name.str.contains(name).astype(int)

FORMULA = ("ln_q ~ ln_p + ln_comp + promo_flag + fest_diwali + fest_yearend"
           " + fest_navratri + fest_ganesh + C(month) + t")

# ---------------------------------------------------------------- per store-product
rows = []
for (sid, pid), g in df.groupby(["store_id", "product_id"]):
    m = smf.ols(FORMULA, data=g).fit()
    rows.append({"store_id": sid, "product_id": pid, "n_weeks": int(m.nobs),
                 "e_raw": m.params["ln_p"], "e_raw_se": m.bse["ln_p"],
                 "comp_sens_est": m.params["ln_comp"],
                 "promo_uplift_est": np.exp(m.params["promo_flag"]) - 1,
                 "r2": m.rsquared,
                 "price_points": g.effective_price.nunique()})
est = pd.DataFrame(rows)

# ---------------------------------------------------------------- store-pooled anchor
pooled = {}
for sid, g in df.groupby("store_id"):
    m = smf.ols(FORMULA.replace("ln_q ~", "ln_q ~ C(product_id) + C(product_id):t +"),
                data=g).fit()
    pooled[sid] = (m.params["ln_p"], m.bse["ln_p"])
est["e_pooled"] = est.store_id.map(lambda s: pooled[s][0])
est["e_pooled_se"] = est.store_id.map(lambda s: pooled[s][1])

# precision-weighted shrinkage: noisy fits lean on the store anchor
# prior spread across products within a store assumed ~0.25
TAU = 0.25
w = TAU**2 / (TAU**2 + est.e_raw_se**2)
est["shrink_weight"] = w
est["elasticity"] = w * est.e_raw + (1 - w) * est.e_pooled
# posterior uncertainty = item-level part + uncertainty in the store anchor
est["elasticity_se"] = np.sqrt(w * est.e_raw_se**2 + (1 - w)**2 * est.e_pooled_se**2)
est["ci_low"] = est.elasticity - 1.96 * est.elasticity_se
est["ci_high"] = est.elasticity + 1.96 * est.elasticity_se
# confidence = how much the item's OWN sales history supports the estimate
# (vs. borrowing from the store's other items)
est["confidence"] = pd.cut(est.e_raw_se, [0, 0.30, 0.45, np.inf],
                           labels=["High", "Medium", "Low"]).astype(str)

est = (est.merge(stores[["store_id", "store_name"]], on="store_id")
          .merge(products[["product_id", "product_name"]], on="product_id"))

# ---------------------------------------------------------------- validation (truth read only here)
truth = pd.read_csv(f"{OUT}/planted_truth.csv")
val = est.merge(truth, on=["store_id", "product_id"])
val["abs_error"] = (val.elasticity - val.true_own_price_elasticity).abs()
val["within_0_2"] = val.abs_error <= 0.2
val["truth_in_ci"] = val.true_own_price_elasticity.between(val.ci_low, val.ci_high)

# ---------------------------------------------------------------- outputs
cols = ["store_id", "store_name", "product_id", "product_name", "n_weeks", "price_points",
        "elasticity", "elasticity_se", "ci_low", "ci_high", "confidence",
        "comp_sens_est", "promo_uplift_est", "r2", "e_raw", "e_raw_se", "e_pooled", "e_pooled_se", "shrink_weight"]
est[cols].round(3).to_csv(f"{OUT}/elasticity_estimates.csv", index=False)
val[cols + ["true_own_price_elasticity", "abs_error", "within_0_2", "truth_in_ci"]] \
    .round(3).to_csv(f"{OUT}/elasticity_validation.csv", index=False)

n = len(val)
print(f"Store-products estimated: {n}")
print(f"Within +/-0.2 of truth : {val.within_0_2.sum()} of {n}")
print(f"Truth inside 95% CI    : {val.truth_in_ci.sum()} of {n}")
print(f"Mean absolute error    : {val.abs_error.mean():.3f}")
print(f"Median R^2             : {val.r2.median():.2f}")
raw_ok = ((val.e_raw - val.true_own_price_elasticity).abs() <= 0.2).sum()
print(f"Raw item-only fits within +/-0.2: {raw_ok} of {n} "
      f"(MAE {(val.e_raw - val.true_own_price_elasticity).abs().mean():.3f})")
print(val.confidence.value_counts().to_string())
print(val.groupby("confidence").within_0_2.agg(["sum", "count"]).to_string())

# ---------------------------------------------------------------- validation chart
fig, ax = plt.subplots(figsize=(7, 6), dpi=160)
lo, hi = -3.0, -0.3
ax.fill_between([lo, hi], [lo - 0.2, hi - 0.2], [lo + 0.2, hi + 0.2],
                color="#1F3A5F", alpha=0.08, label="±0.2 accuracy band")
ax.plot([lo, hi], [lo, hi], color="#1F3A5F", lw=1, ls="--", label="Perfect recovery")
ax.errorbar(val.true_own_price_elasticity, val.elasticity,
            yerr=1.96 * val.elasticity_se, fmt="none", ecolor="#9AA5B1", lw=0.8, alpha=0.7)
ok = val.within_0_2
ax.scatter(val.true_own_price_elasticity[ok], val.elasticity[ok], s=28, color="#2E7D32",
           zorder=3, label=f"Within ±0.2 ({ok.sum()} of {n})")
ax.scatter(val.true_own_price_elasticity[~ok], val.elasticity[~ok], s=28, color="#C62828",
           zorder=3, label=f"Outside ±0.2 ({(~ok).sum()} of {n})")
ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
ax.set_xlabel("Planted (true) elasticity", fontsize=10)
ax.set_ylabel("Estimated elasticity", fontsize=10)
ax.set_title("Does the model recover the true price sensitivity?\n48 store-product combinations",
             fontsize=11, loc="left")
ax.legend(fontsize=8, loc="upper left", frameon=False)
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
plt.savefig(f"{OUT}/elasticity_validation.png")
print("saved chart")
