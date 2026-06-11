# gs_georef

Standalone Python pipeline — **no LichtFeld Studio required** — that converts a
3D Gaussian Splatting PLY file into georeferenced **3D Tiles 1.1** (SPZ-compressed)
ready for **Cesium ion** or any CesiumJS-based viewer.

**Confirmed result on Taman Kota Cimahi dataset: +0.27m offset vs terrain in Cesium ion.**

---

## Based on / Credits

This pipeline is heavily inspired by and derived from
**[dozeri83/geo-register-plugin](https://github.com/dozeri83/geo-register-plugin)** —
a LichtFeld Studio plugin for georeferencing 3D Gaussian Splat scenes.

Core components inherited from dozeri83:

| Component | Origin |
|---|---|
| `spz_encode.py` | Pure-Python SPZ v3 encoder, mirrors Niantic's load-spz.cc byte-for-byte |
| GLB writer (`_write_spz_glb`) | KHR_gaussian_splatting + KHR_gaussian_splatting_compression_spz_2 structure |
| Umeyama + RANSAC solver | robust_umeyama implementation |
| Metashape XML parser | parse_metashape_xml, GEOGCS/EPSG:4326 chunk handling |
| 3D Tiles 1.1 structure | tileset.json schema, geometricError, refine semantics |

**Thank you dozeri83** for the original plugin that made this work possible.

---

## What Changed and Why

### 1. Removed LichtFeld Studio dependency

**dozeri83 original:** requires LFS to be running; similarity transform is solved
from `node.camera_R/T` (LFS camera API) → scene-space positions.

**This pipeline:** reads COLMAP `images.bin` directly. No LFS needed.

**Why:** LFS v0.5.2 (PR #1066) introduced a split between `visualizer-world` and
`data-world` coordinate conventions. `node.world_transform` no longer reliably
returns the data-world transform needed for PLY export. Additionally, LFS cannot
load COLMAP cameras and a PLY splat simultaneously (mutually exclusive modes),
making it impossible to get `node.world_transform` from PLY converter mode.

### 2. Direct COLMAP → ECEF transform (no scene-space intermediate)

**dozeri83 original:** solve similarity from LFS camera API positions (Metashape
scene space, Z ≈ 0–2) → ECEF.

**This pipeline:** solve directly from COLMAP camera centres (from `images.bin`,
Z ≈ 900–920m for Cimahi) → GPS ECEF (from Metashape XML `<reference>` tags).

**Why:** PLY splats and COLMAP camera centres share the same coordinate space.
Solving directly skips the scene-space intermediate and eliminates the need for
`node.world_transform` (W). Result: +0.27m terrain offset vs ~677m floating in
the original LFS approach.

### 3. Removed `diag(1, -1, -1)` flip from tileset matrix

**dozeri83 original:** applies `M = M @ diag(1, -1, -1, 1)` to convert from LFS
visualizer-world (Y-up, Z-backward) to ECEF.

**This pipeline:** flip removed entirely.

**Why:** COLMAP output space has a different axis convention from LFS world-space.
Applying the LFS flip to COLMAP positions inverts the Z axis, causing bbox center
altitude to become negative (~-781m). Without the flip, terrain altitude is correct.

### 4. Added octree tiling

**dozeri83 original:** single-tile export — all splats in one GLB file.

**This pipeline:** octree spatial partitioning → hundreds of leaf tiles.

**Why:** a single tile with 5M splats produces a very large `geometricError` on a
leaf node. Cesium computes high SSE but cannot refine → tile skipped entirely.
Octree splitting with correct per-node `geometricError` (0.0 for leaves, bbox
diagonal for internal nodes) makes Cesium render tiles progressively.

### 5. Fixed `geometricError` (no scale multiplication)

**dozeri83 original (initial):** `geom_err_m = scene_diagonal * scale`

**This pipeline:** `geom_err_m = float(np.linalg.norm(pmax - pmin))`

**Why:** `geometricError` is in local tile space; the transform matrix handles
the coordinate change. Multiplying by scale produced values ~12.79× too large.

### 6. Fixed `refine: "ADD"` → `"REPLACE"`

**Why:** `ADD` requires parent LOD splats + child splats. For single-level splat
exports without an LOD hierarchy, `REPLACE` is the only correct option.

### 7. Added `points3D.bin` reader (optional verification)

Reads COLMAP sparse points to verify terrain altitude after applying the similarity
transform — confirms the transform is correct before the full tile export.

---

## Requirements

```bash
pip install -r requirements.txt  # numpy only
```

---

## Inputs

| File | Description |
|---|---|
| `splat.ply` | Binary little-endian 3DGS PLY from COLMAP training |
| `sparse/0/images.bin` | COLMAP sparse reconstruction cameras |
| `camera_export.xml` | Metashape camera export — chunk CRS **must** be WGS84 / EPSG:4326 |
| `sparse/0/points3D.bin` | *(optional)* COLMAP sparse points — for terrain altitude verification |

**Metashape export:** File → Export → Export Cameras → set chunk coordinate system
to **WGS84 (EPSG:4326)**. Camera label stems in `images.bin` must match XML labels.

---

## Usage

### Step 1 — Solve similarity transform

```bash
python solve_transform.py \
    --images-bin  sparse/0/images.bin \
    --metashape   camera_export.xml \
    --output      similarity_transform.json

# With terrain altitude verification:
python solve_transform.py \
    --images-bin  sparse/0/images.bin \
    --metashape   camera_export.xml \
    --points3d    sparse/0/points3D.bin \
    --output      similarity_transform.json
```

Expected output:
```
  343 cameras read.
  341 GPS cameras loaded.
  68,502 sparse points read.
  Matched 341 cameras (COLMAP ↔ Metashape XML)
  Solver: 341/341 inliers, RMSE=0.0762 m
  Camera centroid → lat=-6.87067, lon=107.55432, alt=917.19 m (drone altitude)
  Sparse points → terrain alt: 790.6–839.2 m (mean=812.8 m)
```

### Step 2 — Export 3D Tiles

```bash
python tiles_exporter.py \
    splat.ply \
    similarity_transform.json \
    output_tiles/
```

Options: `--max-sh-degree 0|1|2|3`, `--max-splats-per-tile INT`,
`--min-tile-size FLOAT`, `--fraction FLOAT`

### Step 3 — Verify

```bash
python verify_tileset.py output_tiles/
```

### Step 4 — Upload to Cesium ion

Add data → 3D Tiles → upload `output_tiles/` folder.

**Optional height offset** if some splats clip into terrain:
```javascript
tileset.modelMatrix = Cesium.Matrix4.multiplyByTranslation(
  tileset.modelMatrix,
  new Cesium.Cartesian3(0, 0, 5),
  new Cesium.Matrix4()
);
```

---

## Confirmed Results

| Metric | dozeri83 LFS plugin | This pipeline |
|---|---|---|
| Cesium offset vs terrain | ~677m floating ❌ | **+0.27m** ✅ |
| Splat alt (Cesium) | ~1594m | 798.82m |
| Terrain alt (Cesium) | ~917m | 798.55m |
| GPS RMSE | 0.076m | 0.076m |
| LFS required | Yes | **No** |
| Reproducible | Depends on LFS version | Always same |

---

## File structure

```
gs_georef/
├── solve_transform.py    # Step 1: solve similarity
├── tiles_exporter.py     # Step 2: PLY → 3D Tiles
├── verify_tileset.py     # Step 3: sanity-check
├── colmap_reader.py      # reads images.bin + points3D.bin
├── metashape_parser.py   # reads Metashape camera XML
├── transform_solver.py   # Umeyama + RANSAC solver
├── spz_encode.py         # SPZ v3 binary encoder
├── requirements.txt
├── README.md
├── STANDALONE_PIPELINE.md
└── PIPELINE_DEBUG_LOG.md
```

---

## Tested on

| Dataset | Splats | Cameras | Tiles | GPS RMSE | Drone alt | Terrain alt | Cesium offset |
|---|---|---|---|---|---|---|---|
| Taman Kota Cimahi, Jawa Barat | 4,999,683 | 341 PPK | 463 | 0.076 m | 917 m | ~813 m | **+0.27m** |

---

## Troubleshooting

**"Only N matched cameras"** — stems in `images.bin` must match XML camera labels.
Check with:
```bash
python -c "from colmap_reader import read_images_bin; c=read_images_bin('sparse/0/images.bin'); print(list(c)[:5])"
python -c "from metashape_parser import parse_metashape_xml; d=parse_metashape_xml('cam.xml'); print([c['name'] for c in d['cameras'][:5]])"
```

**"No chunk-level transform"** — re-export from Metashape with chunk CRS = WGS84 (EPSG:4326).

**Large scenes (>3km)** — use `--max-splats-per-tile` to increase tile count.

---

## License

GPL-3.0 (inherited from dozeri83/geo-register-plugin).

SPZ encoder (`spz_encode.py`) derived from [Niantic spz](https://github.com/nianticlabs/spz) — MIT license.
