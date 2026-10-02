import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt, matplotlib.dates as mdates
plt.rcParams.update({"font.family":"serif","font.size":9,"axes.spines.top":False,"axes.spines.right":False,"axes.titlesize":9.5,"legend.fontsize":7.5,"figure.dpi":200})
NAVY,TEAL,AMBER,GREY,RED,PURP="#16324F","#2E9D93","#E8963A","#8B97A5","#C0392B","#7B5EA7"
g=pd.read_pickle("grid3.pkl"); loc=g.timestamp_local.dt.tz_localize(None); OUT="/home/claude/report/figures/"
m=loc.dt.month; A=g.total_actual_mwh.groupby(m).sum(); L=g.portfolio_mwh.groupby(m).sum(); P=g.hpfc_eur_mwh
fig,ax=plt.subplots(1,2,figsize=(7.2,3.2))
x=np.arange(1,13)
for k,c,f,R,col,lab in [("U","cost_unh",None,g.portfolio_mwh,GREY,"UNHEDGED"),("C","cost_coarse","fut_coarse",g.res_coarse,TEAL,"COARSE_CAL"),("G","cost_gran","fut_gran",g.res_gran,AMBER,"GRANULAR")]:
    real=g[c].groupby(m).sum()/A
    ea=((g[f] if f else 0)+R*P).groupby(m).sum()/L
    ax[0].plot(x,real,color=col,lw=1.6,marker="o",ms=3,label=f"{lab} realised")
    ax[0].plot(x,ea,color=col,lw=1,ls=":",label=f"{lab} locked on 29 Sep 2023")
ax[0].set_xticks(x); ax[0].set_xlabel("Month 2024"); ax[0].set_ylabel("EUR/MWh"); ax[0].set_title("(a) Monthly procurement price: realised vs. locked",loc="left")
ax[0].legend(frameon=False,fontsize=6.2,ncol=2,loc="upper center",bbox_to_anchor=(0.5,-0.2)); ax[0].set_xlabel("")
es=lambda s,q:s[s>=s.quantile(q)].mean()
d=loc.dt.date; vals={}
for k,R in [("COARSE_CAL",g.res_coarse),("QUARTER_ONLY",g.res_q),("GRANULAR",g.res_gran)]:
    s=(R*(g.day_ahead_price_eur_mwh-P)).groupby(d).sum(); vals[k]=[s.quantile(.95),es(s,.95),es(s,.99),s.max()]
xx=np.arange(4); wdt=.26
for off,(k,col) in zip([-wdt,0,wdt],[("COARSE_CAL",TEAL),("QUARTER_ONLY",PURP),("GRANULAR",AMBER)]):
    b=ax[1].bar(xx+off,vals[k],wdt,color=col,label=k)
    for bi in b: ax[1].text(bi.get_x()+bi.get_width()/2,bi.get_height()+80,f"{bi.get_height():,.0f}",ha="center",va="bottom",fontsize=6,rotation=90)
ax[1].set_xticks(xx); ax[1].set_xticklabels(["VaR 95%","ES 95%","ES 99%","Worst day"]); ax[1].set_ylabel("EUR per day")
ax[1].set_title("(b) Daily residual surprise, tail",loc="left"); ax[1].legend(frameon=False,loc="upper left"); ax[1].set_ylim(0,6200)
plt.tight_layout(); plt.savefig(OUT+"fig5_comparison.pdf"); plt.close()
# event
win=(loc>="2024-12-10")&(loc<"2024-12-14"); t=loc[win]
fig,ax=plt.subplots(2,1,figsize=(7.2,3.9),sharex=True,gridspec_kw={"height_ratios":[1,1.3]})
ax[0].plot(t,g.day_ahead_price_eur_mwh[win],color=NAVY,lw=1.1,label="Day-Ahead")
ax[0].plot(t,g.hpfc_eur_mwh[win],color=GREY,lw=1,ls="--",label="HPFC")
ax[0].set_ylabel("EUR/MWh"); ax[0].legend(frameon=False,loc="upper left"); ax[0].set_title("(a) Prices, 10–13 December 2024",loc="left")
for a in ax: a.axvspan(pd.Timestamp("2024-12-11"),pd.Timestamp("2024-12-13"),color=RED,alpha=.06)
ax[1].plot(t,g.portfolio_mwh[win]*4,color=NAVY,lw=1.2,label="Forecast load $L$ (= UNHEDGED residual)")
ax[1].plot(t,g.hedge_coarse[win]*4,color=TEAL,lw=1.3,label="COARSE_CAL hedge")
ax[1].plot(t,g.hedge_gran[win]*4,color=AMBER,lw=1.3,ls="--",label="GRANULAR hedge")
ax[1].plot(t,g.total_actual_mwh[win]*4,color=GREY,lw=.7,label="Actual load $A$")
ax[1].set_ylabel("MW"); ax[1].legend(frameon=False,fontsize=6.5,ncol=2,loc="upper left"); ax[1].set_ylim(0,13)
ax[1].set_title("(b) Load and hedge; the gap between them is the residual bought or sold Day-Ahead",loc="left")
ax[1].xaxis.set_major_locator(mdates.DayLocator()); ax[1].xaxis.set_major_formatter(mdates.DateFormatter("%a %d %b"))
plt.tight_layout(); plt.savefig(OUT+"fig6_event.pdf"); plt.close()
