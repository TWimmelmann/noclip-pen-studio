import numpy as np, cv2, json
from PIL import Image
from matte import object_matte, hybrid_fg, fill_holes, _largest
F32=np.float32

def segment(path, logo_erase=False):
    img=np.asarray(Image.open(path).convert('RGB')).astype(F32)
    H,W=img.shape[:2]
    BG=np.median(np.concatenate([img[:30,:30].reshape(-1,3),img[-30:,-30:].reshape(-1,3)]),0).astype(F32)
    cov,F,obj,core=object_matte(img,BG,min_diff=45)
    FG=hybrid_fg(img,F,cov,BG)
    objb=obj.astype(bool)
    sat=FG.max(-1)-FG.min(-1)
    paint=cv2.morphologyEx(((sat>22)&objb).astype(np.uint8),cv2.MORPH_CLOSE,np.ones((9,9),np.uint8))
    paint=cv2.morphologyEx(paint,cv2.MORPH_OPEN,np.ones((5,5),np.uint8))
    n,lab,st,_=cv2.connectedComponentsWithStats(paint,8)
    order=sorted([i for i in range(1,n) if st[i,4]>400],key=lambda i:-st[i,4])
    if not order: raise RuntimeError('no painted part found in '+path)
    barrel=fill_holes((lab==order[0]).astype(np.uint8))
    dome  =fill_holes((lab==order[1]).astype(np.uint8)) if len(order)>1 else np.zeros_like(barrel)
    metal =cv2.morphologyEx((objb&~barrel.astype(bool)&~dome.astype(bool)).astype(np.uint8),
                            cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    return dict(img=img,BG=BG,cov=cov,F=F,obj=obj,core=core,FG=FG,
                barrel=barrel,dome=dome,metal=metal,H=H,W=W)

def axis_of(mask):
    ys,xs=np.nonzero(cv2.erode(mask,np.ones((7,7),np.uint8)))
    P=np.stack([xs,ys],1).astype(F32); c=P.mean(0)
    _,_,V=np.linalg.svd(P-c,full_matrices=False); d=V[0].astype(F32)
    if d[1]>0: d=-d                       # +d points toward the pen top
    return c,d,np.array([-d[1],d[0]],F32)

def tn_grid(shape,c,d,dp):
    H,W=shape
    gy,gx=np.mgrid[0:H,0:W].astype(F32)
    return ((gx-c[0])*d[0]+(gy-c[1])*d[1], (gx-c[0])*dp[0]+(gy-c[1])*dp[1])

def barrel_u(seg,c,d,dp):
    """signed across-barrel coordinate in [-1,1] over the barrel."""
    t,n=tn_grid(seg['cov'].shape,c,d,dp)
    bm=seg['barrel'].astype(bool)&cv2.erode(seg['obj'],np.ones((5,5),np.uint8)).astype(bool)
    tb=np.round(t).astype(np.int32); off=int(-tb[bm].min()); nb=tb+off
    NB=int(nb[bm].max())+1
    BIG=F32(1e9); lo=np.full(NB,BIG,F32); hi=np.full(NB,-BIG,F32)
    np.minimum.at(lo,nb[bm],n[bm]); np.maximum.at(hi,nb[bm],n[bm])
    def sm(v):
        ok=np.abs(v)<1e8; idx=np.arange(len(v))
        return cv2.GaussianBlur(np.interp(idx,idx[ok],v[ok]).astype(F32).reshape(-1,1),(0,0),25).ravel()
    lo,hi=sm(lo),sm(hi); i=np.clip(nb,0,NB-1)
    u=np.clip((2*n-lo[i]-hi[i])/np.maximum(hi[i]-lo[i],1e-3),-1,1)
    return u,t,n,bm

def profile(seg,bins=41,trim=0.12):
    """mean barrel RGB as a function of the across-barrel coordinate u."""
    c,d,dp=axis_of(seg['barrel'])
    u,t,n,bm=barrel_u(seg,c,d,dp)
    lo,hi=np.percentile(t[bm],[trim*100,(1-trim)*100])
    sel=bm&(t>lo)&(t<hi)&(np.abs(u)<0.97)
    idx=np.clip(((u[sel]+1)/2*bins).astype(int),0,bins-1)
    out=np.zeros((bins,3)); cnt=np.zeros(bins)
    for ch in range(3):
        np.add.at(out[:,ch],idx,seg['FG'][...,ch][sel])
    np.add.at(cnt,idx,1)
    return out/np.maximum(cnt,1)[:,None], cnt

def band_profile(path, lo_frac=0.22, hi_frac=0.76, bins=41):
    """Cross-barrel RGB profile taken from a purely geometric mid-barrel band —
    works for black pens where saturation cannot separate lacquer from metal."""
    img=np.asarray(Image.open(path).convert('RGB')).astype(F32)
    BG=np.median(np.concatenate([img[:30,:30].reshape(-1,3),img[-30:,-30:].reshape(-1,3)]),0).astype(F32)
    cov,F,obj,core=object_matte(img,BG,min_diff=45)
    FG=hybrid_fg(img,F,cov,BG)
    c,d,dp=axis_of(obj)
    t,n=tn_grid(cov.shape,c,d,dp)
    ob=cv2.erode(obj,np.ones((5,5),np.uint8)).astype(bool)
    t0,t1=t[ob].min(),t[ob].max(); Ln=t1-t0
    band=ob&(t>t0+lo_frac*Ln)&(t<t0+hi_frac*Ln)
    tb=np.round(t).astype(np.int32); off=int(-tb[band].min()); nb=tb+off
    NB=int(nb[band].max())+1
    BIG=F32(1e9); plo=np.full(NB,BIG,F32); phi=np.full(NB,-BIG,F32)
    np.minimum.at(plo,nb[band],n[band]); np.maximum.at(phi,nb[band],n[band])
    ok=np.abs(plo)<1e8; idx=np.arange(NB)
    plo=np.interp(idx,idx[ok],plo[ok]); phi=np.interp(idx,idx[ok],phi[ok])
    i=np.clip(nb,0,NB-1)
    u=np.clip((2*n-plo[i]-phi[i])/np.maximum(phi[i]-plo[i],1e-3),-1,1)
    sel=band&(np.abs(u)<0.96)
    bi=np.clip(((u[sel]+1)/2*bins).astype(int),0,bins-1)
    out=np.zeros((bins,3)); cnt=np.zeros(bins)
    for ch in range(3): np.add.at(out[:,ch],bi,FG[...,ch][sel])
    np.add.at(cnt,bi,1)
    return out/np.maximum(cnt,1)[:,None], float(phi.mean()-plo.mean())
