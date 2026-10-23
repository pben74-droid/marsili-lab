#!/usr/bin/env python3
"""Acquisizione INGV FDSN con validazione e pubblicazione atomica del catalogo Marsili."""
import csv
import io
import json
import math
import os
import pathlib
import tempfile
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent
MARSILI = (39 + 14.912 / 60, 14 + 23.228 / 60)
RADIUS_KM = 250
DAYS = 30
QUERY_LIMIT = 20000


def hav(lat, lon):
    a, b = MARSILI
    r = 6371.0088
    x, y = math.radians(lat - a), math.radians(lon - b)
    z = math.sin(x / 2) ** 2 + math.cos(math.radians(a)) * math.cos(math.radians(lat)) * math.sin(y / 2) ** 2
    return 2 * r * math.asin(min(1, math.sqrt(z)))


def parse_time(value):
    value = value.strip()
    if not value:
        raise ValueError('data mancante')
    # Il catalogo INGV FDSN restituisce tempi UTC; preserviamo la stringa originale.
    normalized = value.replace(' ', 'T')
    if normalized.endswith('Z'):
        normalized = normalized[:-1] + '+00:00'
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def finite_float(value, field):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f'{field} non finito')
    return result


def fetch_catalog(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'MarsiliLabWeb/1.1 (public scientific data viewer)'})
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw = resp.read().decode('utf-8-sig')
    if not raw.strip():
        raise RuntimeError('Risposta INGV vuota')
    return raw


def build_catalog(raw, now, start, url):
    reader = csv.DictReader(io.StringIO(raw), delimiter='|')
    if not reader.fieldnames:
        raise RuntimeError('Intestazione catalogo INGV mancante')
    headers = {h.strip().lstrip('#').strip() for h in reader.fieldnames if h}
    required_groups = [
        {'Latitude', 'Lat'}, {'Longitude', 'Lon'},
        {'Magnitude', 'Mag'}, {'Time', 'DateTime', 'Date'},
        {'EventID', 'EventId', 'Event ID', 'ID'},
    ]
    if any(not (group & headers) for group in required_groups):
        raise RuntimeError('Intestazione INGV non compatibile: campi obbligatori mancanti')

    accepted = {}
    counts = Counter()
    total = 0
    for rec in reader:
        total += 1
        z = {k.strip().lstrip('#').strip(): (v or '').strip() for k, v in rec.items() if k}

        def get(*names):
            return next((z[k] for k in names if k in z), '')

        try:
            event_id = get('EventID', 'EventId', 'Event ID', 'ID').split('/')[-1]
            if not event_id:
                raise ValueError('identificativo mancante')
            when = get('Time', 'DateTime', 'Date')
            timestamp = parse_time(when)
            if timestamp < start - timedelta(minutes=1) or timestamp > now + timedelta(minutes=5):
                raise ValueError('data fuori intervallo')
            lat = finite_float(get('Latitude', 'Lat'), 'latitudine')
            lon = finite_float(get('Longitude', 'Lon'), 'longitudine')
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError('coordinate fuori intervallo')
            mag = finite_float(get('Magnitude', 'Mag'), 'magnitudo')
            if not (-2 <= mag <= 10):
                raise ValueError('magnitudo fuori intervallo')
            dep = get('Depth/Km', 'Depth', 'Depth/km')
            depth = finite_float(dep, 'profondità') if dep else None
            if depth is not None and not (-20 <= depth <= 750):
                raise ValueError('profondità fuori intervallo')
            distance = hav(lat, lon)
            if distance > RADIUS_KM:
                counts['outside_radius'] += 1
                continue
            if event_id in accepted:
                counts['duplicates'] += 1
                continue
            accepted[event_id] = {
                'id': event_id, 'time': when, 'lat': lat, 'lon': lon,
                'mag': mag,
                'magtype': get('MagType', 'MagnitudeType', 'Mag Type') or 'M (scala non indicata)',
                'depth': depth,
                'place': get('EventLocationName', 'Location', 'Region'),
                'distance': round(distance, 1),
                'url': 'https://terremoti.ingv.it/event/' + urllib.parse.quote(event_id, safe=''),
            }
        except (ValueError, TypeError, OverflowError) as exc:
            counts['invalid'] += 1
            reason = str(exc).split(':', 1)[0][:80] or 'dato non valido'
            counts['invalid_reasons:' + reason] += 1

    if total >= QUERY_LIMIT:
        raise RuntimeError('Raggiunto limite query INGV: catalogo potenzialmente incompleto; pubblicazione bloccata')
    if not accepted:
        raise RuntimeError('Nessun evento valido entro 250 km: pubblicazione bloccata per sicurezza')
    if counts['invalid'] > max(10, total * 0.1):
        raise RuntimeError(f'Troppe righe non valide ({counts["invalid"]}/{total}): pubblicazione bloccata')

    rows = sorted(accepted.values(), key=lambda x: parse_time(x['time']), reverse=True)
    quality = {
        'status': 'warning' if counts['invalid'] or counts['duplicates'] else 'ok',
        'received': total,
        'accepted': len(rows),
        'outside_radius': counts['outside_radius'],
        'duplicates': counts['duplicates'],
        'invalid': counts['invalid'],
        'invalid_reasons': {
            k.removeprefix('invalid_reasons:'): v
            for k, v in sorted(counts.items()) if k.startswith('invalid_reasons:')
        },
        'catalog_limit_reached': False,
    }
    return {
        'all_events': rows,
        'events': rows,
        'retrieved': now.isoformat(),
        'source': url,
        'marsili': {'lat': MARSILI[0], 'lon': MARSILI[1]},
        'filters': {'days': DAYS, 'radius': RADIUS_KM, 'minmag': 0},
        'analysis': {
            'status': 'Attribuzione causale non quantificabile',
            'summary': 'Le sole localizzazioni epicentrali non permettono di stimare la probabilità di origine magmatica. Servono meccanismi focali, forme d’onda, deformazione e dati geochimici.',
            'indicators': [],
        },
        'quality': quality,
    }


def atomic_write_json(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                         prefix='.data-', suffix='.tmp', delete=False) as f:
            tmp_name = f.name
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, target)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def run():
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=DAYS)
    q = {
        'starttime': start.strftime('%Y-%m-%dT%H:%M:%S'),
        'endtime': now.strftime('%Y-%m-%dT%H:%M:%S'),
        'minlatitude': 36.5, 'maxlatitude': 42,
        'minlongitude': 10.5, 'maxlongitude': 18.5,
        'format': 'text', 'orderby': 'time', 'limit': QUERY_LIMIT,
    }
    url = 'https://webservices.ingv.it/fdsnws/event/1/query?' + urllib.parse.urlencode(q)
    data = build_catalog(fetch_catalog(url), now, start, url)
    target = ROOT / 'docs' / 'data.json'
    atomic_write_json(target, data)
    quality = data['quality']
    print(f'Acquisiti {quality["received"]} eventi; pubblicati {quality["accepted"]}; '
          f'duplicati {quality["duplicates"]}; non validi {quality["invalid"]}; '
          f'fuori raggio {quality["outside_radius"]}; aggiornato {target}')


if __name__ == '__main__':
    run()
