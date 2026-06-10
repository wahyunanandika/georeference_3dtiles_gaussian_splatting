"""Parse Agisoft Metashape camera XML exports.

Extracts per-camera GPS references, scene-space camera centres, and the
chunk-level similarity transform (COLMAP/scene → ECEF).
"""

from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np


class MetashapeXMLError(Exception):
    pass


def parse_metashape_xml(path: str | Path) -> dict:
    """Parse a Metashape camera XML export.

    Returns a dict with keys:
        cameras       : list of {name, lat, lon, alt, C_scene}
        chunk_transform : {s, R, t}  — similarity that maps scene-space → ECEF
    """
    tree = ET.parse(str(path))
    root = tree.getroot()

    chunks = [root] if root.tag == "chunk" else root.findall("chunk")
    if not chunks:
        raise MetashapeXMLError("No <chunk> element found in Metashape XML.")

    cameras_out: list[dict] = []
    chunk_transform_out: dict | None = None

    for chunk in chunks:
        chunk_ref = chunk.find("reference")
        if chunk_ref is None or not (chunk_ref.text or "").strip():
            continue
        wkt = chunk_ref.text.strip()
        if not wkt.startswith("GEOGCS"):
            continue

        # ── chunk-level similarity transform (scene → ECEF) ──────────────
        tf = chunk.find("transform")
        if tf is not None:
            rot_el = tf.find("rotation")
            tra_el = tf.find("translation")
            sca_el = tf.find("scale")
            if rot_el is not None and tra_el is not None and sca_el is not None:
                R = np.array(list(map(float, rot_el.text.split()))).reshape(3, 3)
                t = np.array(list(map(float, tra_el.text.split())))
                s = float(sca_el.text.strip())
                chunk_transform_out = {"s": s, "R": R, "t": t}

        # ── per-camera GPS + scene-space centre ───────────────────────────
        cams_el = chunk.find("cameras")
        if cams_el is None:
            continue

        for cam in cams_el.findall("camera"):
            label = cam.get("label", "")
            if not label:
                continue
            ref = cam.find("reference")
            tfm = cam.find("transform")
            if ref is None or tfm is None:
                continue
            if ref.get("enabled", "1") == "0":
                continue

            x_s = ref.get("x")
            y_s = ref.get("y")
            z_s = ref.get("z")
            if x_s is None or y_s is None or z_s is None:
                continue

            try:
                vals = list(map(float, tfm.text.split()))
                C_scene = np.array([vals[3], vals[7], vals[11]])
            except Exception:
                continue

            cameras_out.append({
                "name":    Path(label).stem,
                "lat":     float(y_s),
                "lon":     float(x_s),
                "alt":     float(z_s),
                "C_scene": C_scene,
            })

    if not cameras_out:
        raise MetashapeXMLError(
            "No cameras with GPS reference found in Metashape XML. "
            "Make sure the chunk CRS is GEOGCS (WGS84 / EPSG:4326)."
        )

    return {"cameras": cameras_out, "chunk_transform": chunk_transform_out}
