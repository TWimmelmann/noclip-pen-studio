import numpy as np, cv2
from scipy.ndimage import gaussian_filter1d
F32=np.float32

def _largest(mask, minpx=400, single=False):
    n,lab,st,_=cv2.connectedComponentsWithStats(mask.astype(np.uint8),8)
    out=np.zeros(mask.shape,np.uint8)
    if n<2: return out
    if single:
        out[lab==1+int(np.argmax(st[1:,4]))]=1; return out
    for i in range(1,n):
        if st[i,4]>=minpx: out[lab==i]=1
    return out

def fill_holes(m):
    ff=m.copy(); h,w=ff.shape; z=np.zeros((h+2,w+2),np.uint8)
    cv2.floodFill(ff,z,(0,0),1)
    return (m|(1-ff)).astype(np.uint8)


def clip_to_core(obj, img, bg, min_diff):
    """Trim anything wider than the object's own solid core.

    A cast shadow lying against the object survives every threshold because it is
    connected to it. But the object here is a pen: at each point along its axis it
    cannot be wider than the part of it that is unmistakably solid. Build that
    envelope from a strict threshold and clip the mask to it."""
    strong=(np.abs(img-bg[None,None,:]).sum(-1)>max(min_diff*2.5,110)).astype(np.uint8)
    strong=cv2.morphologyEx(strong,cv2.MORPH_OPEN,np.ones((5,5),np.uint8))
    strong=_largest(strong,single=True)&obj
    if strong.sum()<500: return obj
    ys,xs=np.nonzero(strong)
    P=np.stack([xs,ys],1).astype(F32); c=P.mean(0)
    _,_,V=np.linalg.svd(P-c,full_matrices=False); d=V[0].astype(F32)
    dp=np.array([-d[1],d[0]],F32)
    H,W=obj.shape
    gy,gx=np.mgrid[0:H,0:W].astype(F32)
    t=(gx-c[0])*d[0]+(gy-c[1])*d[1]; n=(gx-c[0])*dp[0]+(gy-c[1])*dp[1]
    sb=strong.astype(bool)
    tb=np.round(t).astype(np.int32); off=int(-tb[sb].min()); nb=tb+off
    NB=int(nb[sb].max())+1
    BIG=F32(1e9); lo=np.full(NB,BIG,F32); hi=np.full(NB,-BIG,F32)
    np.minimum.at(lo,nb[sb],n[sb]); np.maximum.at(hi,nb[sb],n[sb])
    ok=np.abs(lo)<1e8
    if ok.sum()<8: return obj
    idx=np.arange(NB)
    lo=np.interp(idx,idx[ok],lo[ok]); hi=np.interp(idx,idx[ok],hi[ok])
    lo=cv2.GaussianBlur(lo.astype(F32).reshape(-1,1),(0,0),9).ravel()
    hi=cv2.GaussianBlur(hi.astype(F32).reshape(-1,1),(0,0),9).ravel()
    MARGIN=5.0
    i=np.clip(nb,0,NB-1)
    inside=(n>=lo[i]-MARGIN)&(n<=hi[i]+MARGIN)&(tb+off>=-4)&(tb+off<=NB+3)
    return (obj.astype(bool)&inside).astype(np.uint8)


def object_matte(img, bg, min_diff=6, smooth=1.4, edge=0.60):
    """Geometric sub-pixel coverage matte: immune to specular rim-light that
    happens to match the background."""
    BG=bg[None,None,:]
    rough=(np.abs(img-BG).sum(-1)>min_diff).astype(np.uint8)
    rough=cv2.morphologyEx(rough,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    rough=cv2.morphologyEx(rough,cv2.MORPH_CLOSE,np.ones((9,9),np.uint8))
    obj=fill_holes(_largest(rough,single=True))
    obj=clip_to_core(obj,img,bg,min_diff)
    # smooth the silhouette: removes notches where the object matches the bg
    obj=(cv2.GaussianBlur(obj.astype(F32),(0,0),smooth)>0.5).astype(np.uint8)
    obj=fill_holes(_largest(obj,single=True))
    # true sub-pixel coverage: smooth the contour, rasterise at 4x, box-downsample
    cov=contour_coverage(obj, ss=4, csig=1.2, soften=edge)
    core=cv2.erode(obj,np.ones((5,5),np.uint8))
    F=cv2.inpaint(img.astype(np.uint8),(1-core).astype(np.uint8),9,cv2.INPAINT_TELEA).astype(F32)
    F=np.where(core[...,None].astype(bool),img,F)
    return cov.astype(F32), F, obj, core

def contour_coverage(obj, ss=4, csig=1.2, soften=0.85):
    h,w=obj.shape
    cnts,_=cv2.findContours(obj,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
    big=np.zeros((h*ss,w*ss),np.uint8)
    for c in cnts:
        p=c[:,0,:].astype(np.float64)
        if len(p)<24: continue
        p[:,0]=gaussian_filter1d(p[:,0],csig,mode='wrap')
        p[:,1]=gaussian_filter1d(p[:,1],csig,mode='wrap')
        q=np.round((p+0.5)*ss).astype(np.int32)
        cv2.fillPoly(big,[q],1)
    cov=cv2.resize(big.astype(F32),(w,h),interpolation=cv2.INTER_AREA)
    if soften>0: cov=cv2.GaussianBlur(cov,(0,0),soften)
    return np.clip(cov,0,1)

def hybrid_fg(img, F, cov, bg=None):
    """Unmatted foreground. At a partly covered pixel the photo shows
    a*F + (1-a)*BG; storing that as straight-alpha RGB re-adds the backdrop on
    compositing and rims dark objects in white. Invert the mix instead, and blend
    to the inpainted interior where alpha is too small to divide by safely."""
    if bg is None: bg=np.array([255.,255.,255.],F32)
    a=np.clip(cov,1e-3,1.0)[...,None]
    un=(img-(1.0-a)*bg[None,None,:])/a
    # the interior colour carried outward by the inpaint is what the surface
    # actually looks like a pixel or two in; the edge cannot legitimately be much
    # brighter than that, so cap the inversion there rather than let its error
    # through as a rim
    un=np.minimum(un,F*1.12+8.0)
    w=np.clip((cov-0.45)/0.30,0,1)[...,None]
    return np.clip(un*w+F*(1-w),0,255).astype(F32)
