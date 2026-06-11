# gs_georef

Standalone Python pipeline for converting 3D Gaussian Splatting reconstructions into georeferenced 3D Tiles 1.1 (SPZ-compressed) without requiring LichtFeld Studio.

The pipeline estimates a similarity transform directly from COLMAP camera centres and GPS camera references exported from Metashape, then exports the Gaussian Splat scene as Cesium-compatible 3D Tiles.

## Features

* Direct COLMAP → ECEF georeferencing
* No LichtFeld Studio dependency
* SPZ-compressed Gaussian Splats
* 3D Tiles 1.1 output
* Cesium ion compatible
* Octree-based spatial tiling
* Optional sparse-point validation using COLMAP `points3D.bin`
* Fully reproducible command-line workflow

---

## Tested Result

Dataset: Taman Kota Cimahi, Indonesia

* 4,999,683 Gaussian splats
* 341 GPS PPK cameras
* GPS RMSE: 0.076 m
* Cesium terrain offset: +0.27 m
* 463 octree tiles

---

## Pipeline Overview

```text
COLMAP images.bin
        │
        ▼
 Camera Centres
        │
        ├────────────┐
        ▼            │
Similarity Solver    │
        ▲            │
        │            │
Metashape GPS Cameras
        │
        ▼
Transform Matrix
        │
        ▼
Gaussian Splat PLY
        │
        ▼
Octree Tiling
        │
        ▼
SPZ Encoding
        │
        ▼
3D Tiles 1.1
        │
        ▼
Cesium ion / CesiumJS
```

---

## Requirements

```bash
pip install -r requirements.txt
```

Current dependency:

```text
numpy >= 1.24
```

---

## Inputs

| File                  | Description                                 |
| --------------------- | ------------------------------------------- |
| splat.ply             | Binary Gaussian Splat PLY                   |
| sparse/0/images.bin   | COLMAP camera reconstruction                |
| camera_export.xml     | Metashape camera export (WGS84 / EPSG:4326) |
| sparse/0/points3D.bin | Optional sparse point cloud for validation  |

---

## Usage

### 1. Solve Similarity Transform

```bash
python solve_transform.py \
    --images-bin sparse/0/images.bin \
    --metashape camera_export.xml \
    --output similarity_transform.json
```

Optional terrain verification:

```bash
python solve_transform.py \
    --images-bin sparse/0/images.bin \
    --metashape camera_export.xml \
    --points3d sparse/0/points3D.bin \
    --output similarity_transform.json
```

Example output:

```text
343 cameras read
341 GPS cameras loaded
68,502 sparse points read

Matched 341 cameras
RMSE = 0.0762 m
Scale = 1.00000000
```

---

### 2. Export 3D Tiles

```bash
python tiles_exporter.py \
    splat.ply \
    similarity_transform.json \
    output_tiles/
```

Options:

| Parameter             | Description                  |
| --------------------- | ---------------------------- |
| --max-sh-degree       | Maximum SH degree            |
| --max-splats-per-tile | Override auto tiling         |
| --min-tile-size       | Minimum octree cell size     |
| --fraction            | Subsample splats for testing |

---

### 3. Verify Export

```bash
python verify_tileset.py output_tiles/
```

Example:

```text
OK geometricError
OK refine == REPLACE
OK altitude range
OK KHR_gaussian_splatting

READY TO UPLOAD
```

---

### 4. Upload to Cesium ion

1. Open Cesium ion
2. Add Data
3. Select 3D Tiles
4. Upload the generated output_tiles directory

---

## Validation Dataset

| Metric        | Value             |
| ------------- | ----------------- |
| Dataset       | Taman Kota Cimahi |
| Splats        | 4,999,683         |
| Cameras       | 341 GPS PPK       |
| Tiles         | 463               |
| GPS RMSE      | 0.076 m           |
| Cesium Offset | +0.27 m           |

---

## Limitations

Currently validated on:

* Drone photogrammetry datasets
* Metashape camera exports
* WGS84 (EPSG:4326)

Future work:

* UTM CRS support
* Automatic CRS detection
* Adaptive octree subdivision
* Multi-resolution Gaussian Splat LOD
* 3D Tiles Next / implicit tiling

---

## Acknowledgements

This project builds upon ideas and implementations from:

* dozeri83/geo-register-plugin
* Niantic SPZ

The following components were adapted from geo-register-plugin:

* SPZ encoding
* Similarity transform estimation
* Metashape XML parsing
* 3D Tiles export structure

Special thanks to dozeri83 for creating and maintaining geo-register-plugin, which served as the foundation and inspiration for this work.

---

## License

GPL-3.0

SPZ encoder implementation follows the Niantic SPZ specification (MIT License).
