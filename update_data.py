#!/usr/bin/env python3
"""Fetch authoritative INGV FDSN event data, publish a bounded static JSON snapshot."""
import csv, io, json, math, pathlib, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
ROOT=pathlib.Path(__file__).parent
MARSILI=(39+14.912/60,14+23.228/60)
RADIUS=250

def hav(lat,lon):
    a,b=MARSILI; r=6371.0088
    x=math.radians(lat-a); y=math.radians(lon-b)
    z=math.sin(x/2)**2+math.cos(math.radians(a))*math.cos(math.radians(lat))*math.sin(y/2)**2
    return 2*r*math.asin(min(1,math.sqrt(z)))

def run():
    now=datetime.now(timezone.utc); start=now-timedelta(days=30)
    q={'starttime':start.strftime('%Y-%m-%dT%H:%M:%S'),'endtime':now.strftime('%Y-%m-%dT%H:%M:%S'),
       'minlatitude':36.5,'maxlatitude':42,'minlongitude':10.5,'maxlongitude':18.5,
       'format':'text','orderby':'time','limit':20000}
    url='https://webservices.ingv.it/fdsnws/event/1/query?'+urllib.parse.urlencode(q)
    req=urllib.request.Request(url,headers={'User-Agent':'MarsiliLabWeb/1.0 (public scientific data viewer)'})
    with urllib.request.urlopen(req,timeout=90) as resp: raw=resp.read().decode('utf-8-sig')
    if not raw.strip(): raise RuntimeError('Risposta INGV vuota')
    rows=[]
    for rec in csv.DictReader(io.StringIO(raw),delimiter='|'):
        z={k.strip().lstrip('#').strip():(v or '').strip() for k,v in rec.items() if k}
        def get(*names):
            return next((z[k] for k in names if k in z),'')
        try:
            lat=float(get('Latitude','Lat')); lon=float(get('Longitude','Lon'))
            distance=hav(lat,lon)
            if distance>RADIUS: continue
            mag=float(get('Magnitude','Mag'))
            dep=get('Depth/Km','Depth','Depth/km')
            depth=float(dep) if dep else None
            event_id=get('EventID','EventId','Event ID','ID').split('/')[-1]
            when=get('Time','DateTime','Date')
            if not when or not event_id: continue
            rows.append({'id':event_id,'time':when,'lat':lat,'lon':lon,'mag':mag,
                         'magtype':get('MagType','MagnitudeType','Mag Type') or 'M (scala non indicata)',
                         'depth':depth,'place':get('EventLocationName','Location','Region'),
                         'distance':round(distance,1),'url':'https://terremoti.ingv.it/event/'+urllib.parse.quote(event_id)})
        except (ValueError,TypeError): continue
    if not rows: raise RuntimeError('Nessun evento interpretabile: verificare il formato INGV')
    rows.sort(key=lambda x:x['time'],reverse=True)
    data={'all_events':rows,'events':rows,'retrieved':now.isoformat(),'source':url,
          'marsili':{'lat':MARSILI[0],'lon':MARSILI[1]},'filters':{'days':30,'radius':250,'minmag':0},
          'analysis':{'status':'Attribuzione causale non quantificabile',
                      'summary':'Le sole localizzazioni epicentrali non permettono di stimare la probabilità di origine magmatica. Servono meccanismi focali, forme d’onda, deformazione e dati geochimici.',
                      'indicators':[]}}
    target=ROOT/'docs'/'data.json'
    target.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(f'Acquisiti {len(rows)} eventi; aggiornato {target}')
if __name__=='__main__':run()
