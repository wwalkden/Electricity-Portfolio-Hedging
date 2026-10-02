import numpy as np, pandas as pd
g=pd.read_pickle("grid2.pkl"); loc=g.timestamp_local
d=loc.dt.date.astype(str); w=g[d.isin(["2024-12-11","2024-12-12"])]
print("intervals",len(w),"L",w.portfolio_mwh.sum(),"A",w.total_actual_mwh.sum(),"Hc",w.hedge_coarse.sum(),"Hg",w.hedge_gran.sum())
for k,f,r in [("U",None,"da_unh"),("C","fut_coarse","da_coarse"),("G","fut_gran","da_gran")]:
    F=w[f].sum() if f else 0; R=w[r].sum(); print(k,"fut",round(F),"da",round(R),"imb",round(w.imb.sum()),"tot",round(F+R+w.imb.sum()), "per MWh actual", round((F+R+w.imb.sum())/w.total_actual_mwh.sum(),2))
    res = w.portfolio_mwh if k=="U" else w.portfolio_mwh - w[{"C":"hedge_coarse","G":"hedge_gran"}[k]]
    print("   residual pos",round(res[res>0].sum(),1),"neg",round(res[res<0].sum(),1),"DA-weighted cost of pos",round((res[res>0]*w.day_ahead_price_eur_mwh[res>0]).sum()))
    # sensitivity: DA x2 on event days
    print("   +cost if DA doubled", round((res*w.day_ahead_price_eur_mwh).sum()))
print("DA event mean",w.day_ahead_price_eur_mwh.mean(),"max",w.day_ahead_price_eur_mwh.max(), loc[w.day_ahead_price_eur_mwh.idxmax()])
print("reBAP event max",w.imbalance_price_eur_mwh.max(),"min",w.imbalance_price_eur_mwh.min(),"imb premium", (w.imb_mwh*(w.imbalance_price_eur_mwh-w.day_ahead_price_eur_mwh)).sum())
# hourly profile of price on 12 dec
w12=g[d=="2024-12-12"]; hh=w12.groupby(w12.timestamp_local.dt.hour).agg(DA=("day_ahead_price_eur_mwh","mean"),L=("portfolio_mwh","sum"),Rc=("res_coarse","sum"),Rg=("res_gran","sum"))
print(hh.round(2).to_string())
# Dec month: normal day costs
dec=g[loc.dt.month==12]; dd=dec.groupby(dec.timestamp_local.dt.date)[["cost_unh","cost_coarse","cost_gran"]].sum()
print(dd.median().round(0).to_dict())
# Q4 flip
q4=loc.dt.month>=10
dH=(g.hedge_gran[q4]-g.hedge_coarse[q4]).sum(); diff=g.cost_gran.sum()-g.cost_coarse.sum()
print("Q4 dH",dH,"cost diff G-C",diff,"flip at uniform Q4 DA shift",diff/dH)
# annual load-weighted
print("annual U cost / 366", g.cost_unh.sum()/366)
# monthly futures payoff
for k,h,f in [("C","hedge_coarse","fut_coarse"),("G","hedge_gran","fut_gran")]:
    pi=(g[h]*g.day_ahead_price_eur_mwh-g[f]).groupby(loc.dt.month).sum()
    print(k,"payoff by month",pi.round(0).to_dict())
