#!/usr/bin/env python3
"""Download a *real* EMODnet bathymetric grid through the documented WCS 1.0.0.
Fail closed: no synthetic terrain or replacement values on download errors.
"""
import json, pathlib, tempfile, urllib.parse, urllib.request
from datetime import datetime, timezone
import numpy as np
import rasterio

ROOT=pathlib.Path(__file__).parent
BBOX=(13.55,38.55,15.35,39.95) # lon min, lat min, lon max, lat max
RES=.0125 # degrees; downsampled for a fast interactive surface, NOT native DTM resolution

def run():
    q={'service':'WCS','version':'1.0.0','request':'GetCoverage',
       'coverage':'emodnet:mean','crs':'EPSG:4326',
       'bbox':','.join(map(str,BBOX)),'format':'image/tiff',
       'interpolation':'nearest','resx':str(RES),'resy':str(RES)}
    url='https://ows.emodnet-bathymetry.eu/wcs?'+urllib.parse.urlencode(q)
    req=urllib.request.Request(url,headers={'User-Agent':'MarsiliLab/3.0 scientific bathymetry viewer'})
    with urllib.request.urlopen(req,timeout=180) as resp:
        raw=resp.read()
        if len(raw)>30_000_000:raise ValueError('Risposta troppo grande')
        if raw[:4] not in (b'II*\x00',b'MM\x00*',b'II+\x00',b'MM\x00+'):
            raise ValueError('EMODnet non ha restituito un GeoTIFF: '+raw[:180].decode('utf-8','replace'))
    with tempfile.NamedTemporaryFile(suffix='.tif') as tmp:
        tmp.write(raw);tmp.flush()
        with rasterio.open(tmp.name) as ds:
            if ds.crs is None or ds.crs.to_epsg()!=4326:raise ValueError('CRS GeoTIFF non è EPSG:4326')
            a=ds.read(1,masked=True)
            if ds.width>350 or ds.height>350:raise ValueError('Griglia troppo grande')
            if ds.width<20 or ds.height<20:raise ValueError('Griglia troppo piccola')
            # Raster rows are north-to-south; output lat is south-to-north.
            vals=np.ma.filled(a.astype('float64'),np.nan)[::-1,:]
            lon=[float(rasterio.transform.xy(ds.transform,0,c,offset='center')[0]) for c in range(ds.width)]
            lat=[float(rasterio.transform.xy(ds.transform,r,0,offset='center')[1]) for r in range(ds.height-1,-1,-1)]
            good=vals[np.isfinite(vals)]
            if len(good)<vals.size*.45:raise ValueError('Troppi dati batimetrici mancanti')
            if not (-7000<float(np.nanmin(good))<0 and -7000<float(np.nanmax(good))<500):
                raise ValueError('Valori altimetrici non plausibili per area marina')
            depth=[[None if not np.isfinite(v) or v>0 else round(float(v),1) for v in row] for row in vals]
    obj={'source':'EMODnet Bathymetry DTM WCS emodnet:mean',
         'wcs_url':url,'retrieved':datetime.now(timezone.utc).isoformat(),
         'bbox':list(BBOX),'resolution_deg':RES,'lon':lon,'lat':lat,'depth_m':depth,
         'note':'Quote in metri rispetto al livello del mare; negativo sotto il mare. Celle prive di dato null. Griglia ricampionata, non risoluzione nativa.'}
    target=ROOT/'docs/bathymetry.json'
    target.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':')))
    print('Pubblicata griglia EMODnet',len(lat),'x',len(lon),'->',target)
if __name__=='__main__':run()
