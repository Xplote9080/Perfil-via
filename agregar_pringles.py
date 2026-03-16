#!/usr/bin/env python3
"""
FEPSA — Agregar DIV PRING (Olavarría - Bahía Blanca vía Pringles) a la traza principal

Uso:
    python agregar_pringles.py

Requiere en la misma carpeta:
    - pringles_traza.json       (la traza nueva sin altitudes)
    - traza_fepsa_alt.json      (la traza principal ya con altitudes)

Genera:
    - traza_fepsa_alt.json      (actualizado con DIV PRING incorporada)
"""

import json
import math
import time
import urllib.request
import os
import sys

PRINGLES_FILE = "pringles_traza.json"
TRAZA_FILE    = "traza_fepsa_alt.json"
API_URL       = "https://api.opentopodata.org/v1/srtm30m"
BATCH_SIZE    = 100
DELAY_SEG     = 1.1


def fetch_elevations(points):
    locations = "|".join(f"{lat},{lon}" for lat, lon in points)
    url = f"{API_URL}?locations={locations}&interpolation=bilinear"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FEPSA-traza/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        if data.get("status") == "OK":
            return [r.get("elevation") for r in data["results"]]
        else:
            print(f"  ⚠ API error: {data.get('error')}")
            return [None] * len(points)
    except Exception as e:
        print(f"  ⚠ Error: {e}")
        return [None] * len(points)


def main():
    # Verificar archivos
    for f in [PRINGLES_FILE, TRAZA_FILE]:
        if not os.path.exists(f):
            print(f"ERROR: No se encuentra {f}")
            sys.exit(1)

    print(f"Cargando {PRINGLES_FILE}...")
    with open(PRINGLES_FILE, encoding='utf-8') as f:
        puntos = json.load(f)
    print(f"  {len(puntos)} puntos cargados (DIV PRING)")

    # Agregar altitudes
    total = len(puntos)
    cache_file = "pringles_alt_cache.json"
    cache = {}
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            cache = json.load(f)
        print(f"  Cache previo: {len(cache)} altitudes\n")

    batches = math.ceil(total / BATCH_SIZE)
    print(f"Descargando altitudes SRTM ({batches} requests, ~{batches*DELAY_SEG/60:.1f} min)...\n")

    for i in range(0, total, BATCH_SIZE):
        batch = puntos[i:i+BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        pendientes = [(j, p) for j, p in enumerate(batch)
                      if str(i+j) not in cache]

        if not pendientes:
            print(f"  [{batch_num}/{batches}] Cache OK")
            continue

        coords = [(p['LATITUD'], p['LONGITUD']) for _, p in pendientes]
        print(f"  [{batch_num}/{batches}] Puntos {i+1}–{i+len(batch)}...", end=" ", flush=True)
        alts = fetch_elevations(coords)

        for (j, _), alt in zip(pendientes, alts):
            cache[str(i+j)] = alt

        with open(cache_file, 'w') as f:
            json.dump(cache, f)

        ok = sum(1 for a in alts if a is not None)
        print(f"OK={ok}/{len(alts)}")

        if batch_num < batches:
            time.sleep(DELAY_SEG)

    # Aplicar altitudes
    for i, p in enumerate(puntos):
        p['ALTITUD'] = cache.get(str(i))

    if os.path.exists(cache_file):
        os.remove(cache_file)

    con_alt = sum(1 for p in puntos if p.get('ALTITUD') is not None)
    print(f"\n✓ {con_alt}/{total} puntos con altitud")

    # Fusionar con la traza principal
    print(f"\nCargando {TRAZA_FILE}...")
    with open(TRAZA_FILE, encoding='utf-8') as f:
        traza = json.load(f)
    print(f"  {len(traza)} puntos existentes")

    # Eliminar PRING si ya existe (para no duplicar)
    traza = [p for p in traza if p.get('DIV') != 'PRING']

    # Reasignar IDs para que no choquen
    max_id = max((p.get('ID', 0) for p in traza), default=0)
    for i, p in enumerate(puntos):
        p['ID'] = max_id + i + 1

    # Agregar los nuevos puntos
    traza.extend(puntos)

    # Guardar
    with open(TRAZA_FILE, 'w', encoding='utf-8') as f:
        json.dump(traza, f, ensure_ascii=False)

    print(f"✓ {TRAZA_FILE} actualizado: {len(traza)} puntos totales")
    print(f"\nDIVs en la traza ahora:")
    from collections import Counter
    divs = Counter(p.get('DIV') for p in traza)
    for div, cnt in sorted(divs.items()):
        pts_div = [p for p in traza if p.get('DIV') == div]
        kms = [p['KM'] for p in pts_div]
        print(f"  {div:<10} {cnt:5d} pts   KM {min(kms):.1f}–{max(kms):.1f}")

    print("\n✓ Listo. Recargá el visor en el navegador.")


if __name__ == '__main__':
    main()
