import numpy as np, pandas as pd
g=pd.read_pickle("grid3.pkl"); loc=g.timestamp_local; DA=g.day_ahead_price_eur_mwh; P=g.hpfc_eur_mwh; L=g.portfolio_mwh
es=lambda x,qq:x[x>=x.quantile(qq)].mean()
day=loc.dt.date; mon=loc.dt.month
for k,R in [("U",L),("C",g.res_coarse),("Q",g.res_q),("G",g.res_gran)]:
    sur=R*(DA-P)
    ds=sur.groupby(day).sum(); ms=sur.groupby(mon).sum()
    print(k,"annual surprise",round(sur.sum()),"daily std",round(ds.std()),"VaR95",round(ds.quantile(.95)),"ES95",round(es(ds,.95)),"ES99",round(es(ds,.99)),"max",round(ds.max()),"| monthly std",round(ms.std()),"max",round(ms.max()),"min",round(ms.min()))
# ex-ante price per month for each strategy: (fut + R*HPFC)/L
for k,f,R in [("U",None,L),("C","fut_coarse",g.res_coarse),("Q","fut_q",g.res_q),("G","fut_gran",g.res_gran)]:
    ea=((g[f] if f else 0)+R*P).groupby(mon).sum()/L.groupby(mon).sum()
    print(k,"ex-ante monthly price",ea.round(2).to_dict(),"std",round(ea.std(),2))
