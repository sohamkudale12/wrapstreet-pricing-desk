# WrapStreet Pricing Desk

A prototype that helps a restaurant chain's commercial team test price changes for any
product at any store, see the effect on orders, revenue and contribution, and get a
recommended price with a plain-English rationale.

All data is synthetic: a fictional 8-outlet quick-service chain in real Mumbai areas,
6 products, 104 weeks (Apr 2024 to Mar 2026).

## Run it (about 2 minutes)

1. Install Python 3.10 or newer.
2. Open a terminal in this folder and run:

       pip install -r requirements.txt
       streamlit run app.py

3. The app opens in your browser at http://localhost:8501.

To share a link instead, push this folder to a GitHub repo and deploy it free on
Streamlit Community Cloud (share.streamlit.io), pointing it at `app.py`.

## What's inside

| File | What it does |
|---|---|
| `app.py` | The Streamlit app: Price desk, Chain view, How it works |
| `pricing_engine.py` | Simulation: orders, revenue, contribution at any price or discount |
| `recommend.py` | Decision logic: guardrails, hold rule, pilot-or-roll-out advice, rationale |
| `data/` | Synthetic sales data and the estimated price sensitivities |
| `pipeline/` | Scripts that regenerate the data and re-estimate the model |
| `test_app.py` | Automated check that every page and all 48 store-products load |

## Rebuilding the data (optional)

    cd pipeline
    python generate_data.py         # creates pipeline/output/ with the synthetic data
    python estimate_elasticity.py   # estimates price sensitivity, checks against the truth
    python build_workbook.py        # optional Excel version of the data

Copy `stores.csv`, `products.csv`, `weekly_sales.csv`, `elasticity_estimates.csv` and
`elasticity_validation.csv` from `pipeline/output/` into `data/`. The random seed is fixed,
so the results are identical to the shipped data.

## Suggested demo path (1.5 minutes)

1. **BKC: raise.** Low price sensitivity: raise the Chicken Tikka Wrap to ₹249. Point out
   that ₹259 was blocked by the volume floor.
2. **Test a discount at BKC.** 15% off lifts orders and revenue but cuts contribution.
3. **Vile Parle: lower.** Same wrap, same price, opposite answer: cut to ₹199, pilot first.
4. **Chain view.** Store-level prices earn about twice the uplift of the best single
   chain-wide price, without losing orders.
