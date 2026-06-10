"""Quick sanity-check for a finished tileset.

Usage
-----
python verify_tileset.py path/to/out_dir/
"""

from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path


def ecef_to_lla(x, y, z):
    import math
    a = 6_378_137.0
    e2 = 0.00669437999014
    lon = math.degrees(math.atan2(y, x))
    p   = math.sqrt(x*x + y*y)
    lat = math.degrees(math.atan2(z, p * (1.0 - e2)))
    for _ in range(10):
        lr  = math.radians(lat)
        N   = a / math.sqrt(1.0 - e2 * math.sin(lr)**2)
        lat = math.degrees(math.atan2(z + e2 * N * math.sin(lr), p))
    lr  = math.radians(lat)
    N   = a / math.sqrt(1.0 - e2 * math.sin(lr)**2)
    alt = p / math.cos(lr) - N
    return lat, lon, alt


def check(label, ok, detail=""):
    status = "✅" if ok else "❌"
    print(f"  {status}  {label}" + (f"  ({detail})" if detail else ""))
    return ok


def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_tileset.py <out_dir>")
        sys.exit(1)

    out_dir = Path(sys.argv[1])
    passed = 0
    total  = 0

    # ── tileset.json ──────────────────────────────────────────────────────────
    ts_path = out_dir / "tileset.json"
    if not ts_path.exists():
        print(f"ERROR: {ts_path} not found.")
        sys.exit(1)

    with open(ts_path) as f:
        ts = json.load(f)

    print("\n── tileset.json ──────────────────────────────")

    ge_root = ts.get("geometricError", 0)
    box     = ts["root"]["boundingVolume"]["box"]
    hx, hy, hz = box[3], box[7], box[11]
    diag    = math.sqrt((hx*2)**2 + (hy*2)**2 + (hz*2)**2)
    refine  = ts["root"].get("refine", "?")
    n_children = len(ts["root"].get("children", []))

    T = ts["root"].get("transform", [])
    if T:
        import numpy as np
        M   = np.array(T).reshape(4, 4).T
        tx, ty, tz = M[0, 3], M[1, 3], M[2, 3]
        scale_m    = float(np.linalg.norm(M[:3, 0]))
        lat, lon, alt = ecef_to_lla(tx, ty, tz)
    else:
        scale_m = 1.0
        lat = lon = alt = 0.0

    def c(label, ok, detail=""):
        nonlocal passed, total
        total += 1
        if ok:
            passed += 1
        return check(label, ok, detail)

    c("geometricError == bbox diagonal",
      abs(ge_root - diag) < 0.1,
      f"{ge_root:.2f} vs {diag:.2f}")
    c("refine == REPLACE",
      refine == "REPLACE",
      refine)
    c("has children (tiled)",
      n_children > 0,
      f"{n_children} children")
    c("transform scale ≈ 1.0",
      abs(scale_m - 1.0) < 0.01,
      f"{scale_m:.6f}")
    c("latitude plausible",
      -90 < lat < 90,
      f"{lat:.5f}°")
    c("longitude plausible",
      -180 < lon < 180,
      f"{lon:.5f}°")
    c("altitude 0–5000 m",
      0 < alt < 5000,
      f"{alt:.1f} m")

    print(f"\n  Scene origin: lat={lat:.5f}, lon={lon:.5f}, alt={alt:.1f} m")

    # ── GLB tiles ─────────────────────────────────────────────────────────────
    tiles = sorted(out_dir.glob("tile_*.glb"))
    print(f"\n── GLB tiles ({len(tiles)}) ────────────────────────────")

    if tiles:
        with open(tiles[0], "rb") as f:
            magic  = struct.unpack("<I", f.read(4))[0]
            ver    = struct.unpack("<I", f.read(4))[0]
            _total = struct.unpack("<I", f.read(4))[0]
            clen   = struct.unpack("<I", f.read(4))[0]
            _ctype = f.read(4)
            gltf   = json.loads(f.read(clen))

        c("GLB magic correct",
          magic == 0x46546C67,
          hex(magic))
        c("glTF version 2",
          ver == 2,
          str(ver))
        ext = gltf["meshes"][0]["primitives"][0].get("extensions", {})
        c("KHR_gaussian_splatting present",
          "KHR_gaussian_splatting" in ext)
        node_matrix = gltf["nodes"][0].get("matrix", [])
        c("Y-up node matrix",
          len(node_matrix) == 16 and abs(node_matrix[5] - (-1.0)) < 1e-6,
          str(node_matrix[5] if len(node_matrix) >= 6 else "?"))

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n── Summary ───────────────────────────────────")
    print(f"  {passed}/{total} checks passed")
    if passed == total:
        print("  ✅ READY TO UPLOAD TO CESIUM ION")
    else:
        print("  ⚠️  Fix the failing checks before uploading.")
    print()


if __name__ == "__main__":
    main()
