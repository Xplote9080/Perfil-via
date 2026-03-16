#!/usr/bin/env python3
"""
FEPSA — Enriquecimiento de traza con altitud SRTM
Consulta Open Topo Data (gratuito, sin registro) en batches de 100 puntos.

Uso:
    python fepsa_altitud.py

Requiere:
    - traza_fepsa.json en el mismo directorio
    - Conexión a internet (solo para la descarga de elevaciones)

Genera:
    - traza_fepsa_alt.json   (traza con campo ALTITUD agregado)
    - traza_fepsa_alt.geojson
    - traza_fepsa_alt.kml    (con altitud 3D)
    - perfil_fepsa.html      (gráfico interactivo de perfil por DIV)
"""

import json
import time
import urllib.request
import urllib.error
import math
import os
import sys
from collections import defaultdict

TRAZA_FILE   = "traza_fepsa.json"
OUT_JSON     = "traza_fepsa_alt.json"
OUT_GEOJSON  = "traza_fepsa_alt.geojson"
OUT_KML      = "traza_fepsa_alt.kml"
OUT_HTML     = "perfil_fepsa.html"

API_URL      = "https://api.opentopodata.org/v1/srtm30m"
BATCH_SIZE   = 100   # máximo por request en la API gratuita
DELAY_SEG    = 1.1   # respetar rate limit (1 req/seg)


# ---------------------------------------------------------------------------
# Consulta de elevaciones
# ---------------------------------------------------------------------------

def fetch_elevations(points):
    """
    points: lista de (lat, lon)
    Retorna lista de altitudes en metros (float o None si falla).
    """
    locations = "|".join(f"{lat},{lon}" for lat, lon in points)
    url = f"{API_URL}?locations={locations}&interpolation=bilinear"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FEPSA-traza/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        if data.get("status") == "OK":
            return [r.get("elevation") for r in data["results"]]
        else:
            print(f"  ⚠ API error: {data.get('error', 'desconocido')}")
            return [None] * len(points)
    except Exception as e:
        print(f"  ⚠ Request error: {e}")
        return [None] * len(points)


def enriquecer_traza(puntos):
    """Agrega campo ALTITUD a cada punto consultando la API en batches."""
    total = len(puntos)
    print(f"Enriqueciendo {total} puntos con altitud SRTM...")
    print(f"Batches de {BATCH_SIZE} → {math.ceil(total/BATCH_SIZE)} requests")
    print(f"Tiempo estimado: ~{math.ceil(total/BATCH_SIZE)*DELAY_SEG/60:.1f} minutos\n")

    # Cargar progreso previo si existe (para poder reanudar)
    cache_file = "altitud_cache.json"
    cache = {}
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            cache = json.load(f)
        print(f"Cache encontrado: {len(cache)} altitudes ya descargadas\n")

    for i in range(0, total, BATCH_SIZE):
        batch = puntos[i:i+BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = math.ceil(total / BATCH_SIZE)

        # Ver cuántos ya están en cache
        pendientes = [(j, p) for j, p in enumerate(batch)
                      if str(puntos[i+j]['ID']) not in cache]

        if not pendientes:
            print(f"  [{batch_num}/{total_batches}] Batch {i}-{i+len(batch)} — cache completo")
            continue

        coords = [(p['LATITUD'], p['LONGITUD']) for _, p in pendientes]
        print(f"  [{batch_num}/{total_batches}] Consultando puntos {i+1}–{i+len(batch)}...",
              end=" ", flush=True)

        alts = fetch_elevations(coords)

        for (j, p), alt in zip(pendientes, alts):
            cache[str(puntos[i+j]['ID'])] = alt

        # Guardar cache parcial
        with open(cache_file, 'w') as f:
            json.dump(cache, f)

        ok = sum(1 for a in alts if a is not None)
        print(f"OK={ok}/{len(alts)}")

        if batch_num < total_batches:
            time.sleep(DELAY_SEG)

    # Aplicar altitudes a los puntos
    for p in puntos:
        p['ALTITUD'] = cache.get(str(p['ID']))

    # Limpiar cache
    if os.path.exists(cache_file):
        os.remove(cache_file)

    return puntos


# ---------------------------------------------------------------------------
# Exportadores
# ---------------------------------------------------------------------------

def exportar_json(puntos, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(puntos, f, ensure_ascii=False)
    print(f"✓ {path}")


def exportar_geojson(puntos, path):
    features = []
    for p in puntos:
        alt = p.get('ALTITUD') or 0
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [p['LONGITUD'], p['LATITUD'], alt]
            },
            "properties": {
                "id": p['ID'], "km": round(p['KM'], 3),
                "div": p['DIV'], "alt_m": alt
            }
        })
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({"type": "FeatureCollection", "features": features},
                  f, ensure_ascii=False)
    print(f"✓ {path}")


