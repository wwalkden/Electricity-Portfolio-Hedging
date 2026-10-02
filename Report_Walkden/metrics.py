import numpy as np, pandas as pd
import stage67_figures as s
s.OUT_DIR="./figures"
grid, fut = s.build_dataset()
slp, shape, fut0, da, imb, act = s.load_inputs()
L=grid.portfolio_mwh; A=grid.total_actual_mwh; P=grid.hpfc_eur_mwh; DA=grid.day_ahead_price_eur_mwh; IMB=grid.imbalance_price_eur_mwh
loc=grid.timestamp_local
print("N",len(grid),"peak",grid.is_peak.sum(), "NaN", grid.isna().sum().sum())
# Stage1
act['timestamp_utc']=pd.to_datetime(act.timestamp_utc,utc=True)
for p,k in [("HB",35),("GB",6),("LB",2)]:
    f=slp[f"{p.lower()}_normalized_kwh"].sum()*k/1000; r=act[f"{p.lower()}_actual_mwh"].sum()
    lp=slp[f"{p.lower()}_normalized_kwh"]*k/1000
    print(p, round(f,3), round(r,1), "avgMW",round(lp.mean()*4,3),"maxMW",round(lp.max()*4,3))
print("total MW avg",L.mean()*4, "max", L.max()*4, "min", L.min()*4, "maxtime", loc[L.idxmax()], "mintime", loc[L.idxmin()])
print("peak share of energy", L[grid.is_peak==1].sum()/L.sum(), "peak share of intervals", grid.is_peak.mean())
mon=grid.groupby(loc.dt.month).agg(L=("portfolio_mwh","sum"),A=("total_actual_mwh","sum"),DA=("day_ahead_price_eur_mwh","mean"),H=("hpfc_eur_mwh","mean"))
print(mon.round(1))
# hourly shape weekday HB vs GB
g=slp.copy(); g['h']=g.timestamp_local if False else pd.to_datetime(g.timestamp_utc,utc=True).dt.tz_convert("Europe/Berlin").dt.hour
for c,k in [("hb",35),("gb",6),("lb",2)]:
    hh=(g.groupby('h')[f"{c}_normalized_kwh"].mean()*k/1000*4)
    print(c,"hourly MW argmax",hh.idxmax(),round(hh.max(),2),"argmin",hh.idxmin(),round(hh.min(),2))
wk=grid.groupby(loc.dt.dayofweek>=5).portfolio_mwh.mean()*4; print("weekday/weekend MW",wk.round(3).to_dict())
# value per MWh of load
print("load-weighted HPFC",(L*P).sum()/L.sum(), "time avg HPFC", P.mean())
print("load-weighted DA",(L*DA).sum()/L.sum(), "time avg DA", DA.mean())
# HPFC reconciliation
def per(period):
    r=fut0[fut0.delivery_period.astype(str)==period].iloc[0]
    st=pd.Timestamp(r.delivery_start).tz_localize("Europe/Berlin"); en=pd.Timestamp(r.delivery_end_exclusive).tz_localize("Europe/Berlin")
    return (loc>=st)&(loc<en)
rows=[]
for period in ["M01","M02","M03","Q2","Q3","Q4","CAL","Q1"]:
    m=per(period); pk=m&(grid.is_peak==1)
    b=s.futures_price(fut0,period,"BASE"); p_=s.futures_price(fut0,period,"PEAK")
    nall=m.sum(); npk=pk.sum(); off=(b*nall-p_*npk)/(nall-npk)
    rows.append(dict(period=period,Nall=nall,Npk=npk,base=b,peak=p_,off=round(off,2),hb=round(P[m].mean(),3),hp=round(P[pk].mean(),3),ho=round(P[m&(grid.is_peak==0)].mean(),3),db=round(P[m].mean()-b,4),dp=round(P[pk].mean()-p_,4)))
print(pd.DataFrame(rows).to_string())
print(fut0[fut0.load_type=="BASE"][["delivery_period","price_eur_mwh","market_activity"]].to_string())
print(fut0[fut0.load_type=="PEAK"][["delivery_period","price_eur_mwh","market_activity"]].to_string())
print("min HPFC",P.min(),"max",P.max())
grid.to_pickle("grid.pkl")
