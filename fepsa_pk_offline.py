#!/usr/bin/env python3
"""
FEPSA Avanza — Posicionamiento offline GPS → Punto Kilométrico
Traza extraída de /api/kms/ObtenerTraza

Uso:
    python3 fepsa_pk_offline.py                        # demo con coordenadas de ejemplo
    python3 fepsa_pk_offline.py -lat -34.837 -lon -59.874
    python3 fepsa_pk_offline.py -lat -34.837 -lon -59.874 -div 74
"""

import json
import math
import argparse
from collections import defaultdict

TRAZA_FILE = "traza_fepsa.json"  # mismo directorio que este script

# ---------------------------------------------------------------------------
# Geometría — todo en math puro, sin dependencias externas
# ---------------------------------------------------------------------------

def haversine_m(lat1, lon1, lat2, lon2):
    """Distancia en metros entre dos puntos (fórmula de Haversine)."""
    R = 6_371_000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def point_to_segment_distance(px, py, ax, ay, bx, by):
    """
    Distancia de punto P al segmento AB (en coordenadas planas aproximadas).
    Devuelve (distancia, t) donde t∈[0,1] es la posición relativa sobre AB.
    """
    dx, dy = bx - ax, by - ay
    len_sq = dx*dx + dy*dy
    if len_sq == 0:
        return math.hypot(px - ax, py - ay), 0.0
    t = max(0.0, min(1.0, ((px - ax)*dx + (py - ay)*dy) / len_sq))
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    return math.hypot(px - proj_x, py - proj_y), t


def snap_to_traza(lat, lon, puntos, div_filter=None, max_dist_m=500):
    """
    Dado un punto GPS (lat, lon), encuentra el PK más cercano sobre la traza.

    Parámetros:
        puntos      — lista de dicts de la traza
        div_filter  — si se indica, filtra solo esa DIV
        max_dist_m  — distancia máxima aceptable (m); si se supera devuelve None

    Retorna dict con:
        pk          — punto kilométrico interpolado
        div         — división/ramal
        dist_m      — distancia al punto proyectado (m)
        segmento    — (ID punto A, ID punto B)
        coords_snap — (lat, lon) del punto proyectado sobre la vía
    """
    candidatos = [p for p in puntos if div_filter is None or p['DIV'] == div_filter]
    if not candidatos:
        return None

    mejor = None
    mejor_dist = float('inf')

    # Convertir a coordenadas planas aproximadas (suficiente para ~100 km)
    # Usamos lat/lon escalado: 1° lat ≈ 111 km, 1° lon ≈ 111*cos(lat) km
    lat_ref = candidatos[0]['LATITUD']
    cos_lat = math.cos(math.radians(lat_ref))

    px = lon * cos_lat
    py = lat

    for i in range(len(candidatos) - 1):
        a, b = candidatos[i], candidatos[i+1]

        # Solo comparar segmentos de la misma DIV
        if a['DIV'] != b['DIV']:
            continue

        ax, ay = a['LONGITUD'] * cos_lat, a['LATITUD']
        bx, by = b['LONGITUD'] * cos_lat, b['LATITUD']

        dist_plana, t = point_to_segment_distance(px, py, ax, ay, bx, by)

        # Convertir distancia plana a metros
        dist_m = dist_plana * 111_000

        if dist_m < mejor_dist:
            mejor_dist = dist_m
            # Interpolar KM
            km_interp = a['KM'] + t * (b['KM'] - a['KM'])
            # Coords del punto proyectado
            snap_lon = (ax + t*(bx-ax)) / cos_lat
            snap_lat = ay + t*(by-ay)
            mejor = {
                'pk': round(km_interp, 3),
                'div': a['DIV'],
                'dist_m': round(dist_m, 1),
                'segmento': (a['ID'], b['ID']),
                'coords_snap': (round(snap_lat, 6), round(snap_lon, 6))
            }

    if mejor and mejor['dist_m'] > max_dist_m:
        return None  # Demasiado lejos de cualquier vía

    return mejor


def get_divs(puntos):
    """Lista de DIVs disponibles con rango de KM."""
    divs = defaultdict(list)
    for p in puntos:
        divs[p['DIV']].append(p['KM'])
    return {d: (round(min(kms), 1), round(max(kms), 1)) for d, kms in sorted(divs.items())}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="FEPSA PK offline")
    parser.add_argument('-lat', type=float, help='Latitud GPS')
    parser.add_argument('-lon', type=float, help='Longitud GPS')
    parser.add_argument('-div', type=str, default=None, help='Filtrar por DIV (ej: 74, AP, EP)')
    parser.add_argument('-listdivs', action='store_true', help='Listar todas las DIVs')
    parser.add_argument('-traza', type=str, default=TRAZA_FILE, help='Ruta al JSON de traza')
    args = parser.parse_args()

    print(f"Cargando traza desde {args.traza}...")
    with open(args.traza) as f:
        puntos = json.load(f)
    print(f"  {len(puntos)} puntos cargados.\n")

    if args.listdivs:
        divs = get_divs(puntos)
        print(f"{'DIV':<10} {'KM desde':>10} {'KM hasta':>10}  pts")
        print("-" * 45)
        cnt = defaultdict(int)
        for p in puntos: cnt[p['DIV']] += 1
        for div, (km_min, km_max) in divs.items():
            print(f"  {div:<8} {km_min:>10.1f} {km_max:>10.1f}  {cnt[div]}")
        return

    if args.lat is None or args.lon is None:
        # Demo con algunos puntos de ejemplo
        ejemplos = [
            (-34.8376, -59.8744, "Inicio DIV 74"),
            (-34.9200, -60.1500, "Intermedio aprox"),
            (-38.7000, -62.2500, "Zona sur"),
            (-34.6037, -58.3816, "Buenos Aires (fuera de vía)"),
        ]
        print("=== DEMO — posicionamiento de puntos de ejemplo ===\n")
        for lat, lon, desc in ejemplos:
            result = snap_to_traza(lat, lon, puntos, div_filter=args.div)
            if result:
                print(f"📍 {desc}")
                print(f"   GPS:      {lat}, {lon}")
                print(f"   PK:       {result['pk']} km  (DIV {result['div']})")
                print(f"   Dist vía: {result['dist_m']} m")
                print(f"   Snap:     {result['coords_snap']}")
            else:
                print(f"📍 {desc} → fuera de rango (>500m de cualquier vía)")
            print()
    else:
        result = snap_to_traza(args.lat, args.lon, puntos, div_filter=args.div)
        if result:
            print(f"📍 GPS: {args.lat}, {args.lon}")
            print(f"   PK:       {result['pk']} km")
            print(f"   DIV:      {result['div']}")
            print(f"   Dist vía: {result['dist_m']} m")
            print(f"   Snap:     {result['coords_snap']}")
            print(f"   Segmento: puntos ID {result['segmento'][0]} → {result['segmento'][1]}")
        else:
            print(f"⚠ Punto ({args.lat}, {args.lon}) a más de 500m de cualquier vía registrada.")


if __name__ == '__main__':
    main()
