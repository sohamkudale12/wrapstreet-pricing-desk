"""
WrapStreet Pricing Desk - Streamlit prototype (Step 7)
Run:  streamlit run app.py
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import pricing_engine as pe
from recommend import recommend, best_uniform_price, menu_prices, DEFAULTS

st.set_page_config(page_title="WrapStreet Pricing Desk", page_icon="🌯", layout="wide")

# ------------------------------------------------------------------ palette & type
INK, SLATE, MIST = "#1D2B36", "#6B7A8F", "#E6E9ED"
TAXI, GAIN, LOSS = "#F2B705", "#2E7D32", "#C0392B"
FONT = "Source Sans 3, Source Sans Pro, sans-serif"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;700;800&display=swap');
h1, h2, h3, .tag-price, .scn-num {{ font-family: 'Archivo', {FONT}; letter-spacing: -0.01em; }}
h1 {{ font-weight: 800; }}
.block-container {{ padding-top: 2rem; max-width: 1250px; }}
.tag {{ background: {TAXI}; color: {INK}; border-radius: 6px 6px 6px 28px;
        padding: 1.1rem 1.4rem 1.2rem; position: relative; }}
.tag::before {{ content: ""; position: absolute; top: 16px; right: 18px; width: 12px; height: 12px;
        border-radius: 50%; background: #FBFBF9; box-shadow: inset 0 0 0 2px {INK}; }}
.tag-action {{ font-weight: 700; font-size: 1.05rem; }}
.tag-price {{ font-size: 3.1rem; font-weight: 800; line-height: 1.05; margin: .25rem 0 .4rem; }}
.tag-price .old {{ font-size: 1.6rem; font-weight: 500; text-decoration: line-through;
        opacity: .55; margin-right: .5rem; }}
.tag-meta {{ font-size: .95rem; }}
.tag.hold {{ background: {MIST}; }}
.cmp {{ width: 100%; border-collapse: collapse; font-size: .98rem; }}
.cmp th {{ text-align: right; font-weight: 600; color: {SLATE}; padding: .35rem .6rem;
        border-bottom: 1px solid {MIST}; }}
.cmp th:first-child, .cmp td:first-child {{ text-align: left; }}
.cmp td {{ text-align: right; padding: .45rem .6rem; border-bottom: 1px solid {MIST}; }}
.up {{ color: {GAIN}; font-weight: 600; }} .down {{ color: {LOSS}; font-weight: 600; }}
.why {{ border-left: 4px solid {TAXI}; padding: .6rem 1rem; background: #F5F6F7;
        border-radius: 0 6px 6px 0; line-height: 1.5; max-width: 80ch; }}
.profile {{ color: {SLATE}; font-size: 1rem; margin-top: -.6rem; }}
.check {{ line-height: 1.9; }}
.scn {{ border-top: 3px solid {MIST}; padding-top: .5rem; }}
.scn.best {{ border-top-color: {TAXI}; }}
.scn-num {{ font-size: 2rem; font-weight: 800; }}
.scn-sub {{ color: {SLATE}; }}
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------ helpers
def inr(x, sign=False):
    """Indian digit grouping: 1550970 -> 15,50,970."""
    neg = x < 0
    s = str(int(round(abs(x))))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    pre = "−" if neg else ("+" if sign and x > 0 else "")
    return f"{pre}₹{s}"


def lakh(x, sign=True):
    pre = "+" if sign and x > 0 else ("−" if x < 0 else "")
    return f"{pre}₹{abs(x) / 1e5:.1f} lakh"


def pct(x, sign=True):
    return f"{x:+.1%}" if sign else f"{x:.1%}"


def delta_cls(x):
    return "up" if x > 0.0005 else "down" if x < -0.0005 else ""


def base_layout(fig, height=360):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10),
                      font=dict(family=FONT, color=INK, size=13),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", y=1.12, x=0),
                      hoverlabel=dict(font_family=FONT))
    fig.update_xaxes(gridcolor=MIST, zeroline=False)
    fig.update_yaxes(gridcolor=MIST, zeroline=False)
    return fig


@st.cache_data
def load():
    sales, stores, products, est = pe.load_data()
    stores["short"] = stores.store_name.str.replace("WrapStreet ", "", regex=False)
    return sales, stores, products, est


sales, stores, products, est = load()
S = stores.set_index("store_id")
P = products.set_index("product_id")

# ------------------------------------------------------------------ sidebar
if "store" not in st.session_state:
    st.session_state.store = "S01"
    st.session_state.product = "P02"


def jump(sid, pid="P02"):
    st.session_state.store, st.session_state.product = sid, pid
    st.session_state.page = "Price desk"


with st.sidebar:
    st.markdown("### WrapStreet Pricing Desk")
    page = st.radio("View", ["Price desk", "Chain view", "How it works"], key="page",
                    label_visibility="collapsed")
    st.divider()
    st.selectbox("Store", stores.store_id, key="store",
                 format_func=lambda s: f"{S.loc[s, 'short']} ({S.loc[s, 'store_type']})")
    st.selectbox("Product", products.product_id, key="product",
                 format_func=lambda p: f"{P.loc[p, 'product_name']} (₹{P.loc[p, 'current_price']})")

    st.caption("Demo shortcuts: Chicken Tikka Wrap at")
    st.button("BKC: raise", on_click=jump, args=("S01",), width="stretch")
    st.button("Vile Parle: lower", on_click=jump, args=("S06",), width="stretch")
    st.button("Thane: hold", on_click=jump, args=("S08",), width="stretch")

    with st.expander("Business rules"):
        max_move = st.slider("Largest price change allowed", 5, 25, 15, 1, format="±%d%%") / 100
        comp_gap = st.slider("Max price above local competitor", 5, 30, 15, 1, format="%d%%") / 100
        vol_floor = st.slider("Largest drop in orders accepted", 0, 25, 10, 1, format="%d%%") / 100
        hold_th = st.slider("Minimum gain worth a price change", 0.0, 5.0, 2.0, 0.5, format="%.1f%%") / 100
        commission = st.slider("Aggregator commission (delivery)", 15, 35, 25, 1, format="%d%%") / 100
        uplift = st.slider("Extra orders from discount visibility", 0, 15, 7, 1, format="%d%%",
                           help="Orders gained from a discount beyond the price effect. "
                                "Estimated at about 7% from past promotions; assumed not to fade.") / 100
    st.caption("All data is synthetic. Store areas are real; the chain and its numbers are not.")

pe.COMMISSION = commission
RULES = {"max_move": max_move, "max_vs_competitor": comp_gap,
         "volume_floor": -vol_floor, "hold_threshold": hold_th}


@st.cache_data
def chain_run(rules_t, commission, uplift):
    pe.COMMISSION = commission
    rules = dict(rules_t)
    recs, bases = [], {}
    for sid in stores.store_id:
        for pid in products.product_id:
            b = pe.baseline(sales, products, est, sid, pid)
            bases[(sid, pid)] = b
            r, _ = recommend(b, rules, uplift, P.loc[pid, "product_name"], S.loc[sid, "short"])
            recs.append(r)
    rec = pd.DataFrame(recs)
    uni_cm, uni_q, uni_prices = 0.0, 0.0, {}
    for pid in products.product_id:
        bs = [bases[(s, pid)] for s in stores.store_id]
        p = best_uniform_price(bs, pid, bs[0]["price"], rules)
        uni_prices[pid] = p
        for b in bs:
            q, _, cm = pe.project(b, p)
            uni_cm += cm
            uni_q += q
    return rec, uni_cm, uni_q, uni_prices


# ================================================================== PRICE DESK
def price_desk():
    sid, pid = st.session_state.store, st.session_state.product
    s, p = S.loc[sid], P.loc[pid]
    base = pe.baseline(sales, products, est, sid, pid)
    rec, cand = recommend(base, RULES, uplift, p.product_name, s.short)
    _, rev0, cm0 = pe.project(base, base["price"])

    st.title(f"{p.product_name} at {s.short}")
    st.markdown(f"<div class='profile'>{s.store_type} catchment, {s.income_tier.lower()} income, "
                f"{s.competition_intensity.lower()} competition. Nearby competitor sells a comparable "
                f"item at {inr(base['competitor_price'])}. Today's price is {inr(base['price'])} at every outlet."
                f"</div>", unsafe_allow_html=True)
    st.write("")

    # ---- recommendation
    left, right = st.columns([1, 1.5], gap="large")
    labels = {"RAISE": "Raise the price", "LOWER": "Lower the price", "HOLD": "Keep today's price"}
    with left:
        if rec["action"] == "HOLD":
            price_html = inr(rec["current_price"])
            meta = "No change recommended"
        else:
            price_html = f"<span class='old'>{inr(rec['current_price'])}</span>{inr(rec['recommended_price'])}"
            meta = rec["rollout"]
        st.markdown(f"""
        <div class="tag {'hold' if rec['action'] == 'HOLD' else ''}">
          <div class="tag-action">{labels[rec['action']]}</div>
          <div class="tag-price">{price_html}</div>
          <div class="tag-meta">{meta}<br>{rec['confidence']} confidence in the price-sensitivity estimate</div>
        </div>""", unsafe_allow_html=True)

    with right:
        rows = [("Weekly orders", rec["orders_now"], rec["orders_new"], False),
                ("Weekly net revenue", rec["revenue_now"], rec["revenue_new"], True),
                ("Weekly contribution", rec["contribution_now"], rec["contribution_new"], True)]
        body = ""
        for name, a, b, money in rows:
            ch = b / a - 1
            fa = inr(a) if money else f"{a:,.0f}"
            fb = inr(b) if money else f"{b:,.0f}"
            body += (f"<tr><td>{name}</td><td>{fa}</td><td>{fb}</td>"
                     f"<td class='{delta_cls(ch)}'>{pct(ch)}</td></tr>")
        if rec["action"] != "HOLD":
            body += (f"<tr><td>Contribution change, cautious to optimistic</td><td></td><td></td>"
                     f"<td>{pct(rec['contribution_change_pessimistic_pct'])} to "
                     f"{pct(rec['contribution_change_optimistic_pct'])}</td></tr>")
        st.markdown(f"<table class='cmp'><tr><th></th><th>Today</th><th>Recommended</th>"
                    f"<th>Change</th></tr>{body}</table>", unsafe_allow_html=True)
        if rec["action"] != "HOLD":
            st.caption(f"That is {inr(rec['contribution_change_weekly'], sign=True)} a week, "
                       f"or about {inr(rec['contribution_change_weekly'] * 52, sign=True)} a year "
                       f"from this one item at this one store.")

    st.markdown(f"<div class='why'>{rec['rationale']}</div>", unsafe_allow_html=True)
    st.write("")

    tab1, tab2, tab3 = st.tabs(["Try a price", "Test a discount", "Sales history"])

    # ---- try a price
    with tab1:
        lo = int(base["price"] * (1 - max(0.20, max_move)))
        hi = int(base["price"] * (1 + max(0.20, max_move)))
        cA, cB = st.columns([1, 2], gap="large")
        with cA:
            my = st.slider("Your price (₹)", lo, hi, int(rec["recommended_price"]), 1,
                           key=f"try_{sid}_{pid}")
            q, rev, cm = pe.project(base, my)
            m1, m2 = st.columns(2)
            m1.metric("Weekly orders", f"{q:,.0f}", pct(q / base["orders"] - 1))
            m2.metric("Weekly revenue", inr(rev), pct(rev / rev0 - 1))
            m1.metric("Weekly contribution", inr(cm), pct(cm / cm0 - 1))
            be = pe.breakeven_volume_change(base, my)
            m2.metric("Break-even volume", "n/a" if not np.isfinite(be) else pct(be),
                      help="How much order volume must change for contribution to stay flat at this price.")
            move = my / base["price"] - 1
            checks = [
                (abs(move) <= max_move + 1e-9, f"Price change {pct(move)} within ±{max_move:.0%}"),
                (my <= base["competitor_price"] * (1 + comp_gap),
                 f"{pct(my / base['competitor_price'] - 1)} vs competitor, limit +{comp_gap:.0%}"),
                (q / base["orders"] - 1 >= -vol_floor,
                 f"Orders {pct(q / base['orders'] - 1)}, floor −{vol_floor:.0%}"),
                (pe.unit_margin(my, base) > 0, f"Margin per order {inr(pe.unit_margin(my, base))}"),
            ]
            st.markdown("<div class='check'>" + "<br>".join(
                f"{'✅' if ok else '❌'} {txt}" for ok, txt in checks) + "</div>", unsafe_allow_html=True)

        with cB:
            grid = np.arange(lo, hi + 1)
            cms, lows, highs, blocked = [], [], [], []
            for g in grid:
                q_, _, c_ = pe.project(base, g)
                cl = [pe.project(base, g, elasticity=e)[2] for e in (base["e_low"], base["e_high"])]
                cms.append(c_); lows.append(min(cl)); highs.append(max(cl))
                blocked.append(abs(g / base["price"] - 1) > max_move + 1e-9
                               or g > base["competitor_price"] * (1 + comp_gap)
                               or q_ / base["orders"] - 1 < -vol_floor)
            fig = go.Figure()
            # shade blocked ranges
            start = None
            for i, b in enumerate(blocked + [False]):
                if b and start is None:
                    start = grid[i]
                if not b and start is not None:
                    fig.add_vrect(x0=start - 0.5, x1=grid[i - 1] + 0.5, fillcolor=LOSS,
                                  opacity=0.06, line_width=0)
                    start = None
            fig.add_trace(go.Scatter(x=np.r_[grid, grid[::-1]], y=np.r_[highs, lows[::-1]],
                                     fill="toself", fillcolor="rgba(107,122,143,0.15)",
                                     line=dict(width=0), name="Likely range", hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=grid, y=cms, line=dict(color=INK, width=3),
                                     name="Projected weekly contribution",
                                     hovertemplate="₹%{x}: ₹%{y:,.0f}/week<extra></extra>"))
            for x, lab, col, sym in [(base["price"], "Today", SLATE, "circle"),
                                     (rec["recommended_price"], "Recommended", TAXI, "star"),
                                     (my, "Your price", INK, "diamond")]:
                fig.add_trace(go.Scatter(x=[x], y=[pe.project(base, x)[2]], mode="markers",
                                         marker=dict(size=16 if sym == "star" else 12, color=col, symbol=sym,
                                                     line=dict(color=INK, width=1.5)),
                                         name=lab, hovertemplate=f"{lab}: ₹%{{x}}<extra></extra>"))
            fig.update_xaxes(title="Menu price (₹)", tickprefix="₹")
            fig.update_yaxes(title="Weekly contribution (₹)", tickprefix="₹", tickformat=",.0f")
            st.plotly_chart(base_layout(fig, 400), width="stretch")
            st.caption("Red shading marks prices that break a business rule. "
                       "Grey band shows the range if customers are more or less price-sensitive than estimated.")

    # ---- discount
    with tab2:
        d = st.select_slider("Discount", [0.05, 0.10, 0.15, 0.20, 0.25], 0.15,
                             format_func=lambda x: f"{x:.0%} off", key=f"disc_{sid}_{pid}")
        dp = base["price"] * (1 - d)
        qd, rd, cd = pe.project(base, dp, extra_uplift=uplift)
        cA, cB = st.columns([1, 1.6], gap="large")
        with cA:
            ok = cd >= cm0
            st.markdown(f"#### {'This discount pays for itself' if ok else 'This discount loses money'}")
            joiner = "and" if ok else "but"
            st.write(f"At {d:.0%} off, the {p.product_name} sells for {inr(dp)}. Orders change by "
                     f"{pct(qd / base['orders'] - 1)} and revenue by {pct(rd / rev0 - 1)}, "
                     f"{joiner} contribution changes by **{pct(cd / cm0 - 1)}** "
                     f"({inr((cd - cm0), sign=True)} a week).")
            be = pe.breakeven_volume_change(base, dp)
            st.write(f"To break even, orders would need to rise {pct(be)}.")
            _, _, c_plain = pe.project(base, dp)
            st.caption(f"This assumes a discount draws {uplift:.0%} extra orders through visibility, "
                       f"on top of the price effect. Without that boost, the same {d:.0%} cut would change "
                       f"contribution by {pct(c_plain / cm0 - 1)}. Repeated discounts usually lose that "
                       f"boost, so treat discount results as optimistic.")
        with cB:
            vals = [qd / base["orders"] - 1, rd / rev0 - 1, cd / cm0 - 1]
            fig = go.Figure(go.Bar(
                x=["Orders", "Net revenue", "Contribution"], y=[v * 100 for v in vals],
                marker_color=[GAIN if v >= 0 else LOSS for v in vals],
                text=[pct(v) for v in vals], textposition="outside", cliponaxis=False))
            fig.update_yaxes(title="Change vs today (%)", ticksuffix="%")
            fig.add_hline(y=0, line_color=INK, line_width=1)
            st.plotly_chart(base_layout(fig, 320), width="stretch")

    # ---- history
    with tab3:
        h = sales[(sales.store_id == sid) & (sales.product_id == pid)].copy()
        h["week_start"] = pd.to_datetime(h.week_start)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=h.week_start, y=h.orders, name="Weekly orders",
                                 line=dict(color=INK, width=2)))
        promo = h[h.promo_flag == 1]
        fig.add_trace(go.Scatter(x=promo.week_start, y=promo.orders, mode="markers", name="Discount week",
                                 marker=dict(color=TAXI, size=9, line=dict(color=INK, width=1))))
        fig.add_trace(go.Scatter(x=h.week_start, y=h.effective_price, name="Price paid (₹)",
                                 yaxis="y2", line=dict(color=SLATE, width=1.5, shape="hv", dash="dot")))
        fig.update_layout(yaxis=dict(title="Orders"),
                          yaxis2=dict(title="Price (₹)", overlaying="y", side="right",
                                      tickprefix="₹", showgrid=False))
        st.plotly_chart(base_layout(fig, 380), width="stretch")
        st.caption(f"104 weeks, Apr 2024 to Mar 2026. {h.effective_price.nunique()} different prices "
                   f"in this history, from the April 2025 revision, store price tests and discounts. "
                   f"That variation is what the price-sensitivity estimate learns from.")


# ================================================================== CHAIN VIEW
def chain_view():
    rec, uni_cm, uni_q, uni_prices = chain_run(tuple(sorted(RULES.items())), commission, uplift)
    cm0, q0 = rec.contribution_now.sum(), rec.orders_now.sum()
    cm1, q1 = rec.contribution_new.sum(), rec.orders_new.sum()

    st.title("Chain view")
    st.markdown("<div class='profile'>8 stores, 6 products, 48 pricing decisions under the current business rules.</div>",
                unsafe_allow_html=True)
    st.write("")
    cols = st.columns(3, gap="large")
    scen = [("Today's uniform prices", cm0, q0, False),
            ("Best single price for the whole chain", uni_cm, uni_q, False),
            ("Store-level prices from this tool", cm1, q1, True)]
    for c, (name, cm, q, best) in zip(cols, scen):
        up = (cm - cm0) * 52
        c.markdown(f"""<div class="scn {'best' if best else ''}">
            <div>{name}</div>
            <div class="scn-num">{lakh(up) if abs(up) > 1 else '₹0'} a year</div>
            <div class="scn-sub">Contribution {pct(cm / cm0 - 1)}, orders {pct(q / q0 - 1)}</div>
            </div>""", unsafe_allow_html=True)
    st.write("")
    n = rec.action.value_counts()
    st.write(f"**{n.get('RAISE', 0)}** raises, **{n.get('LOWER', 0)}** cuts and **{n.get('HOLD', 0)}** holds. "
             f"Of the {n.get('RAISE', 0) + n.get('LOWER', 0)} changes, "
             f"**{(rec.rollout == 'Roll out').sum()}** can roll out now and "
             f"**{(rec.rollout == 'Pilot for 4 weeks first').sum()}** should be piloted first.")

    order_s = ["BKC", "Colaba", "Lower Parel", "Powai", "Ghatkopar", "Andheri West", "Thane", "Vile Parle"]
    order_p = list(products.product_name)
    m = rec.pivot(index="store_name", columns="product_name", values="price_change_pct").loc[order_s, order_p]
    pr = rec.pivot(index="store_name", columns="product_name", values="recommended_price").loc[order_s, order_p]
    ro = rec.pivot(index="store_name", columns="product_name", values="rollout").loc[order_s, order_p]
    text = [[("Hold" if abs(m.iloc[i, j]) < 1e-4 else
              f"₹{pr.iloc[i, j]:.0f}<br>{m.iloc[i, j]:+.0%}{' *' if ro.iloc[i, j].startswith('Pilot') else ''}")
             for j in range(len(order_p))] for i in range(len(order_s))]
    lim = max(0.05, max_move)
    fig = go.Figure(go.Heatmap(
        z=m.values * 100, x=[x.replace(" ", "<br>", 1) for x in order_p], y=order_s,
        text=text, texttemplate="%{text}", zmin=-lim * 100, zmax=lim * 100, zmid=0,
        colorscale=[[0, LOSS], [0.5, "#F5F6F7"], [1, GAIN]],
        colorbar=dict(title="Price<br>change", ticksuffix="%"),
        hovertemplate="%{y}, %{x}<br>%{z:+.1f}%<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    st.markdown("#### Recommended price by store and product")
    st.plotly_chart(base_layout(fig, 430), width="stretch")
    st.caption("Cells marked \\* should be piloted for 4 weeks first: the change could lose money if customers are more "
               "price-sensitive than estimated.")

    st.markdown("#### Every decision")
    show = rec[["store_name", "product_name", "action", "current_price", "recommended_price",
                "orders_change_pct", "contribution_change_pct", "contribution_change_weekly",
                "rollout", "confidence"]].copy()
    show.columns = ["Store", "Product", "Action", "Today ₹", "Recommended ₹", "Orders change",
                    "Contribution change", "Contribution ₹/week", "Rollout", "Confidence"]
    st.dataframe(show, hide_index=True, width="stretch", column_config={
        "Orders change": st.column_config.NumberColumn(format="percent"),
        "Contribution change": st.column_config.NumberColumn(format="percent"),
        "Contribution ₹/week": st.column_config.NumberColumn(format="%.0f"),
    })
    st.download_button("Download recommendations (CSV)", rec.to_csv(index=False),
                       "wrapstreet_recommendations.csv", "text/csv")
    st.caption("Best single chain-wide prices: " + ", ".join(
        f"{P.loc[k, 'product_name']} ₹{v:.0f}" for k, v in uni_prices.items()) +
        ". This comparison uses a chain-level volume floor and no competitor rule, which flatters uniform pricing.")


# ================================================================== HOW IT WORKS
def how_it_works():
    st.title("How it works")
    st.markdown("""
