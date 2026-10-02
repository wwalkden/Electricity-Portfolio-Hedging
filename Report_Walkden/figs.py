import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt, matplotlib.dates as mdates
plt.rcParams.update({"font.family":"serif","font.size":9,"axes.spines.top":False,"axes.spines.right":False,"axes.titlesize":9.5,"legend.fontsize":8,"figure.dpi":200})
NAVY,TEAL,AMBER,GREY,RED="#16324F","#2E9D93","#E8963A","#8B97A5","#C0392B"
g=pd.read_pickle("grid3.pkl"); loc=g.timestamp_local.dt.tz_localize(None); OUT="/home/claude/report/figures/"
slp=pd.read_csv("slp_profiles.csv"); slp["ts"]=pd.to_datetime(slp.timestamp_utc,utc=True).dt.tz_convert("Europe/Berlin")
act=pd.read_csv("actual_portfolio_load.csv")
# F1 portfolio
fig,ax=plt.subplots(1,2,figsize=(7.2,2.6))
wd=slp.ts.dt.dayofweek<5; tod=slp.ts.dt.hour+slp.ts.dt.minute/60
prof={}
for c,k,lab,col in [("hb",35,"HB (households)",NAVY),("gb",6,"GB (commercial)",TEAL),("lb",2,"LB (agriculture)",AMBER)]:
    prof[lab]=(slp[f"{c}_normalized_kwh"]*k/1000*4)[wd].groupby(tod[wd]).mean()
x=prof["HB (households)"].index
ax[0].stackplot(x,*prof.values(),labels=list(prof.keys()),colors=[NAVY,TEAL,AMBER],alpha=.85)
ax[0].axvspan(8,20,color="grey",alpha=.08); ax[0].text(14,7.0,"Peak window 08–20",ha="center",fontsize=7,color="dimgray"); ax[0].set_ylim(0,7.6)
ax[0].set_xlim(0,24); ax[0].set_xticks(range(0,25,4)); ax[0].set_xlabel("Local time (h), weekdays"); ax[0].set_ylabel("Average load (MW)")
ax[0].set_title("(a) Average weekday profile by customer group",loc="left"); ax[0].legend(loc="upper left",frameon=False,fontsize=7)
m=loc.dt.month; fm=g.portfolio_mwh.groupby(m).sum(); am=g.total_actual_mwh.groupby(m).sum()
xx=np.arange(1,13); ax[1].bar(xx-.2,fm,.4,color=NAVY,label="Forecast $L$"); ax[1].bar(xx+.2,am,.4,color=GREY,label="Realised $A$")
ax[1].set_xticks(xx); ax[1].set_xlabel("Month 2024"); ax[1].set_ylabel("Energy (MWh)"); ax[1].set_ylim(2500,4500)
ax[1].set_title("(b) Monthly portfolio energy",loc="left"); ax[1].legend(frameon=False)
plt.tight_layout(); plt.savefig(OUT+"fig1_portfolio.pdf"); plt.close()
# F2 HPFC
fig,ax=plt.subplots(1,2,figsize=(7.2,2.6),gridspec_kw={"width_ratios":[1.6,1]})
d=loc.dt.floor("D"); hd=g.hpfc_eur_mwh.groupby(d).mean(); dd=g.day_ahead_price_eur_mwh.groupby(d).mean()
ax[0].plot(dd.index,dd,color=GREY,lw=.8,label="Realised Day-Ahead (daily mean)")
ax[0].plot(hd.index,hd,color=NAVY,lw=1.1,label="HPFC (daily mean)")
blocks=[("M01","2024-01-01","2024-02-01",75.32),("M02","2024-02-01","2024-03-01",60.09),("M03","2024-03-01","2024-04-01",63.45),("Q2","2024-04-01","2024-07-01",66.23),("Q3","2024-07-01","2024-10-01",74.74),("Q4","2024-10-01","2025-01-01",101.39)]
for i,(n,a,b,p) in enumerate(blocks): ax[0].hlines(p,pd.Timestamp(a),pd.Timestamp(b),color=AMBER,lw=1.6,label="Base quote (calibration block)" if i==0 else None)
ax[0].set_ylabel("EUR/MWh"); ax[0].set_ylim(-20,420); ax[0].legend(frameon=False,loc="upper left"); ax[0].set_title("(a) HPFC, block quotes and realised prices, 2024",loc="left")
ax[0].xaxis.set_major_formatter(mdates.DateFormatter("%b"))
wk=(loc>="2024-01-15")&(loc<"2024-01-22")
ax[1].plot(loc[wk],g.hpfc_eur_mwh[wk],color=NAVY,lw=1); ax[1].plot(loc[wk],g.day_ahead_price_eur_mwh[wk],color=GREY,lw=.8)
ax[1].axhline(88.68,color=AMBER,ls="--",lw=.9,label="M01 Peak 88.68"); ax[1].axhline(67.44,color=TEAL,ls="--",lw=.9,label="M01 Off-Peak 67.44"); ax[1].legend(frameon=False,fontsize=6.5,loc="upper right")

