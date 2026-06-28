#!/usr/bin/env python3
"""
Convert an OBJ file directly to a Sky .meshes file (BstBaked.meshes).

Usage:
  python obj2meshes.py <input.obj>

Prompts for material ID and version (3C or 3D).
Requires: 20.py (with the bounds order fix) in the same directory.
"""

import sys
import os
import json
import subprocess
import tempfile
import base64

# Fixed LOD0 data from levelLod.js (18 bytes)
LOD0_RAW = bytes.fromhex("1B000100C0010000000000000000000000")
LOD0_B64 = base64.b64encode(LOD0_RAW).decode('ascii')

def run_converter(args, input_data=None):
    cmd = [sys.executable, '20.py'] + args
    proc = subprocess.run(cmd, capture_output=True, text=True, input=input_data)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise RuntimeError(f"20.py failed with code {proc.returncode}")
    return proc.stdout

def build_initial_json(version_hex: int) -> dict:
    """Create a minimal JSON with empty GEO0 and a valid LOD0 segment."""
    return {
        "magic": "LVL0",
        "version": version_hex,
        "minBound": [0.0, 0.0, 0.0],
        "maxBound": [0.0, 0.0, 0.0],
        "_sectionOrder": ["GEO0", "LOD0"],
        "_firstSectionOffset": 0x88,
        "sections": {
            "GEO0": {
                "indexCount": 0,
                "vertexCount": 0,
                "chunkCount": 0,
                "depthChunkCount": 0,
                "subchunkCount": 0,
                "compressedVertexSize": 0,
                "vertices": [],
                "indices": [],
                "chunks": [],
                "subchunks": []
            },
            "LOD0": {
                "_raw": LOD0_B64,
                "_size": len(LOD0_RAW)
            }
        }
    }

def compute_global_bounds(geo: dict) -> tuple:
    verts = geo.get('vertices', [])
    if not verts:
        return [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    xs = [v['pos'][0] for v in verts]
    ys = [v['pos'][1] for v in verts]
    zs = [v['pos'][2] for v in verts]
    return [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_obj = sys.argv[1]
    if not os.path.isfile(input_obj):
        print(f"Error: file '{input_obj}' not found")
        sys.exit(1)

    # Material ID
    try:
        mat_id = input("Enter main material ID (0-255, default 0): ").strip()
        mat_id = int(mat_id) if mat_id else 0
        if not 0 <= mat_id <= 255:
            raise ValueError
    except (EOFError, ValueError):
        print("Invalid input, must be an integer between 0 and 255.")
        sys.exit(1)

    # Version
    try:
        ver_str = input("Enter version (3C or 3D, default 3C): ").strip().upper()
        if not ver_str:
            ver_str = "3C"
        if ver_str not in ("3C", "3D"):
            raise ValueError
        version = int(ver_str, 16)
    except (EOFError, ValueError):
        print("Invalid input, must be '3C' or '3D'.")
        sys.exit(1)

    print(f"Processing {input_obj} with material ID {mat_id}, version 0x{version:02X}...")

    initial_data = build_initial_json(version)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(initial_data, f, indent=2)
        initial_json = f.name

    imported_json = None
    try:
        # 1. Import OBJ
        print("  Importing OBJ into JSON...")
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp_out:
            imported_json = tmp_out.name

        stdin_input = f"{mat_id}\n0\n"
        run_converter(['import-obj', initial_json, input_obj, imported_json],
                      input_data=stdin_input)

        # 2. Update global bounds
        print("  Updating global bounds...")
        with open(imported_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        geo = data.get('sections', {}).get('GEO0')
        if not geo:
            raise RuntimeError("GEO0 section missing after import")
        minb, maxb = compute_global_bounds(geo)
        data['minBound'] = minb
        data['maxBound'] = maxb
        with open(imported_json, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        # 3. Convert to .meshes
        output_file = "BstBaked.meshes"
        print(f"  Generating {output_file}...")
        run_converter(['to-meshes', imported_json, output_file])

        print(f"Done. Output: {output_file}")

    finally:
        for f in [initial_json, imported_json]:
            if f and os.path.exists(f):
                os.remove(f)

if __name__ == '__main__':
    main()