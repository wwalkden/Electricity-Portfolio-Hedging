import numpy as np, pandas as pd, stage67_figures as s
grid=pd.read_pickle("grid.pkl"); fut=pd.read_csv("futures_prices.csv")
L=grid.portfolio_mwh; A=grid.total_actual_mwh; P=grid.hpfc_eur_mwh; DA=grid.day_ahead_price_eur_mwh; IMB=grid.imbalance_price_eur_mwh; loc=grid.timestamp_local; pk=grid.is_peak
_,(cb,cp),gpos = s.add_hedges(grid.copy(), fut)
print("COARSE",cb,cp)
for k,v in gpos.items(): print(k,v)
for name,hcol,blocks in [("C","hedge_coarse",None),("G","hedge_gran","gperiod")]:
    H=grid[hcol]; R=L-H
    print(name,"notional",H.sum(),"Hval",(H*P).sum(),"Lval",(L*P).sum(),"VNerr",(H*P).sum()-(L*P).sum(),"RMSE",np.sqrt((R**2).mean()),"absR",R.abs().sum(),"Rpos",R[R>0].sum(),"Rneg",R[R<0].sum(), "netR",R.sum())
    if blocks:
        for b,gg in grid.groupby("gperiod"):
            Hb=gg[hcol]; print("  ",b,"notional",round(Hb.sum(),1),"L",round(gg.portfolio_mwh.sum(),1),"VNerr",round((Hb*gg.hpfc_eur_mwh).sum()-(gg.portfolio_mwh*gg.hpfc_eur_mwh).sum(),6), "Hval",round((Hb*gg.hpfc_eur_mwh).sum()))
    # residual by peak/off
    print("  R peak",R[pk==1].sum(),"R off",R[pk==0].sum())
print("UNH absR",L.abs().sum(),"RMSE",np.sqrt((L**2).mean()))
# Stage 4 costs
for name,f,r,h in [("U",None,"da_unh",None),("C","fut_coarse","da_coarse","hedge_coarse"),("G","fut_gran","da_gran","hedge_gran")]:
    Cf=grid[f].sum() if f else 0; Cr=grid[r].sum(); Cfc=Cf+Cr
    if h:
        H=grid[h]; Pi=(H*DA).sum()-Cf
    else: Pi=0
    alt=(L*DA).sum()-Pi
    print(name,"Cfut",round(Cf,2),"Cres",round(Cr,2),"Cforecast",round(Cfc,2),"alt",round(alt,2),"diff",Cfc-alt,"Pi",round(Pi,2), "Cfin", round(Cfc+grid.imb.sum(),2))
I=grid.imb_mwh
print("Cimb",grid.imb.sum(),"premium",(I*(IMB-DA)).sum(),"I DA part",(I*DA).sum())
print("I pos",I[I>0].sum(),"neg",I[I<0].sum(),"net",I.sum(),"abs",I.abs().sum(), "cnt pos",(I>0).sum(),"neg",(I<0).sum())
print("cost of short (I>0) at reBAP",(I[I>0]*IMB[I>0]).sum(),"long",(I[I<0]*IMB[I<0]).sum())
prem=I*(IMB-DA); 
srt=prem.sort_values(ascending=False); n1=int(len(prem)*0.01)
print("premium worst 1% sum",srt.iloc[:n1].sum(),"of total",prem.sum(), "top10",srt.iloc[:10].sum())
print("reBAP stats",IMB.describe().round(2).to_dict(),"DA",DA.describe().round(2).to_dict())
print("neg DA count",(DA<0).sum())
print("imb |I| quantiles",I.abs().quantile([.5,.9,.99]).round(4).to_dict(), "max",I.max(),I.min())
# corr I with IMB
print("corr(I,reBAP-DA)",np.corrcoef(I,IMB-DA)[0,1])
grid["prem"]=prem
mp={k:s.monthly_price(grid,c) for k,c in [("U","cost_unh"),("C","cost_coarse"),("G","cost_gran")]}
print(pd.DataFrame(mp).round(2))
for k,v in mp.items(): print(k,"std",round(v.std(),3),"std0",round(v.std(ddof=0),3),"range",round(v.max()-v.min(),2),"max",v.idxmax(),"min",v.idxmin())
dp={k:s.daily_price(grid,c) for k,c in [("U","cost_unh"),("C","cost_coarse"),("G","cost_gran")]}
def es(x,q): return x[x>=x.quantile(q)].mean()
for k,v in dp.items(): print(k,"mean",round(v.mean(),2),"VaR95",round(v.quantile(.95),2),"ES95",round(es(v,.95),2),"ES99",round(es(v,.99),2),"std",round(v.std(),2),"max",round(v.max(),2),v.idxmax())
# daily cost EUR ES
dc={k:grid.groupby(loc.dt.date)[c].sum() for k,c in [("U","cost_unh"),("C","cost_coarse"),("G","cost_gran")]}
for k,v in dc.items(): print(k,"daily EUR mean",round(v.mean()),"ES95",round(es(v,.95)),"ES99",round(es(v,.99)),"max",round(v.max()))
load=A.sum()
for k,c in [("U","cost_unh"),("C","cost_coarse"),("G","cost_gran")]: print(k,"avg price",grid[c].sum()/load)
# quarterly hedge MWh comparison Q4
for k,h in [("C","hedge_coarse"),("G","hedge_gran")]:
    print(k,"Q4 hedge MWh",grid.loc[loc.dt.month>=10,h].sum(), "Q4 L",L[loc.dt.month>=10].sum())
grid.to_pickle("grid2.pkl")