The desk answers one question for the commercial team: **should we raise, lower or keep the price of
this item at this store, and what happens to orders, revenue and contribution if we do?**
""")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("""
#### The method
1. **Learn price sensitivity.** For each store and item, a log-log regression on 104 weeks of
   sales estimates how orders respond to price, controlling for competitor price, discounts,
   festivals, month and growth. Noisy items borrow strength from the store's other items.
2. **Simulate.** Orders at a new price = today's orders × (new price ÷ today's price) ^ elasticity.
3. **Measure what matters.** Contribution = net revenue − food and packaging − aggregator
   commission on delivery orders. Rent and salaries don't change with one item's price, so they're left out.
4. **Decide within business rules.** Menu-style prices only, within the allowed move, competitor
   gap and volume floor. Small gains mean hold. Uncertain gains mean pilot first.
""")
    with c2:
        st.markdown("#### Does the model find the truth?")
        v = pd.read_csv(f"{pe.OUT}/elasticity_validation.csv")
        rv = pd.read_csv(f"{pe.OUT}/recommendation_validation.csv")
        moved = rv[rv.action != "HOLD"]
        st.write(f"The synthetic data was built with known price sensitivities, hidden from the model. "
                 f"Estimates landed within ±0.2 of the truth for **{int(v.within_0_2.sum())} of {len(v)}** "
                 f"store-items, and the truth sat inside the stated range for **{int(v.truth_in_ci.sum())} of {len(v)}**. "
                 f"Under the default rules, **{int((moved.true_cm_change > 0).sum())} of {len(moved)}** recommended "
                 f"price changes improve contribution under the true values.")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[-2.7, -0.4], y=[-2.7, -0.4], mode="lines", name="Perfect",
                                 line=dict(color=SLATE, dash="dash", width=1)))
        fig.add_trace(go.Scatter(
            x=v.true_own_price_elasticity, y=v.elasticity, mode="markers", name="Store-item",
            marker=dict(size=9, color=np.where(v.within_0_2, INK, LOSS)),
            text=v.store_name.str.replace("WrapStreet ", "") + ", " + v.product_name,
            hovertemplate="%{text}<br>true %{x:.2f}, estimated %{y:.2f}<extra></extra>"))
        fig.update_xaxes(title="True price sensitivity")
        fig.update_yaxes(title="Estimated")
        st.plotly_chart(base_layout(fig, 320), width="stretch")

    st.markdown("#### Assumptions")
    st.dataframe(pd.DataFrame([
        ("Data", "Synthetic: fictional 8-outlet chain in real Mumbai areas, Apr 2024 to Mar 2026"),
        ("Revenue", "Ex-GST (5% restaurant GST passes through)"),
        ("Aggregator commission", f"{commission:.0%} of order value on delivery orders (adjustable)"),
        ("Food and packaging cost", "27% to 37% of today's price, by item"),
        ("Discount visibility", f"{uplift:.0%} extra orders beyond the price effect, assumed not to fade"),
        ("Price sensitivity", "Constant within ±20% of today's price"),
        ("Current state", "Average of the last 8 weeks (Feb to Mar 2026)"),
    ], columns=["Item", "Assumption"]), hide_index=True, width="stretch")

    st.markdown("#### Limits to keep in mind")
    st.markdown("""
- **Competitors are assumed not to react.** A rival matching our cut would shrink the gain.
- **Items are priced one at a time.** Customers switching between items (wrap to bowl) isn't modelled.
- **The model only learns from past price variation.** Prices far outside what was tried are extrapolation.
- **Short-run, weekly effects only.** Brand perception and long-term habits aren't captured.
""")


{"Price desk": price_desk, "Chain view": chain_view, "How it works": how_it_works}[page]()
