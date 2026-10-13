from __future__ import annotations
import numpy as np
import pandas as pd

P = {
    "N":60,"ATRN":14,"VOLN":20,"ZTH":1.5,"RVVAC":1.2,"RVTH":1.5,
    "RVCAP":3.0,"MVCAP":4.0,"DTH":0.25,"ATH":0.10,"CTH":0.10,
    "COOL":3,"WDR":0.50,"WDB":0.25,"WCV":0.25,
}

def tdx_sma(x: pd.Series, n: int, m: int = 1) -> pd.Series:
    a=x.astype(float).to_numpy(); out=np.full(len(a),np.nan); last=np.nan
    for i,v in enumerate(a):
        if np.isnan(v):
            out[i]=last; continue
        last=v if np.isnan(last) else (m*v+(n-m)*last)/n
        out[i]=last
    return pd.Series(out,index=x.index)

def cnt(x: pd.Series,n:int)->pd.Series:
    return x.astype(int).rolling(n,min_periods=1).sum()

def calc(df: pd.DataFrame, **kw) -> pd.DataFrame:
    p=P|kw
    o,h,l,c,v=(df[k].astype(float) for k in ["open","high","low","close","volume"])
    pc=c.shift(1)
    tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    atrb=tdx_sma(tr,p["ATRN"]).shift(1)
    trok=atrb>0.0001
    mov=pd.Series(np.where(trok,tr/atrb,0),index=df.index)
    vb=v.rolling(p["VOLN"],min_periods=p["VOLN"]).mean().shift(1)
    vok=vb>0
    rv=pd.Series(np.where(vok,v/vb,1),index=df.index)
    xf=rv.clip(upper=p["RVCAP"]); yf=mov.clip(upper=p["MVCAP"])
    x=xf.shift(1); y=yf.shift(1); n=p["N"]
    mx=x.rolling(n,min_periods=n).mean(); my=y.rolling(n,min_periods=n).mean()
    cxy=(x*y).rolling(n,min_periods=n).mean()-mx*my
    vx=(x*x).rolling(n,min_periods=n).mean()-mx*mx
    vy=(y*y).rolling(n,min_periods=n).mean()-my*my
    k=pd.Series(np.where(vx>0.0001,np.maximum(cxy/vx,0),0),index=df.index)
    b=my-k*mx
    ex=np.maximum(b+k*xf,0); res=mov-ex
    rm=res.shift(1).rolling(n,min_periods=n).mean()
    rs=res.shift(1).rolling(n,min_periods=n).std(ddof=1)
    zr=pd.Series(np.where(rs>0.0001,(res-rm)/rs,0),index=df.index)
    rho=pd.Series(np.where((vx>0.0001)&(vy>0.0001),cxy/np.sqrt(vx*vy),0),index=df.index)
    wn=2*n+max(p["ATRN"],p["VOLN"])+5
    valid=(np.arange(1,len(df)+1)>wn)&trok.to_numpy()&vok.to_numpy()&(rs.to_numpy()>0.0001)
    z=pd.Series(np.where(valid,zr,0),index=df.index)
    trb=np.maximum(tr,0.001)
    dr=(c-pc)/trb; db=(c-o)/trb
    clv=pd.Series(np.where(h>l,(2*c-h-l)/(h-l),0),index=df.index)
    ws=max(p["WDR"]+p["WDB"]+p["WCV"],0.0001)
    d=(p["WDR"]*dr+p["WDB"]*db+p["WCV"]*clv)/ws
    eu0=pd.Series(valid,index=df.index)&(z>p["ZTH"])&(d>p["DTH"])&(rv>=p["RVVAC"])
    vu0=pd.Series(valid,index=df.index)&(z>p["ZTH"])&(d>p["DTH"])&(rv<p["RVVAC"])
    abu0=pd.Series(valid,index=df.index)&(z<-p["ZTH"])&(rv>p["RVTH"])&(d>p["ATH"])&(clv>p["CTH"])
    def evt(s): return s&(cnt(s.shift(1).fillna(False),p["COOL"])==0)
    return pd.DataFrame({
        "MOV":mov,"RVRAW":rv,"EXPECT":ex,"RES":res,"Z":z,"DIR":d,"CLV":clv,
        "RHO":rho,"R2RAW":rho*rho,"R2POS":rho.clip(lower=0)**2,
        "EU0":eu0,"VU0":vu0,"ABU0":abu0,"EU":evt(eu0),"VU":evt(vu0),"ABU":evt(abu0),
    })