def exportar_kml(puntos, path):
    divs = defaultdict(list)
    for p in puntos:
        divs[p['DIV']].append(p)
    for d in divs:
        divs[d].sort(key=lambda x: x['KM'])

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '  <Document>',
        '    <n>Traza FEPSA con altitud SRTM</n>',
        '    <Style id="via">',
        '      <LineStyle><color>ff0000ff</color><width>2</width></LineStyle>',
        '    </Style>',
    ]
    for div, pts in sorted(divs.items()):
        km_min = round(min(p['KM'] for p in pts), 1)
        km_max = round(max(p['KM'] for p in pts), 1)
        lines.append(f'    <Folder><n>DIV {div} (KM {km_min}–{km_max})</n>')
        coords = ' '.join(
            f"{p['LONGITUD']},{p['LATITUD']},{p.get('ALTITUD') or 0}"
            for p in pts
        )
        lines += [
            f'      <Placemark><n>DIV {div}</n>',
            f'        <styleUrl>#via</styleUrl>',
            f'        <LineString>',
            f'          <altitudeMode>absolute</altitudeMode>',
            f'          <tessellate>1</tessellate>',
            f'          <coordinates>{coords}</coordinates>',
            f'        </LineString>',
            f'      </Placemark>',
            f'    </Folder>',
        ]
    lines += ['  </Document>', '</kml>']
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"✓ {path}")