ax[1].xaxis.set_major_formatter(mdates.DateFormatter("%a")); ax[1].set_title("(b) One week, 15–21 Jan 2024",loc="left")
plt.tight_layout(); plt.savefig(OUT+"fig2_hpfc.pdf"); plt.close()
# F3 hedge shape week Jan + Dec
fig,ax=plt.subplots(1,2,figsize=(7.2,2.6),sharey=True)
for a,(s0,s1,t) in zip(ax,[("2024-01-15","2024-01-22","(a) Winter week, 15–21 Jan"),("2024-07-15","2024-07-22","(b) Summer week, 15–21 Jul")]):
    w=(loc>=s0)&(loc<s1)
    a.plot(loc[w],g.portfolio_mwh[w]*4,color=NAVY,lw=1,label="Forecast load $L$")
    a.plot(loc[w],g.hedge_coarse[w]*4,color=TEAL,lw=1.2,label="COARSE_CAL hedge")
    a.plot(loc[w],g.hedge_gran[w]*4,color=AMBER,lw=1.2,ls="--",label="GRANULAR hedge")
    a.xaxis.set_major_formatter(mdates.DateFormatter("%a")); a.set_title(t,loc="left")
ax[0].set_ylabel("MW"); ax[0].legend(frameon=False,loc="upper left",ncol=1)
plt.tight_layout(); plt.savefig(OUT+"fig3_hedge_shape.pdf"); plt.close()
# F4 imbalance premium concentration
I=g.imb_mwh; prem=(I*(g.imbalance_price_eur_mwh-g.day_ahead_price_eur_mwh)).sort_values(ascending=False).to_numpy()
fig,ax=plt.subplots(1,2,figsize=(7.2,2.5))
ax[0].plot(np.arange(1,len(prem)+1)/len(prem)*100,np.cumsum(prem)/1000,color=NAVY)
ax[0].axhline(prem.sum()/1000,color=GREY,ls="--",lw=.8); ax[0].text(60,prem.sum()/1000+1,f"Annual total {prem.sum()/1000:.1f}k",fontsize=7,color="dimgray")
ax[0].set_xscale("log"); ax[0].set_xlabel("Share of quarter-hours, sorted by premium (%, log)"); ax[0].set_ylabel("Cumulative premium (kEUR)")
ax[0].set_title("(a) Concentration of the imbalance premium",loc="left")
for lab,s,col in [("Day-Ahead",g.day_ahead_price_eur_mwh,GREY),("reBAP",g.imbalance_price_eur_mwh,RED)]:
    v=np.sort(s.to_numpy()); n=len(v); q=np.arange(1,n+1)/n
    ax[1].plot(v[q>0.99],q[q>0.99]*100,color=col,label=lab)
ax[1].set_xscale("symlog",linthresh=100); ax[1].set_xlabel("Price (EUR/MWh, symlog)"); ax[1].set_ylabel("Percentile")
ax[1].set_title("(b) Upper 1% of the price distributions",loc="left"); ax[1].legend(frameon=False)
plt.tight_layout(); plt.savefig(OUT+"fig4_imbalance.pdf"); plt.close()
# residual by hour (text)
wd=loc.dt.dayofweek<5
print((g.res_coarse*4)[wd].groupby(loc.dt.hour[wd]).mean().round(2).to_dict())
neg=(g.day_ahead_price_eur_mwh<0)
for k,R in [("C",g.res_coarse),("G",g.res_gran)]:
    m=neg&(R<0); print(k,"long at negative DA MWh",round(R[m].sum(),1),"cost",round((R[m]*g.day_ahead_price_eur_mwh[m]).sum()))
