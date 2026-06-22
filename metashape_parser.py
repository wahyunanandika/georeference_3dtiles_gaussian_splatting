# Adapted from dozeri83/geo-register-plugin
# https://github.com/dozeri83/geo-register-plugin
# Original licensed under GPL-3.0
# Modifications by wahyunanandika — June 2026
"""Parse Agisoft Metashape camera XML exports.

Supports two chunk CRS types:
  - GEOGCS (WGS84 / EPSG:4326) — camera <reference> x=lon, y=lat, z=alt
  - PROJCS UTM                  — camera <reference> x=easting, y=northing, z=height
"""

from __future__ import annotations
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path


class MetashapeXMLError(Exception):
    pass


# ─── UTM helpers ──────────────────────────────────────────────────────────────

def _parse_utm_zone(wkt: str) -> tuple[int, bool]:
    """Extract UTM zone number and hemisphere from a PROJCS WKT string.

    Returns (zone_number, is_south).
    Raises MetashapeXMLError if zone cannot be determined.
    """
    m = re.search(r'UTM\s+zone\s+(\d+)([NS])', wkt, re.IGNORECASE)
    if not m:
        raise MetashapeXMLError(
            f"Cannot parse UTM zone from CRS. Expected 'UTM zone NN[NS]' in WKT.\n"
            f"WKT preview: {wkt[:80]}"
        )
    zone_number = int(m.group(1))
    is_south    = m.group(2).upper() == 'S'
    return zone_number, is_south


def _utm_to_ecef(
    easting: float,
    northing: float,
    height: float,
    zone_number: int,
    is_south: bool,
) -> tuple[float, float, float]:
    """Convert UTM (easting, northing, ellipsoidal height) → ECEF XYZ (WGS84)."""
    # WGS84 constants
    a   = 6_378_137.0
    f   = 1.0 / 298.257223563
    b   = a * (1.0 - f)
    e2  = 1.0 - (b / a) ** 2
    ep2 = e2 / (1.0 - e2)

    k0  = 0.9996
    E0  = 500_000.0
    N0  = 10_000_000.0 if is_south else 0.0

    x = easting  - E0
    y = northing - N0

    lon0 = math.radians((zone_number - 1) * 6 - 180 + 3)

    M   = y / k0
    mu  = M / (a * (1.0 - e2/4.0 - 3.0*e2**2/64.0 - 5.0*e2**3/256.0))
    e1  = (1.0 - math.sqrt(1.0 - e2)) / (1.0 + math.sqrt(1.0 - e2))

    phi1 = (mu
            + (3.0*e1/2.0 - 27.0*e1**3/32.0)       * math.sin(2.0*mu)
            + (21.0*e1**2/16.0 - 55.0*e1**4/32.0)  * math.sin(4.0*mu)
            + (151.0*e1**3/96.0)                    * math.sin(6.0*mu)
            + (1097.0*e1**4/512.0)                  * math.sin(8.0*mu))

    sp1  = math.sin(phi1)
    cp1  = math.cos(phi1)
    tp1  = math.tan(phi1)
    N1   = a / math.sqrt(1.0 - e2 * sp1 ** 2)
    T1   = tp1 ** 2
    C1   = ep2 * cp1 ** 2
    R1   = a * (1.0 - e2) / (1.0 - e2 * sp1 ** 2) ** 1.5
    D    = x / (N1 * k0)

    lat = phi1 - (N1 * tp1 / R1) * (
        D**2/2.0
        - (5.0 + 3.0*T1 + 10.0*C1 - 4.0*C1**2 - 9.0*ep2) * D**4/24.0
        + (61.0 + 90.0*T1 + 298.0*C1 + 45.0*T1**2 - 252.0*ep2 - 3.0*C1**2) * D**6/720.0)

    lon = lon0 + (
        D
        - (1.0 + 2.0*T1 + C1) * D**3/6.0
        + (5.0 - 2.0*C1 + 28.0*T1 - 3.0*C1**2 + 8.0*ep2 + 24.0*T1**2) * D**5/120.0
    ) / cp1

    # geodetic → ECEF
    N_lat = a / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
    X = (N_lat + height) * math.cos(lat) * math.cos(lon)
    Y = (N_lat + height) * math.cos(lat) * math.sin(lon)
    Z = (N_lat * (1.0 - e2) + height)   * math.sin(lat)
    return X, Y, Z


# ─── WGS84 helper ─────────────────────────────────────────────────────────────

def _wgs84_to_ecef(lat_deg: float, lon_deg: float, alt_m: float) -> tuple[float, float, float]:
    a  = 6_378_137.0
    e2 = 0.00669437999014
    lr = math.radians(lat_deg)
    lo = math.radians(lon_deg)
    N  = a / math.sqrt(1.0 - e2 * math.sin(lr) ** 2)
    return (
        (N + alt_m) * math.cos(lr) * math.cos(lo),
        (N + alt_m) * math.cos(lr) * math.sin(lo),
        (N * (1.0 - e2) + alt_m)   * math.sin(lr),
    )


# ─── Main parser ──────────────────────────────────────────────────────────────