def exportar_html_perfil(puntos, path):
    """Genera un HTML con gráfico interactivo de perfil altimétrico por DIV."""
    divs = defaultdict(list)
    for p in puntos:
        if p.get('ALTITUD') is not None:
            divs[p['DIV']].append(p)
    for d in divs:
        divs[d].sort(key=lambda x: x['KM'])

    # Preparar datos para el gráfico
    div_data = {}
    for div, pts in sorted(divs.items()):
        div_data[div] = {
            'km':  [round(p['KM'], 3) for p in pts],
            'alt': [round(p['ALTITUD'], 1) for p in pts],
            'km_range': f"{min(p['KM'] for p in pts):.1f}–{max(p['KM'] for p in pts):.1f}"
        }

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Perfil Altimétrico — Red FEPSA</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
  body {{ font-family: monospace; background: #111; color: #eee; margin: 0; padding: 10px; }}
  h1 {{ color: #0af; font-size: 1.2em; }}
  #controls {{ margin: 10px 0; }}
  select {{ background: #222; color: #eee; border: 1px solid #0af; padding: 4px 8px; font-size: 1em; }}
  #info {{ font-size: 0.85em; color: #aaa; margin: 5px 0; }}
  #chart {{ width: 100%; height: 70vh; }}
</style>
</head>
<body>
<h1>📐 Perfil Altimétrico — Red FEPSA (SRTM30m)</h1>
<div id="controls">
  DIV / Ramal:
  <select id="divSel" onchange="renderDiv()">
    {''.join(f'<option value="{d}">{d} (KM {v["km_range"]})</option>' for d,v in sorted(div_data.items()))}
  </select>
</div>
<div id="info"></div>
<div id="chart"></div>

<script>
const DATA = {json.dumps(div_data)};

function pendiente(km1, alt1, km2, alt2) {{
  const distM = (km2 - km1) * 1000;
  if (distM === 0) return 0;
  return ((alt2 - alt1) / distM * 1000).toFixed(1); // ‰
}}

function renderDiv() {{
  const div = document.getElementById('divSel').value;
  const d = DATA[div];
  if (!d) return;

  // Calcular pendientes por segmento
  const pends = [];
  for (let i = 1; i < d.km.length; i++) {{
    pends.push(parseFloat(pendiente(d.km[i-1], d.alt[i-1], d.km[i], d.alt[i])));
  }}
  const maxPend = Math.max(...pends.map(Math.abs)).toFixed(1);
  const altMin  = Math.min(...d.alt).toFixed(0);
  const altMax  = Math.max(...d.alt).toFixed(0);

  document.getElementById('info').innerHTML =
    `Puntos: ${{d.km.length}} &nbsp;|&nbsp; `+
    `Alt: ${{altMin}}–${{altMax}} m &nbsp;|&nbsp; `+
    `Pendiente máx: ${{maxPend}} ‰`;

  const trace = {{
    x: d.km,
    y: d.alt,
    type: 'scatter',
    mode: 'lines',
    line: {{ color: '#00aaff', width: 2 }},
    fill: 'tozeroy',
    fillcolor: 'rgba(0,100,180,0.15)',
    name: 'Altitud (m)',
    hovertemplate: 'KM %{{x}}<br>Alt: %{{y}} m<extra></extra>'
  }};

  const layout = {{
    paper_bgcolor: '#111',
    plot_bgcolor: '#1a1a2e',
    font: {{ color: '#eee', family: 'monospace' }},
    xaxis: {{
      title: 'Punto Kilométrico',
      gridcolor: '#333',
      tickformat: '.1f'
    }},
    yaxis: {{
      title: 'Altitud (m s.n.m.)',
      gridcolor: '#333'
    }},
    margin: {{ t: 20, r: 20, b: 50, l: 60 }},
    showlegend: false
  }};

  Plotly.newPlot('chart', [trace], layout, {{responsive: true}});
}}

renderDiv();
</script>
</body>
</html>"""

    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✓ {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not os.path.exists(TRAZA_FILE):
        print(f"ERROR: No se encuentra {TRAZA_FILE}")
        print("Asegurate de tener el archivo en el mismo directorio que este script.")
        sys.exit(1)

    print(f"Cargando {TRAZA_FILE}...")
    with open(TRAZA_FILE, encoding='utf-8') as f:
        puntos = json.load(f)
    print(f"  {len(puntos)} puntos cargados.\n")

    # Enriquecer con altitudes
    puntos = enriquecer_traza(puntos)

    con_alt = sum(1 for p in puntos if p.get('ALTITUD') is not None)
    print(f"\n{con_alt}/{len(puntos)} puntos con altitud obtenida.\n")

    # Exportar
    print("Generando archivos de salida...")
    exportar_json(puntos, OUT_JSON)
    exportar_geojson(puntos, OUT_GEOJSON)
    exportar_kml(puntos, OUT_KML)
    exportar_html_perfil(puntos, OUT_HTML)

    print(f"""
Listo. Archivos generados:
  {OUT_JSON}      → traza completa con altitudes
  {OUT_GEOJSON}   → para QGIS / OsmAnd / uMap
  {OUT_KML}       → para Maps.me / Google Earth (3D)
  {OUT_HTML}      → perfil interactivo, abrí en el navegador

Abrí {OUT_HTML} en Chrome/Firefox para ver el perfil altimétrico
con pendientes en ‰ por cada DIV/ramal.
""")


if __name__ == '__main__':
    main()