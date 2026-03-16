#!/usr/bin/env python3
"""
Agrega/reemplaza DIV PRING (Olavarría - Bahía Blanca vía Pringles)
en traza_fepsa_alt.json con altitudes SRTM.

Uso: python agregar_pringles_v2.py

Requiere en la misma carpeta:
    - pringles_traza.json
    - traza_fepsa_alt.json
"""
import json, math, time, urllib.request, os, sys

API_URL    = "https://api.opentopodata.org/v1/srtm30m"
BATCH_SIZE = 100
DELAY_SEG  = 1.1
TRAZA_FILE = "traza_fepsa_alt.json"
PRING_FILE = "pringles_traza.json"

def fetch_elevations(points):
    locations = "|".join(f"{lat},{lon}" for lat, lon in points)
    url = f"{API_URL}?locations={locations}&interpolation=bilinear"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FEPSA-traza/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        if data.get("status") == "OK":
            return [r.get("elevation") for r in data["results"]]
        print(f"  API error: {data.get('error')}")
        return [None] * len(points)
    except Exception as e:
        print(f"  Error: {e}")
        return [None] * len(points)

def main():
    for f in [TRAZA_FILE, PRING_FILE]:
        if not os.path.exists(f):
            print(f"ERROR: falta {f}"); sys.exit(1)

    print(f"Cargando {PRING_FILE}...")
    with open(PRING_FILE) as f:
        puntos = json.load(f)
    print(f"  {len(puntos)} puntos  KM {puntos[0]['KM']:.1f}–{puntos[-1]['KM']:.1f}")

    # Descargar altitudes
    total   = len(puntos)
    cache_f = "cache_PRING.json"
    cache   = {}
    if os.path.exists(cache_f):
        with open(cache_f) as f: cache = json.load(f)
        print(f"  Cache previo: {len(cache)} altitudes")

    batches = math.ceil(total / BATCH_SIZE)
    print(f"\nDescargando altitudes SRTM ({batches} requests, ~{batches*DELAY_SEG/60:.1f} min)...")

    for i in range(0, total, BATCH_SIZE):
        batch     = puntos[i:i+BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        pendientes = [(j, p) for j, p in enumerate(batch) if str(i+j) not in cache]
        if not pendientes:
            print(f"  [{batch_num}/{batches}] cache OK")
            continue
        coords = [(p['LATITUD'], p['LONGITUD']) for _, p in pendientes]
        print(f"  [{batch_num}/{batches}] puntos {i+1}–{i+len(batch)}...", end=" ", flush=True)
        alts = fetch_elevations(coords)
        for (j, _), alt in zip(pendientes, alts):
            cache[str(i+j)] = alt
        with open(cache_f, 'w') as f: json.dump(cache, f)
        print(f"OK={sum(1 for a in alts if a is not None)}/{len(alts)}")
        if batch_num < batches: time.sleep(DELAY_SEG)

    for i, p in enumerate(puntos):
        p['ALTITUD'] = cache.get(str(i))
    if os.path.exists(cache_f): os.remove(cache_f)

    con_alt = sum(1 for p in puntos if p.get('ALTITUD') is not None)
    print(f"\n✓ {con_alt}/{total} puntos con altitud")

    # Fusionar con traza principal
    print(f"\nCargando {TRAZA_FILE}...")
    with open(TRAZA_FILE) as f:
        traza = json.load(f)

    # Eliminar cualquier versión previa de PRING
    antes = len(traza)
    traza = [p for p in traza if p.get('DIV') != 'PRING']
    print(f"  PRING previos eliminados: {antes - len(traza)} puntos")

    # Reasignar IDs
    max_id = max((p.get('ID', 0) for p in traza), default=0)
    for i, p in enumerate(puntos):
        p['ID']  = max_id + i + 1
        p['DIV'] = 'PRING'

    traza.extend(puntos)

    with open(TRAZA_FILE, 'w') as f:
        json.dump(traza, f, ensure_ascii=False)

    pring_pts = [p for p in traza if p.get('DIV') == 'PRING']
    kms = [p['KM'] for p in pring_pts]
    print(f"✓ PRING agregado: {len(pring_pts)} puntos  KM {min(kms):.1f}–{max(kms):.1f}")
    print(f"✓ {TRAZA_FILE} actualizado: {len(traza)} puntos totales")

if __name__ == '__main__':
    main()
