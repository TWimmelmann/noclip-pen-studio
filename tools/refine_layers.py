"""Efterbehandling af lag-filerne: rene kanter og roligere lak.

Kører på de færdige pen_?1.png-filer (lagene fra build_layers.py) og retter tre
ting, der ses tydeligst på mørke farver:

1. Trappekanter. Skaftet er en ret cylinder, men dækningen (alpha) var rastreret
   i hele pixels, så en næsten lodret kant hoppede 1 px ad gangen. Kanterne
   fittes nu som rette linjer langs aksen, og dækningen genberegnes med
   sub-pixel antialiasing.
2. Lys rand. Fotoets kant blander pennen med den hvide fotobaggrund. I lagene
   ender det som hvidt lys (G) og en lak-dyk (R) i de yderste ~10 px, og på en
   sort eller mørk pen ses det som en grå glorie. Randen trykkes sammen til det
   halve og dæmpes.
3. Bølger i lakken. Rester af JPEG-blokke løber skråt over det diagonale skaft.
   Der glattes langs aksen (hvor lakken er konstant), ikke på tværs.

Brug:  python refine_layers.py ../public
"""
import sys, os, json
import numpy as np, cv2
from PIL import Image
F=np.float32

POSES={
 'v':dict(c=(798.769,757.719),d=(-0.0016657,-0.9999986),crop=(737,107),barrelT=(-496.31,497.72)),
 'd':dict(c=(845.200,787.779),d=(0.4411512,-0.8974328),crop=(520,211),barrelT=(-492.41,484.37)),
}

def refine(folder, tag, P):
    A=np.asarray(Image.open(os.path.join(folder,f'pen_{tag}1.png'))).astype(F)
    B=np.asarray(Image.open(os.path.join(folder,f'pen_{tag}2.png'))).astype(F)
    H,W=A.shape[:2]
    k,s,cov=A[...,0]/200,A[...,1]/255,A[...,2]/255
    wb,wd=B[...,0]/255,B[...,1]/255
    cx,cy=P['c'][0]-P['crop'][0],P['c'][1]-P['crop'][1]
    dx,dy=P['d']; nx,ny=-dy,dx
    gy,gx=np.mgrid[0:H,0:W].astype(F)
    t=(gx-cx)*dx+(gy-cy)*dy; n=(gx-cx)*nx+(gy-cy)*ny
    t0,t1=P['barrelT']

    # ---- 1. straight barrel edges -------------------------------------------
    win=(t>t0+10)&(t<t1-10)
    inside=win&(cov>=0.5)&(wb>0.5)
    tb=np.round(t[inside]).astype(int); nn=n[inside]
    T=np.unique(tb)
    lo=np.array([nn[tb==v].min() for v in T]); hi=np.array([nn[tb==v].max() for v in T])
    def robust_line(x,y):
        m=np.ones(len(x),bool)
        for _ in range(4):
            p=np.polyfit(x[m],y[m],1); r=y-np.polyval(p,x)
            sd=max(np.std(r[m]),0.3); m=np.abs(r)<2.5*sd
        return p
    pl,ph=robust_line(T,lo),robust_line(T,hi)
    LO=np.polyval(pl,t); HI=np.polyval(ph,t)
    # pick the offset that keeps the barrel's area exactly as photographed
    ref=cov[win&(np.abs(n-(LO+HI)/2)<(HI-LO)/2+6)].sum()
    band=win&(np.abs(n-(LO+HI)/2)<(HI-LO)/2+6)
    best=None
    for delta in np.linspace(-1.5,1.5,61):
        c2=np.clip(0.5+np.minimum(n-(LO-delta),(HI+delta)-n),0,1)
        e=abs(c2[band].sum()-ref)
        if best is None or e<best[0]: best=(e,delta)
    delta=best[1]; LO-=delta; HI+=delta
    covB=np.clip(0.5+np.minimum(n-LO,HI-n),0,1)
    # feather in over the last 8 px of the window so the barrel meets the metal
    fe=np.clip(np.minimum(t-(t0+10),(t1-10)-t)/8,0,1)*win
    side=band
    covN=np.where(side,cov*(1-fe)+covB*fe,cov)

    # ---- 2. compress the rim -------------------------------------------------
    D=11.0
    dist=np.minimum(n-LO,HI-n)                       # distance in from the edge
    rim=win&(dist>-1)&(dist<D)
    dd=np.clip(dist,0,D)
    dsrc=2*dd-dd*dd/D                                 # slope 2 at the edge, 0 at D
    lower=(n-LO)<(HI-n)
    nsrc=np.where(lower,LO+dsrc,HI-dsrc)
    mx=(cx+t*dx+nsrc*nx).astype(F); my=(cy+t*dy+nsrc*ny).astype(F)
    kS=cv2.remap(k,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
    sS=cv2.remap(s,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
    # interior reference D px in, same t
    nref=np.where(lower,LO+D,HI-D)
    rx=(cx+t*dx+nref*nx).astype(F); ry=(cy+t*dy+nref*ny).astype(F)
    sR=cv2.remap(s,rx,ry,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
    sS=sR+(sS-sR)*0.6                                 # soft-touch rim is faint
    w=(rim*fe).astype(F)
    k2=k*(1-w)+kS*w; s2=s*(1-w)+sS*w

    # other lacquer edges (stylus dome, barrel ends): damp the white-light rim
    solid=(covN>0.5).astype(np.uint8)
    dt=cv2.distanceTransform(solid,cv2.DIST_L2,3)
    lac=(wd>0.3)|((wb>0.3)&~win)
    damp=np.where(lac,0.55+0.45*np.clip(dt/4,0,1),1).astype(F)
    s2=s2*damp

    # ---- 3. smooth along the axis -------------------------------------------
    sig=8.0; r=int(3*sig)
    yy,xx=np.mgrid[-r:r+1,-r:r+1].astype(F)
    a=xx*dx+yy*dy; b=xx*nx+yy*ny
    K=np.exp(-(a*a)/(2*sig*sig)-(b*b)/(2*0.5*0.5)); K=(K/K.sum()).astype(F)
    core=(win&(dist>2.5)).astype(F)
    core=cv2.GaussianBlur(core,(0,0),1.5)*(win&(dist>1.5))
    def along(x):
        num=cv2.filter2D(x*core,-1,K,borderType=cv2.BORDER_REPLICATE)
        den=cv2.filter2D(core,-1,K,borderType=cv2.BORDER_REPLICATE)
        return np.where(den>1e-3,num/np.maximum(den,1e-3),x)
    k2=k2*(1-core)+along(k2)*core
    s2=s2*(1-core)+along(s2)*core

    out=np.dstack([np.clip(k2*200,0,255),np.clip(s2*255,0,255),np.clip(covN*255,0,255)]).round().astype(np.uint8)
    Image.fromarray(out).save(os.path.join(folder,f'pen_{tag}1.png'),optimize=True)
    print(tag,'edge fit lo/hi slope %.5f %.5f, offset %.2f px'%(pl[0],ph[0],delta))

if __name__=='__main__':
    folder=sys.argv[1] if len(sys.argv)>1 else '../public'
    for tag,P in POSES.items(): refine(folder,tag,P)
