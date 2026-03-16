#!/usr/bin/env python3
"""
Agrega altitudes SRTM a las 4 DIVs nuevas y las fusiona en traza_fepsa_alt.json

Requiere en la misma carpeta:
    - traza_emplobos.json       (Cañuelas - Empalme Lobos)
    - traza_rauch.json      (Las Flores - Tandil, ex LFT)
    - traza_baril.json      (Patagones - Bariloche, ex PAB)
    - pringles_traza.json   (Olavarría - Bahía Blanca vía Pringles)
    - traza_fepsa_alt.json

Uso: python agregar_nuevas_divs.py
"""
import json, math, time, urllib.request, os, sys

API_URL    = "https://api.opentopodata.org/v1/srtm30m"
BATCH_SIZE = 100
DELAY_SEG  = 1.1
TRAZA_FILE = "traza_fepsa_alt.json"

NUEVAS = [
    ("traza_emplobos.json",     "EMP. LOBOS"),
    ("traza_rauch.json",     "RAUCH"),
    ("traza_baril.json",     "BARIL"),
    ("pringles_traza.json",  "PRING"),
]

# DIVs obsoletas a eliminar (nombres viejos que pueden quedar en la traza)
OBSOLETAS = {'PAB', 'LFT'}

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

def enriquecer(puntos, div):
    total    = len(puntos)
    cache_f  = f"cache_{div}.json"
    cache    = {}
    if os.path.exists(cache_f):
        with open(cache_f) as f: cache = json.load(f)
        print(f"  Cache previo: {len(cache)} altitudes")

    batches = math.ceil(total / BATCH_SIZE)
    print(f"  {total} pts — {batches} requests (~{batches*DELAY_SEG/60:.1f} min)")

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
        p['DIV']     = div  # asegurar nombre correcto
    if os.path.exists(cache_f): os.remove(cache_f)
    return puntos

def main():
    # Verificar archivos
    faltantes = [f for f, _ in NUEVAS if not os.path.exists(f)]
    if not os.path.exists(TRAZA_FILE): faltantes.append(TRAZA_FILE)
    if faltantes:
        print(f"ERROR: faltan archivos: {faltantes}"); sys.exit(1)

    print(f"Cargando {TRAZA_FILE}...")
    with open(TRAZA_FILE) as f: traza = json.load(f)

    # Eliminar DIVs que se van a reemplazar + nombres obsoletos
    divs_a_eliminar = {div for _, div in NUEVAS} | OBSOLETAS
    antes = len(traza)
    traza = [p for p in traza if p.get('DIV') not in divs_a_eliminar]
    print(f"  Eliminados {antes - len(traza)} puntos de DIVs a reemplazar")
    print(f"  Base: {len(traza)} puntos restantes")

    max_id = max((p.get('ID', 0) for p in traza), default=0)

    for archivo, div in NUEVAS:
        print(f"\n=== {div} ({archivo}) ===")
        with open(archivo) as f: puntos = json.load(f)
        kms = [p['KM'] for p in puntos]
        print(f"  KM {min(kms):.1f}–{max(kms):.1f}")
        puntos = enriquecer(puntos, div)
        con_alt = sum(1 for p in puntos if p.get('ALTITUD') is not None)
        print(f"  {con_alt}/{len(puntos)} con altitud")
        for i, p in enumerate(puntos):
            p['ID'] = max_id + i + 1
        max_id += len(puntos)
        traza.extend(puntos)

    with open(TRAZA_FILE, 'w') as f:
        json.dump(traza, f, ensure_ascii=False)

    print(f"\n✓ {TRAZA_FILE} actualizado: {len(traza)} puntos totales")
    print("\nDIVs agregadas:")
    from collections import Counter
    divs = Counter(p.get('DIV') for p in traza)
    for div, _ in NUEVAS:
        d = div if isinstance(div, str) else div
    for _, div in NUEVAS:
        pts = [p for p in traza if p.get('DIV') == div]
        if pts:
            kms = [p['KM'] for p in pts]
            print(f"  {div:<8} {len(pts):5d} pts  KM {min(kms):.1f}–{max(kms):.1f}")

if __name__ == '__main__':
    main()
