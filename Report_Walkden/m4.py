import numpy as np, pandas as pd, stage67_figures as s
g=pd.read_pickle("grid2.pkl"); fut=pd.read_csv("futures_prices.csv"); loc=g.timestamp_local
L=g.portfolio_mwh.to_numpy(); P=g.hpfc_eur_mwh.to_numpy(); pk=g.is_peak.to_numpy()
q=((loc.dt.month-1)//3+1).map(lambda i:f"Q{i}").to_numpy()
H=np.zeros(len(g)); F=np.zeros(len(g)); pos={}
for b in ["Q1","Q2","Q3","Q4"]:
    m=q==b; xb,xp=s.solve_block(L[m],P[m],pk[m]); pos[b]=(xb,xp)
    H[m]=0.25*(xb+xp*pk[m]); F[m]=0.25*(xb*s.futures_price(fut,b,"BASE")+xp*pk[m]*s.futures_price(fut,b,"PEAK"))
print(pos)
g["hedge_q"]=H; g["fut_q"]=F; g["res_q"]=g.portfolio_mwh-H; g["da_q"]=g.res_q*g.day_ahead_price_eur_mwh; g["cost_q"]=g.fut_q+g.da_q+g.imb
R=g.res_q; print("notional",H.sum(),"VN",(H*P).sum()-(L*P).sum(),"RMSE",np.sqrt((R**2).mean()),"absR",R.abs().sum())
print("Cfut",F.sum(),"Cres",g.da_q.sum(),"Cfin",g.cost_q.sum(),"saving",g.cost_unh.sum()-g.cost_q.sum(),"avgp",g.cost_q.sum()/g.total_actual_mwh.sum())
mp=s.monthly_price(g,"cost_q"); print("std",mp.std(),"range",mp.max()-mp.min()); print(mp.round(2).to_dict())
dp=s.daily_price(g,"cost_q"); es=lambda x,qq:x[x>=x.quantile(qq)].mean()
print("mean",dp.mean(),"VaR95",dp.quantile(.95),"ES95",es(dp,.95),"ES99",es(dp,.99))
d=loc.dt.date.astype(str); w=g[d.isin(["2024-12-11","2024-12-12"])]
print("event fut",w.fut_q.sum(),"da",w.da_q.sum(),"tot",w.cost_q.sum())
g.to_pickle("grid3.pkl")
