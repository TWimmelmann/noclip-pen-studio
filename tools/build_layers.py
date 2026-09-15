"""Byg lag-filer til NOCLIP Pen Studio ud fra et produktfoto.

Værktøjet renderer ikke pennen om — det skiller fotoet ad i lag, så farven kan
skiftes uden at lys, struktur og kanter går tabt:

  l1  R = lakkoefficient   G = hvidt lys   B = dækning (alpha)
  l2  R = skaft            G = stylus-top  B = metaldele
  l3  R = metalluminans    G = illumination (til at skygge tryk)

Brug:
  python build_layers.py foto.jpg --tag vert --out ../public
  python build_layers.py foto.jpg --tag diag --erase-logo

Kravene til fotoet står i README i denne mappe. Kort fortalt: én pen, ren lys
baggrund, hele pennen i billedet, og så lidt JPEG-komprimering som muligt.
"""

import argparse, os
import numpy as np, cv2, json
from PIL import Image
from matte import object_matte, hybrid_fg, fill_holes
import penlib
F32=np.float32

def build(path, tag, erase_logo=False, denoise_along=9.0, outdir=None):
    s=penlib.segment(path)
    img,cov,obj,core,FG=s['img'],s['cov'],s['obj'],s['core'],s['FG']
    barrel,dome,metal=s['barrel'],s['dome'],s['metal']
    H,W=s['H'],s['W']
    R,G,B=FG[...,0],FG[...,1],FG[...,2]

    def soft(m,sg=1.1): return cv2.GaussianBlur(m.astype(F32),(0,0),sg)
    wb,wd,wm=soft(barrel),soft(dome),soft(metal)
    tot=np.maximum(wb+wd+wm,1e-6); wb,wd,wm=wb/tot,wd/tot,wm/tot
    inside=(cov>0.001); wb,wd,wm=[x*inside for x in (wb,wd,wm)]

    lac=(barrel|dome).astype(bool)
    sat=FG.max(-1)-FG.min(-1)
    pure=lac&(sat>np.percentile(sat[lac],70))&core.astype(bool)
    base=np.median(FG[pure],0).astype(F32)
    M=np.stack([base,np.full(3,255.,F32)],1); Minv=np.linalg.inv(M.T@M)@M.T
    ks=np.einsum('ij,hwj->hwi',Minv,FG)
    k=np.clip(ks[...,0],0,1.27); sp=np.clip(ks[...,1],0,1)

    logo_bbox=None
    if erase_logo:
        lg=((sp>0.55)&(k<0.45)&cv2.erode(barrel,np.ones((13,13),np.uint8)).astype(bool)).astype(np.uint8)
        ys,xs=np.nonzero(lg); logo_bbox=[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())]
        lg=cv2.dilate(lg,np.ones((11,11),np.uint8))
        kk=cv2.inpaint((k/1.27*255).astype(np.uint8),lg,14,cv2.INPAINT_TELEA).astype(F32)/255*1.27
        ss=cv2.inpaint((sp*255).astype(np.uint8),lg,14,cv2.INPAINT_TELEA).astype(F32)/255
        m3=cv2.GaussianBlur(lg.astype(F32),(0,0),2.0)
        k=k*(1-m3)+cv2.GaussianBlur(kk,(0,0),2.5)*m3
        sp=sp*(1-m3)+cv2.GaussianBlur(ss,(0,0),2.5)*m3

    # directional denoise: strong along the axis, none across it
    c,d,dp=penlib.axis_of(barrel)
    r=int(np.ceil(3*denoise_along)); yy,xx=np.mgrid[-r:r+1,-r:r+1].astype(F32)
    a=xx*d[0]+yy*d[1]; b=xx*dp[0]+yy*dp[1]
    K=np.exp(-(a*a)/(2*denoise_along**2)-(b*b)/(2*0.55**2)); K=(K/K.sum()).astype(F32)
    wcore=cv2.GaussianBlur(cv2.erode((wb>0.85).astype(np.uint8),np.ones((9,9),np.uint8)).astype(F32),(0,0),6.0)
    k=k*(1-wcore)+cv2.filter2D(k,-1,K,borderType=cv2.BORDER_REPLICATE)*wcore
    sp=sp*(1-wcore)+cv2.filter2D(sp,-1,K,borderType=cv2.BORDER_REPLICATE)*wcore
    dm=cv2.GaussianBlur((wd>0.6).astype(F32),(0,0),3.0)
    k=k*(1-dm)+cv2.bilateralFilter(k,9,0.05,6)*dm
    sp=sp*(1-dm)+cv2.bilateralFilter(sp,9,0.05,6)*dm

    # metal: one normalisation for the whole Part 2, anchored on robust
    # percentiles. Normalising each part separately (an earlier attempt) stretched
    # the narrow-range ring up into the ramp's white end and flattened its
    # roundness, which read as a dark rim where it met the barrel.
    L=(0.2126*R+0.7152*G+0.0722*B)
    mb=cv2.erode(metal,np.ones((7,7),np.uint8)).astype(bool)
    med=float(np.median(L[mb]))
    p3,p97=np.percentile(L[mb],[3,97])
    half=max((p97-p3)/2.0,12.0)
    meta_metal=[med,float(half)]
    mlum=np.clip(0.5+(L-med)/(2.0*half),0,1)
    mm=cv2.GaussianBlur((wm>0.6).astype(F32),(0,0),2.0)
    mlum=mlum*(1-mm)+cv2.bilateralFilter(mlum.astype(F32),7,0.045,5)*mm

    illum=np.clip(k*0.55+sp*1.7,0,1.6); illum=illum/np.percentile(illum[lac],97)
    illum=np.clip(cv2.GaussianBlur(illum,(0,0),1.8),0,1)

    t,n=penlib.tn_grid(cov.shape,c,d,dp)
    pen=cov>0.02; bar=barrel.astype(bool)
    mid=bar&(np.abs(t-np.median(t[bar]))<8)
    Lp=float(t[pen].max()-t[pen].min()); Dp=float(n[mid].max()-n[mid].min())
    ys,xs=np.nonzero(pen); x0,x1,y0,y1=int(xs.min()),int(xs.max()),int(ys.min()),int(ys.max())
    ch=(y1-y0)*1.10; cw=ch*3/4; ccx,ccy=(x0+x1)/2,(y0+y1)/2
    meta=dict(tag=tag,width=W,height=H,
      axis=dict(cx=float(c[0]),cy=float(c[1]),dx=float(d[0]),dy=float(d[1])),
      penT=[float(t[pen].min()),float(t[pen].max())],
      barrelT=[float(t[bar].min()),float(t[bar].max())],
      pxAlong=round(Lp/140.0,4), pxAcross=round(Dp/9.5,4),
      penBBox=[x0,y0,x1,y1],
      portrait=dict(x=round(ccx-cw/2,1),y=round(ccy-ch/2,1),w=round(cw,1),h=round(ch,1)),
      base=[float(v) for v in base], logoBBox=logo_bbox, metalRange=meta_metal)

    # crop every layer to the pen plus a margin: the rest of the frame is empty
    # background, so storing and looping over it is pure waste
    MG=14
    cx0,cy0=max(0,x0-MG),max(0,y0-MG); cx1,cy1=min(W,x1+MG+1),min(H,y1+MG+1)
    meta['crop']=[int(cx0),int(cy0),int(cx1-cx0),int(cy1-cy0)]
    C=lambda a: a[cy0:cy1,cx0:cx1]
    ch_,cw_=cy1-cy0,cx1-cx0
    def u8(x,sc=255.0): return np.clip(C(x)*sc,0,255).astype(np.uint8)
    out=outdir or '.'
    os.makedirs(out,exist_ok=True)
    pre=os.path.join(out,tag)
    Image.fromarray(np.dstack([u8(k,200.0),u8(sp),u8(cov)])).save(pre+'_l1.png',optimize=True)
    Image.fromarray(np.dstack([u8(wb),u8(wd),u8(wm)])).save(pre+'_l2.png',optimize=True)
    Image.fromarray(np.dstack([u8(mlum),u8(illum),np.zeros((ch_,cw_),np.uint8)])).save(pre+'_l3.png',optimize=True)
    # the contact point is where the tip meets the surface: lowest covered row
    ys_,xs_=np.nonzero(cov>0.35)
    ymax=int(ys_.max()); band=ys_>=ymax-6
    meta['contact']=[round(float(xs_[band].mean()),1),float(ymax)]
    json.dump(meta,open(pre+'_meta.json','w'),indent=1)
    return meta,k,sp,cov,wb,wd,wm,mlum

