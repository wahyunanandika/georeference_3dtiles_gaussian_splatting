"""Read camera centre positions and sparse 3D points from COLMAP binary files.

COLMAP images.bin binary layout
--------------------------------
u64   num_images
for each image:
    u32   image_id
    f64   qw, qx, qy, qz   (world-to-camera quaternion)
    f64   tx, ty, tz        (world-to-camera translation)
    u32   camera_id
    str   name              (null-terminated)
    u64   num_points2D
    for each point2D:
        f64 x, f64 y, i64 point3D_id

COLMAP points3D.bin binary layout
-----------------------------------
u64   num_points
for each point:
    u64   point3D_id
    f64   x, y, z
    u8    r, g, b
    f64   error
    u64   track_length
    for each track element:
        u32 image_id, u32 point2D_idx
"""

from __future__ import annotations
import struct
from pathlib import Path
import numpy as np


def _quat_to_rot(qw: float, qx: float, qy: float, qz: float) -> np.ndarray:
    """Quaternion (w,x,y,z) → 3×3 rotation matrix (world-to-camera)."""
    n = qw*qw + qx*qx + qy*qy + qz*qz
    if n < 1e-12:
        return np.eye(3)
    s = 2.0 / n
    wx, wy, wz = qw*qx*s, qw*qy*s, qw*qz*s
    xx, xy, xz = qx*qx*s, qx*qy*s, qx*qz*s
    yy, yz, zz = qy*qy*s, qy*qz*s, qz*qz*s
    return np.array([
        [1 - (yy+zz),     xy - wz,      xz + wy],
        [    xy + wz,  1 - (xx+zz),     yz - wx],
        [    xz - wy,      yz + wx,  1 - (xx+yy)],
    ])


def read_images_bin(path: str | Path) -> dict[str, np.ndarray]:
    """Return {image_stem: camera_center_xyz} from COLMAP images.bin.

    Camera centre in COLMAP world space: C = -R^T @ T
    """
    path = Path(path)
    cameras: dict[str, np.ndarray] = {}

    with open(path, "rb") as f:
        num_images, = struct.unpack("<Q", f.read(8))

        for _ in range(num_images):
            image_id, = struct.unpack("<I", f.read(4))
            qw, qx, qy, qz = struct.unpack("<4d", f.read(32))
            tx, ty, tz      = struct.unpack("<3d", f.read(24))
            camera_id,      = struct.unpack("<I", f.read(4))

            name_bytes = b""
            while True:
                ch = f.read(1)
                if ch == b"\x00" or not ch:
                    break
                name_bytes += ch
            name = name_bytes.decode("utf-8", errors="replace")

            num_pts, = struct.unpack("<Q", f.read(8))
            f.read(num_pts * 24)

            R = _quat_to_rot(qw, qx, qy, qz)
            T = np.array([tx, ty, tz])
            C = -(R.T @ T)

            stem = Path(name).stem
            cameras[stem] = C

    return cameras


def read_points3d_bin(path: str | Path) -> np.ndarray:
    """Return (N, 3) float64 array of 3D point XYZ from COLMAP points3D.bin.

    These points are in the same COLMAP world space as camera centres from
    read_images_bin, and in the same space as the PLY splat positions.
    Useful for verifying that a similarity transform places terrain at the
    correct geodetic altitude before running the full tile export.
    """
    path = Path(path)
    coords: list[np.ndarray] = []

    with open(path, "rb") as f:
        num_pts, = struct.unpack("<Q", f.read(8))
        for _ in range(num_pts):
            struct.unpack("<Q", f.read(8))          # point3D_id
            xyz = struct.unpack("<3d", f.read(24))
            f.read(3)                               # rgb
            f.read(8)                               # error
            track_len, = struct.unpack("<Q", f.read(8))
            f.read(track_len * 8)                   # track
            coords.append(np.array(xyz))

    return np.array(coords, dtype=np.float64)