def parse_metashape_xml(path: str | Path) -> dict:
    """Parse a Metashape camera XML export.

    Supports GEOGCS (WGS84) and PROJCS (UTM) chunk CRS.

    Returns:
        {
          "cameras":          list of {name, ecef: (X,Y,Z), lat, lon, alt}
                              lat/lon/alt are WGS84 geodetic for reference only.
                              For UTM inputs, lat/lon/alt are back-converted from UTM.
          "chunk_transform":  {s, R, t} or None
          "crs_type":         "wgs84" | "utm"
          "utm_zone":         (zone_number, is_south) or None
        }
    """
    tree = ET.parse(str(path))
    root = tree.getroot()

    chunks = [root] if root.tag == "chunk" else root.findall("chunk")
    if not chunks:
        raise MetashapeXMLError("No <chunk> element found in Metashape XML.")

    cameras_out: list[dict] = []
    chunk_transform_out: dict | None = None
    crs_type = "unknown"
    utm_zone = None

    for chunk in chunks:
        chunk_ref = chunk.find("reference")
        if chunk_ref is None or not (chunk_ref.text or "").strip():
            continue

        wkt = chunk_ref.text.strip()

        # ── Detect CRS type ──────────────────────────────────────────────────
        if wkt.startswith("GEOGCS"):
            crs_type = "wgs84"
        elif wkt.startswith("PROJCS") and "UTM" in wkt.upper():
            crs_type = "utm"
            utm_zone = _parse_utm_zone(wkt)
        else:
            crs_preview = wkt[:60].replace("\n", " ")
            raise MetashapeXMLError(
                f"Unsupported chunk CRS: {crs_preview}...\n"
                "Supported: GEOGCS (WGS84) or PROJCS UTM."
            )

        # ── Chunk-level similarity transform (scene → ECEF) ──────────────────
        tf = chunk.find("transform")
        if tf is not None:
            rot_el = tf.find("rotation")
            tra_el = tf.find("translation")
            sca_el = tf.find("scale")
            if rot_el is not None and tra_el is not None and sca_el is not None:
                import numpy as np
                R = np.array(list(map(float, rot_el.text.split()))).reshape(3, 3)
                t = np.array(list(map(float, tra_el.text.split())))
                s = float(sca_el.text.strip())
                chunk_transform_out = {"s": s, "R": R, "t": t}

        # ── Per-camera references ─────────────────────────────────────────────
        cams_el = chunk.find("cameras")
        if cams_el is None:
            continue

        for cam in cams_el.findall("camera"):
            label = cam.get("label", "")
            if not label:
                continue
            ref = cam.find("reference")
            tfm = cam.find("transform")
            if ref is None:
                continue
            if ref.get("enabled", "1") == "0":
                continue

            x_s = ref.get("x")
            y_s = ref.get("y")
            z_s = ref.get("z")
            if x_s is None or y_s is None or z_s is None:
                continue

            x = float(x_s)
            y = float(y_s)
            z = float(z_s)

            try:
                tfm_vals = list(map(float, tfm.text.split())) if tfm is not None else None
                C_scene = None
                if tfm_vals and len(tfm_vals) >= 12:
                    C_scene = [tfm_vals[3], tfm_vals[7], tfm_vals[11]]
            except Exception:
                C_scene = None

            if crs_type == "wgs84":
                # x=lon, y=lat, z=alt
                lat, lon, alt = y, x, z
                ecef = _wgs84_to_ecef(lat, lon, alt)
            else:
                # x=easting, y=northing, z=height (UTM)
                zone_number, is_south = utm_zone
                ecef = _utm_to_ecef(x, y, z, zone_number, is_south)
                # back-convert to lat/lon for reference
                import numpy as np
                ex, ey, ez = ecef
                a_val = 6_378_137.0; e2_val = 0.00669437999014
                lon_r = math.atan2(ey, ex)
                p     = math.sqrt(ex**2 + ey**2)
                lat_r = math.atan2(ez, p*(1-e2_val))
                for _ in range(10):
                    N_v = a_val / math.sqrt(1-e2_val*math.sin(lat_r)**2)
                    lat_r = math.atan2(ez + e2_val*N_v*math.sin(lat_r), p)
                N_v  = a_val / math.sqrt(1-e2_val*math.sin(lat_r)**2)
                alt  = p/math.cos(lat_r) - N_v
                lat  = math.degrees(lat_r)
                lon  = math.degrees(lon_r)

            cameras_out.append({
                "name":    Path(label).stem,
                "lat":     lat,
                "lon":     lon,
                "alt":     alt,
                "ecef":    ecef,
                "C_scene": C_scene,
            })

    if not cameras_out:
        raise MetashapeXMLError(
            "No cameras with GPS reference found in Metashape XML. "
            f"CRS type detected: {crs_type}. "
            "Make sure cameras have <reference> tags with x, y, z attributes."
        )

    return {
        "cameras":         cameras_out,
        "chunk_transform": chunk_transform_out,
        "crs_type":        crs_type,
        "utm_zone":        utm_zone,
    }
