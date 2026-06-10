# gs_georef

Standalone Python pipeline — no LichtFeld Studio required — that converts a
3D Gaussian Splatting PLY file into georeferenced **3D Tiles 1.1** (SPZ-compressed)
ready for **Cesium ion** or any CesiumJS-based viewer.

## Requirements

```bash
pip install -r requirements.txt  # numpy only
```

## Inputs

| File | Description |
|---|---|
| `splat.ply` | Binary little-endian 3DGS PLY from COLMAP training |
| `sparse/0/images.bin` | COLMAP sparse reconstruction cameras |
| `camera_export.xml` | Metashape camera export — chunk CRS **must** be WGS84 / EPSG:4326 |
| `sparse/0/points3D.bin` | *(optional)* COLMAP sparse points — for terrain altitude verification |

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

## Tested on

| Dataset | Splats | Cameras | Tiles | GPS RMSE | Drone alt | Terrain alt |
|---|---|---|---|---|---|---|
| Taman Kota Cimahi, Jawa Barat | 4,999,683 | 341 PPK | 463 | 0.076 m | 917 m | ~813 m |

## Troubleshooting

**"Only N matched cameras"** — stems in `images.bin` must match XML camera labels.
Check with:
```bash
python -c "from colmap_reader import read_images_bin; c=read_images_bin('sparse/0/images.bin'); print(list(c)[:5])"
python -c "from metashape_parser import parse_metashape_xml; d=parse_metashape_xml('cam.xml'); print([c['name'] for c in d['cameras'][:5]])"
```

**"No chunk-level transform"** — re-export from Metashape with chunk CRS = WGS84 (EPSG:4326).
