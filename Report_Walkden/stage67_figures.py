"""
stage67_figures.py
==================================================================
Reproduces the Stage 6 & Stage 7 figures for the Ostrom Power-Markets
report, straight from the raw project CSVs.

Pipeline (self-contained, no notebook state required):
    1. Scale the three SLPs to the customer book  -> forecast load L
    2. Build the HPFC from futures + historical shape (granular anchors)
    3. Solve both value-neutral KKT hedges          -> COARSE_CAL, GRANULAR
    4. Decompose cost = futures + DA-residual + imbalance, per quarter-hour
    5. Aggregate to the figures used in the deck

Figures produced (PNG):
    S6_comparison_table.png   9-measure x 3-strategy table
    S6_monthly_price.png      monthly procurement price, 3 strategies
    S6_ES_tail.png            Mean / VaR95 / ES95 / ES99 of daily cost
    S7_dec_exposure.png       residual exposure vs realised DA, 10-14 Dec
    S7_episode_table.png      11-12 Dec cost decomposition

Usage:
    python stage67_figures.py
Point DATA_DIR / OUT_DIR below at wherever the CSVs and output live.
For LaTeX inclusion you can switch savefig to .pdf (vector) instead of .png.
==================================================================
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

# ----------------------------------------------------------------- config
DATA_DIR = "."                      # folder holding the raw CSVs
OUT_DIR  = "./figures"              # where PNGs are written
os.makedirs(OUT_DIR, exist_ok=True)

DT = 0.25                           # hours per quarter-hour interval
SCALE = {"HB": 35, "GB": 6, "LB": 2}   # SLP -> customer book (E_p / 1000 MWh)
GRANULAR_BLOCKS = ["M01", "M02", "M03", "Q2", "Q3", "Q4"]  # finest tradable cover

# deck palette
NAVY, TEAL, AMBER, GREY = "#16324F", "#2E9D93", "#E8963A", "#8B97A5"
AMBERBG, AMBEREDGE = "#FBEFDD", "#E8963A"


# ================================================================= 1. data
def load_inputs():
    p = lambda f: os.path.join(DATA_DIR, f)

    slp = pd.read_csv(p("slp_profiles.csv"))
    slp["timestamp_utc"] = pd.to_datetime(slp["timestamp_utc"], utc=True)
    slp["timestamp_local"] = slp["timestamp_utc"].dt.tz_convert("Europe/Berlin")
    # forecast load L_t : scale each normalised SLP and sum (result in MWh)
    slp["portfolio_mwh"] = (
        slp["hb_normalized_kwh"] * SCALE["HB"]
        + slp["gb_normalized_kwh"] * SCALE["GB"]
        + slp["lb_normalized_kwh"] * SCALE["LB"]
    ) / 1000.0

    shape = pd.read_csv(p("shape_factors.csv"))
    shape["timestamp_utc"] = pd.to_datetime(shape["timestamp_utc"], utc=True)

    fut = pd.read_csv(p("futures_prices.csv"))

    da  = pd.read_csv(p("day_ahead_prices.csv"))
    da["timestamp_utc"] = pd.to_datetime(da["timestamp_utc"], utc=True)

    imb = pd.read_csv(p("imbalance_prices.csv"))
    imb["timestamp_utc"] = pd.to_datetime(imb["timestamp_utc"], utc=True)

    act = pd.read_csv(p("actual_portfolio_load.csv"))
    act["timestamp_utc"] = pd.to_datetime(act["timestamp_utc"], utc=True)

    return slp, shape, fut, da, imb, act


def futures_price(fut, period, load_type):
    """Quoted futures price for a delivery period and BASE/PEAK."""
    m = (fut["delivery_period"].astype(str) == period) & (fut["load_type"] == load_type)
    return float(fut.loc[m, "price_eur_mwh"].iloc[0])


# ================================================================= 2. HPFC
def build_hpfc(slp, shape, fut):
    """
    HPFC_t = anchor_price(block, peak/off) * shape_t / mean_block(shape).
    Off-peak prices are implied from Base/Peak by volume identity:
        P_off = (P_base * N_all - P_peak * N_peak) / N_off
    Curve is built hourly then mapped onto the quarter-hour grid.
    """
    shape = shape.copy()
    shape["hour_utc"] = shape["timestamp_utc"].dt.floor("h")
    sh = (shape.groupby("hour_utc")
                .agg(historical_shape_factor=("historical_shape_factor", "mean"),
                     is_peak=("is_peak", "first"))
                .reset_index())
    sh["timestamp_local"] = sh["hour_utc"].dt.tz_convert("Europe/Berlin")

    def anchor_of(ts):
        m = ts.month
        return ({1: "M01", 2: "M02", 3: "M03"}.get(m)
                or ("Q2" if m in (4, 5, 6) else "Q3" if m in (7, 8, 9) else "Q4"))
    sh["anchor_period"] = sh["timestamp_local"].apply(anchor_of)

    rows = []
    for period in GRANULAR_BLOCKS:
        blk = sh[sh["anchor_period"] == period]
        n_all, n_pk = len(blk), int(blk["is_peak"].sum())
        n_off = n_all - n_pk
        b = futures_price(fut, period, "BASE")
        pk = futures_price(fut, period, "PEAK")
        off = (n_all * b - n_pk * pk) / n_off
        rows.append({"anchor_period": period, "base_price": b,
                     "peak_price": pk, "offpeak_price": off})
    anc = pd.DataFrame(rows)

    sh = sh.merge(anc, on="anchor_period", how="left")
    sh["anchor_price"] = np.where(sh["is_peak"] == 1, sh["peak_price"], sh["offpeak_price"])
    sh["shape_mean"] = sh.groupby(["anchor_period", "is_peak"])[
        "historical_shape_factor"].transform("mean")
    sh["hpfc_eur_mwh"] = sh["anchor_price"] * sh["historical_shape_factor"] / sh["shape_mean"]

    grid = slp[["timestamp_utc", "timestamp_local", "portfolio_mwh"]].copy()
    grid["hour_utc"] = grid["timestamp_utc"].dt.floor("h")
    grid = grid.merge(sh[["hour_utc", "hpfc_eur_mwh"]], on="hour_utc", how="left")
    # peak flag on the quarter-hour grid: Mon-Fri 08:00-20:00 local
    loc = grid["timestamp_local"]
    grid["is_peak"] = ((loc.dt.dayofweek < 5) & (loc.dt.hour >= 8) & (loc.dt.hour < 20)).astype(int)
    return grid


# ================================================================= 3. hedge
def solve_block(L, P, is_peak):
    """
    Value-neutral minimum-variance hedge for one block via the KKT system.
    Decision vector x = [x_base, x_peak] in MW.
    Objective: min ||L - H||^2 ,  H_t = DT*(x_base + x_peak*is_peak)
    Constraint: sum(H*P) = sum(L*P)  (equal EUR-value under the HPFC).
    """
    A = np.column_stack([np.full(len(L), DT), DT * is_peak])   # H = A @ x
    c = A.T @ P                       # value of each unit position
    value_L = L @ P                   # EUR-value of the load
    KKT = np.block([[2 * A.T @ A, c.reshape(-1, 1)],
                    [c.reshape(1, -1), np.zeros((1, 1))]])
    rhs = np.concatenate([2 * A.T @ L, [value_L]])
    sol = np.linalg.solve(KKT, rhs)
    return sol[0], sol[1]             # x_base, x_peak  (both > 0 here, so KKT = equality-constrained LS)


def add_hedges(grid, fut):
    L = grid["portfolio_mwh"].to_numpy()
    P = grid["hpfc_eur_mwh"].to_numpy()
    pk = grid["is_peak"].to_numpy()

    # COARSE_CAL : one calendar-year block
    cb, cp = solve_block(L, P, pk)
    grid["hedge_coarse"] = DT * (cb + cp * grid["is_peak"])

    # GRANULAR : one block per M01..M03, Q2..Q4
    def gblock(m):
        return ({1: "M01", 2: "M02", 3: "M03"}.get(m)
                or ("Q2" if m in (4, 5, 6) else "Q3" if m in (7, 8, 9) else "Q4"))
    grid["gperiod"] = grid["timestamp_local"].dt.month.map(gblock)
    gpos = {}
    grid["hedge_gran"] = 0.0
    for period in GRANULAR_BLOCKS:
        mask = (grid["gperiod"] == period).to_numpy()
        xb, xp = solve_block(L[mask], P[mask], pk[mask])
        gpos[period] = (xb, xp)
        grid.loc[mask, "hedge_gran"] = DT * (xb + xp * grid.loc[mask, "is_peak"])

    return grid, (cb, cp), gpos


# ================================================================= 4. costs
def add_costs(grid, fut, coarse_pos, gpos):
    cb, cp = coarse_pos
    CALb, CALp = futures_price(fut, "CAL", "BASE"), futures_price(fut, "CAL", "PEAK")

    # per-interval futures cost (base leg every hour + peak leg in peak hours)
    grid["fut_coarse"] = DT * (cb * CALb + cp * grid["is_peak"] * CALp)
    grid["fut_gran"] = grid.apply(
        lambda r: DT * (gpos[r["gperiod"]][0] * futures_price(fut, r["gperiod"], "BASE")
                        + gpos[r["gperiod"]][1] * r["is_peak"] * futures_price(fut, r["gperiod"], "PEAK")),
        axis=1)

    # residual R = L - H, priced at realised Day-Ahead
    grid["res_coarse"] = grid["portfolio_mwh"] - grid["hedge_coarse"]
    grid["res_gran"]   = grid["portfolio_mwh"] - grid["hedge_gran"]
    grid["da_unh"]    = grid["portfolio_mwh"] * grid["day_ahead_price_eur_mwh"]
    grid["da_coarse"] = grid["res_coarse"] * grid["day_ahead_price_eur_mwh"]
    grid["da_gran"]   = grid["res_gran"]   * grid["day_ahead_price_eur_mwh"]

    # imbalance I = A - L, settled at reBAP (strategy-invariant)
    grid["imb_mwh"] = grid["total_actual_mwh"] - grid["portfolio_mwh"]
    grid["imb"]     = grid["imb_mwh"] * grid["imbalance_price_eur_mwh"]

    # total procurement cost per interval, per strategy
    grid["cost_unh"]    = grid["da_unh"] + grid["imb"]
    grid["cost_coarse"] = grid["fut_coarse"] + grid["da_coarse"] + grid["imb"]
    grid["cost_gran"]   = grid["fut_gran"]   + grid["da_gran"]   + grid["imb"]
    return grid


def build_dataset():
    slp, shape, fut, da, imb, act = load_inputs()
    grid = build_hpfc(slp, shape, fut)
    grid = grid.merge(da[["timestamp_utc", "day_ahead_price_eur_mwh"]], on="timestamp_utc", how="left")
    grid = grid.merge(imb[["timestamp_utc", "imbalance_price_eur_mwh"]], on="timestamp_utc", how="left")
    grid = grid.merge(act[["timestamp_utc", "total_actual_mwh"]], on="timestamp_utc", how="left")
    grid, coarse_pos, gpos = add_hedges(grid, fut)
    grid = add_costs(grid, fut, coarse_pos, gpos)
    return grid, fut


# ================================================================= helpers
def callout(ax, x, y, text, fs=10.0):
    ax.annotate(text, xy=(x, y), xycoords="axes fraction", fontsize=fs,
                ha="left", va="top", color=NAVY,
                bbox=dict(boxstyle="round,pad=0.55", fc=AMBERBG, ec=AMBEREDGE, lw=1.4))


def daily_price(grid, cost_col):
    """Daily cost-weighted procurement price (EUR/MWh) = daily cost / daily actual load."""
    g = grid.groupby(grid["timestamp_local"].dt.date)
    return (g[cost_col].sum() / g["total_actual_mwh"].sum())

def monthly_price(grid, cost_col):
    g = grid.groupby(grid["timestamp_local"].dt.month)
    return (g[cost_col].sum() / g["total_actual_mwh"].sum())


# ================================================================= 5. figures
def fig_comparison_table(grid):
    load = grid["total_actual_mwh"].sum()
    cost = {k: grid[c].sum() for k, c in
            [("U", "cost_unh"), ("C", "cost_coarse"), ("G", "cost_gran")]}
    mp = {k: monthly_price(grid, c) for k, c in
          [("U", "cost_unh"), ("C", "cost_coarse"), ("G", "cost_gran")]}
    res = {"C": grid["res_coarse"], "G": grid["res_gran"]}
    rmse = {k: np.sqrt((v ** 2).mean()) for k, v in res.items()}
    imb_settle = grid["imb"].sum()
    imb_prem = (grid["imb_mwh"] * (grid["imbalance_price_eur_mwh"] - grid["day_ahead_price_eur_mwh"])).sum()

    # rows: (label, U, C, G, best)  best: 1=lowest wins, 2=GRAN column, 0=none
    rows = [
        ("Final annual cost (EUR)",          f"{cost['U']:,.0f}", f"{cost['C']:,.0f}", f"{cost['G']:,.0f}", 1),
        ("Average procurement price (EUR/MWh)", f"{cost['U']/load:.2f}", f"{cost['C']/load:.2f}", f"{cost['G']/load:.2f}", 1),
        ("Saving vs UNHEDGED (EUR)",         "0", f"{cost['U']-cost['C']:,.0f}", f"{cost['U']-cost['G']:,.0f}", 1),
        ("Monthly price std. dev. (EUR/MWh)", f"{mp['U'].std():.2f}", f"{mp['C'].std():.2f}", f"{mp['G'].std():.2f}", 1),
        ("Monthly price range (EUR/MWh)",    f"{mp['U'].max()-mp['U'].min():.2f}", f"{mp['C'].max()-mp['C'].min():.2f}", f"{mp['G'].max()-mp['G'].min():.2f}", 1),
        ("Absolute residual DA volume (MWh)", f"{grid['portfolio_mwh'].abs().sum():,.0f}", f"{res['C'].abs().sum():,.0f}", f"{res['G'].abs().sum():,.0f}", 2),
        ("Residual-load RMSE (MWh)",         "\u2014", f"{rmse['C']:.2f}", f"{rmse['G']:.2f}", 2),
        ("Imbalance settlement (EUR)",       f"{imb_settle:,.0f}", f"{imb_settle:,.0f}", f"{imb_settle:,.0f}", 0),
        ("Imbalance premium (EUR)",          f"{imb_prem:,.0f}", f"{imb_prem:,.0f}", f"{imb_prem:,.0f}", 0),
    ]
    fig, ax = plt.subplots(figsize=(11, 6.6)); ax.axis("off")
    ax.set_title("Total cost & risk across the three strategies", color=NAVY,
                 fontsize=15, fontweight="bold", loc="left", pad=14)
    colx = [0.02, 0.44, 0.635, 0.83]; colw = 0.165; y0 = 0.86; rh = 0.088
    for j, h in enumerate(["Measure", "UNHEDGED", "COARSE_CAL", "GRANULAR"]):
        w = 0.42 if j == 0 else colw
        ax.add_patch(FancyBboxPatch((colx[j], y0), w, rh, boxstyle="square,pad=0",
                                    transform=ax.transAxes, fc=NAVY, ec="none"))
        ax.text(colx[j] + 0.008, y0 + rh/2, h, transform=ax.transAxes, color="white",
                fontsize=10, fontweight="bold", va="center")
    for i, (label, u, c, g, best) in enumerate(rows):
        yy = y0 - (i + 1) * rh
        ax.text(colx[0] + 0.008, yy + rh/2, label, transform=ax.transAxes, color=NAVY,
                va="center", fontsize=9.5)
        for j, v in enumerate([u, c, g]):
            win = (best == 1 and j == 1) or (best == 2 and j == 2)
            fc = (TEAL if j == 1 else AMBER) if win else "#F3F5F8"
            ax.add_patch(FancyBboxPatch((colx[j+1], yy), colw, rh, boxstyle="square,pad=0",
                                        transform=ax.transAxes, fc=fc, ec="#DDE3EA", lw=0.8))
            ax.text(colx[j+1] + colw/2, yy + rh/2, v, transform=ax.transAxes,
                    color="white" if win else NAVY, va="center", ha="center",
                    fontsize=9.5, fontweight="bold" if win else "normal")
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "S6_comparison_table.png"), dpi=170,
                bbox_inches="tight", facecolor="white"); plt.close()


def fig_monthly_price(grid):
    mp = {k: monthly_price(grid, c) for k, c in
          [("UNHEDGED", "cost_unh"), ("COARSE CAL", "cost_coarse"), ("GRANULAR", "cost_gran")]}
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    fig, ax = plt.subplots(figsize=(10.5, 5.6))
    ax.axvspan(9.5, 12.5, color=AMBERBG, alpha=0.7, zorder=0)          # Q4 shading
    for name, col in [("UNHEDGED", GREY), ("COARSE CAL", TEAL), ("GRANULAR", AMBER)]:
        ax.plot(range(1, 13), mp[name].values, "o-", lw=2.2 if name != "UNHEDGED" else 2,
                color=col, label=name)
    ax.set_xticks(range(1, 13)); ax.set_xticklabels(months)
    ax.set_ylabel("Monthly procurement price (EUR/MWh)", color=NAVY)
    ax.set_title("Monthly procurement price by strategy", color=NAVY, fontsize=13.5,
                 fontweight="bold")
    ax.grid(alpha=0.25); ax.legend(frameon=False, loc="upper left", ncol=3)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "S6_monthly_price.png"), dpi=170,
                bbox_inches="tight", facecolor="white"); plt.close()


def fig_es_tail(grid):
    dp = {k: daily_price(grid, c) for k, c in
          [("UNHEDGED", "cost_unh"), ("COARSE CAL", "cost_coarse"), ("GRANULAR", "cost_gran")]}
    def es(s, q):  # expected shortfall = mean beyond the q-quantile
        return s[s >= s.quantile(q)].mean()
    metrics = ["Mean", "VaR 95%", "ES 95%", "ES 99%"]
    vals = {k: [dp[k].mean(), dp[k].quantile(0.95), es(dp[k], 0.95), es(dp[k], 0.99)]
            for k in dp}
    x = np.arange(4); w = 0.26
    fig, ax = plt.subplots(figsize=(9.8, 5.6))
    for off, (name, col) in zip([-w, 0, w],
                                [("UNHEDGED", GREY), ("COARSE CAL", TEAL), ("GRANULAR", AMBER)]):
        bars = ax.bar(x + off, vals[name], w, color=col, label=name)
        for xi, b in zip(x, bars):
            ax.text(b.get_x() + b.get_width()/2, b.get_height() + 3,
                    f"{b.get_height():.0f}", ha="center", fontsize=8, color=NAVY)
    # highlight COARSE as the tail winner on the risk metrics
    for i in (1, 2, 3):
        ax.add_patch(Rectangle((x[i] - w/2 - 0.02, 0), w + 0.04, vals["COARSE CAL"][i],
                               fill=False, ec="#D7263D", lw=1.8))
    ax.set_xticks(x); ax.set_xticklabels(metrics)
    ax.set_ylabel("Daily procurement price (EUR/MWh)", color=NAVY)
    ax.set_title("Cost tail (Expected Shortfall) \u2014 strategies tie on the mean, separate in the tail",
                 color=NAVY, fontsize=12.5, fontweight="bold")
    ax.legend(frameon=False); ax.grid(alpha=0.25, axis="y")
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "S6_ES_tail.png"), dpi=170,
                bbox_inches="tight", facecolor="white"); plt.close()


def fig_dec_exposure(grid):
    d = grid["timestamp_local"].dt.date.astype(str)
    win = grid[d.isin(["2024-12-10", "2024-12-11", "2024-12-12", "2024-12-13"])].copy()
    t = win["timestamp_local"].dt.tz_localize(None)
    fig, ax = plt.subplots(figsize=(11, 5.8))
    ax.plot(t, win["portfolio_mwh"], color=GREY, lw=1.8, label="UNHEDGED residual (=full load)")
    ax.plot(t, win["res_coarse"], color=TEAL, lw=1.8, label="COARSE residual R=L\u2212H")
    ax.plot(t, win["res_gran"], color=AMBER, lw=1.8, label="GRANULAR residual R=L\u2212H")
    ax.axhline(0, color="#9AA6B2", lw=0.8)
    ax.set_ylabel("Residual exposure to DA (MWh / 0.25h)", color=NAVY)
    ax2 = ax.twinx()
    ax2.plot(t, win["day_ahead_price_eur_mwh"], "--", color=NAVY, lw=1.6, label="Realised DA price")
    ax2.set_ylabel("Day-Ahead price (EUR/MWh)", color=NAVY)
    ip = win["day_ahead_price_eur_mwh"].idxmax()
    pt = win.loc[ip, "timestamp_local"].tz_localize(None); pv = win.loc[ip, "day_ahead_price_eur_mwh"]
    ax2.annotate(f"DA peak {pv:.0f} EUR/MWh\n12 Dec", xy=(pt, pv), xytext=(pt, pv * 0.72),
                 fontsize=9.5, color=NAVY, ha="center", fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color=NAVY, lw=1.4),
                 bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=NAVY, lw=1.2))
    ax.set_title("Severe price event \u2014 residual exposure vs the Dunkelflaute spike (10\u201313 Dec)",
                 color=NAVY, fontsize=13, fontweight="bold", loc="left")
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, loc="upper left", fontsize=9)
    ax.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "S7_dec_exposure.png"), dpi=170,
                bbox_inches="tight", facecolor="white"); plt.close()


def fig_episode_table(grid):
    d = grid["timestamp_local"].dt.date.astype(str)
    w = grid[d.isin(["2024-12-11", "2024-12-12"])]
    fut_c = w["fut_coarse"].sum(); fut_g = w["fut_gran"].sum()
    da_u = w["da_unh"].sum(); da_c = w["da_coarse"].sum(); da_g = w["da_gran"].sum()
    imb = w["imb"].sum()
    data = [("UNHEDGED",   0,     da_u, imb, da_u + imb),
            ("COARSE_CAL", fut_c, da_c, imb, fut_c + da_c + imb),
            ("GRANULAR",   fut_g, da_g, imb, fut_g + da_g + imb)]
    fig, ax = plt.subplots(figsize=(10, 4.2)); ax.axis("off")
    ax.set_title("Severe price event \u2014 11\u201312 December cost decomposition (EUR)",
                 color=NAVY, fontsize=14, fontweight="bold", loc="left", pad=12)
    heads = ["", "Futures", "DA residual", "Imbalance", "TOTAL"]
    colx = [0.01, 0.22, 0.42, 0.63, 0.82]; colw = 0.175; y0 = 0.66; rh = 0.15
    for j, h in enumerate(heads):
        ax.add_patch(FancyBboxPatch((colx[j], y0), colw, rh, boxstyle="square,pad=0",
                                    transform=ax.transAxes, fc=NAVY, ec="none"))
        ax.text(colx[j] + (0.01 if j == 0 else colw/2), y0 + rh/2, h, transform=ax.transAxes,
                color="white", fontsize=11, fontweight="bold",
                va="center", ha="left" if j == 0 else "center")
    rowcol = {"UNHEDGED": GREY, "COARSE_CAL": TEAL, "GRANULAR": AMBER}
    for i, (name, f, r, im, tot) in enumerate(data):
        yy = y0 - (i + 1) * rh
        ax.text(colx[0] + 0.01, yy + rh/2, name, transform=ax.transAxes,
                color=rowcol[name], fontweight="bold", va="center", fontsize=11)
        for j, v in enumerate([f, r, im, tot]):
            ax.add_patch(FancyBboxPatch((colx[j+1], yy), colw, rh, boxstyle="square,pad=0",
                                        transform=ax.transAxes,
                                        fc=("#EEF4F3" if j == 2 else "#F5F7FA"), ec="#DDE3EA", lw=0.8))
            ax.text(colx[j+1] + colw/2, yy + rh/2, f"{v:,.0f}", transform=ax.transAxes,
                    color=NAVY, va="center", ha="center",
                    fontsize=11, fontweight="bold" if j == 3 else "normal")
    plt.savefig(os.path.join(OUT_DIR, "S7_episode_table.png"), dpi=170,
                bbox_inches="tight", facecolor="white"); plt.close()


# ================================================================= main
if __name__ == "__main__":
    grid, fut = build_dataset()

    # quick reconciliation printout (matches the deck; delete if not wanted)
    load = grid["total_actual_mwh"].sum()
    print("Forecast load (MWh):", round(grid["portfolio_mwh"].sum(), 1))
    print("Realised load (MWh):", round(load, 1))
    print("HPFC base mean (EUR/MWh):", round(grid["hpfc_eur_mwh"].mean(), 3), "(quoted CAL base 77.26)")
    for k, c in [("UNHEDGED", "cost_unh"), ("COARSE_CAL", "cost_coarse"), ("GRANULAR", "cost_gran")]:
        print(f"  {k:11s} annual cost EUR {grid[c].sum():,.0f}")

    fig_comparison_table(grid)
    fig_monthly_price(grid)
    fig_es_tail(grid)
    fig_dec_exposure(grid)
    fig_episode_table(grid)
    print("Figures written to", os.path.abspath(OUT_DIR))