def main():
    ap=argparse.ArgumentParser(description='Byg lag-filer fra et produktfoto af en pen.')
    ap.add_argument('foto', help='JPG eller PNG med én pen på ren lys baggrund')
    ap.add_argument('--tag', required=True,
                    help="navn på positur, fx 'vert' eller 'diag' (bruges som filpræfiks)")
    ap.add_argument('--out', default='.', help='mappe til lag-filerne (default: her)')
    ap.add_argument('--erase-logo', action='store_true',
                    help='mal et eksisterende tryk væk, så skaftet starter blankt')
    ap.add_argument('--denoise', type=float, default=9.0,
                    help='udglatning langs skaftet i px (default 9; 0 slår fra)')
    a=ap.parse_args()
    m,*_=build(a.foto,a.tag,erase_logo=a.erase_logo,
               denoise_along=a.denoise,outdir=a.out)
    print('%s: %.2f px/mm langs, %.2f px/mm tværs' % (a.tag,m['pxAlong'],m['pxAcross']))
    print('  lakfarve i kilden : #%02X%02X%02X' % tuple(int(v) for v in m['base']))
    print('  metal (median,spredning): %.1f, %.1f' % tuple(m['metalRange']))
    print('  beskåret til      : %s' % m['crop'])
    print('  kontaktpunkt      : %s' % m['contact'])
    print()
    print('Indsæt tallene i POSES i public/index.html — se tools/README.md.')


if __name__=='__main__':
    main()
