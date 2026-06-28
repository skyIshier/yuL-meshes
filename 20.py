#!/usr/bin/env python3
"""
Sky: Children of the Light — .meshes ↔ JSON 转换器 / OBJ 导入
所有数据完整保留，支持往返转换。

用法:
  python 20.py to-json <输入.meshes> [输出.json]
  python 20.py to-meshes <输入.json> [输出.meshes]
  python 20.py import-obj <输入.json> <输入.obj> [输出.json]
"""

import struct
import sys
import os
import json
import base64
import subprocess

_script_dir = os.path.dirname(os.path.abspath(__file__))
_RUN_BASE = os.environ.get('TMPDIR') or os.environ.get('TMP') or os.environ.get('HOME') or '/tmp'
_CODEC_BIN = os.path.join(_RUN_BASE, 'meshopt_codec')


# ─── meshopt codec auto-build ─────────────────────────────────────────────────

def _ensure_codec():
    if os.access(_CODEC_BIN, os.X_OK):
        return _CODEC_BIN
    src_c = os.path.join(_script_dir, 'meshopt_codec.c')
    src_cpp = os.path.join(_script_dir, 'vertexcodec.cpp')
    src_h = os.path.join(_script_dir, 'meshoptimizer.h')
    if not (os.path.exists(src_c) and os.path.exists(src_cpp) and os.path.exists(src_h)):
        return None
    import subprocess as sp
    obj = os.path.join(_script_dir, '_vtxcodec.o')
    tmp = os.path.join(_script_dir, '_meshopt_codec')
    print("Building meshopt_codec from source...")
    r1 = sp.run(['gcc', '-c', '-O2', '-o', obj, src_cpp], capture_output=True, text=True)
    if r1.returncode != 0:
        print(f"  compile error: {r1.stderr.strip()}")
        return None
    r2 = sp.run(['gcc', '-O2', '-o', tmp, src_c, obj], capture_output=True, text=True)
    os.remove(obj)
    if r2.returncode != 0:
        print(f"  link error: {r2.stderr.strip()}")
        return None
    try:
        os.rename(tmp, _CODEC_BIN)
    except OSError:
        import shutil
        shutil.copy(tmp, _CODEC_BIN)
        os.remove(tmp)
    os.chmod(_CODEC_BIN, 0o755)
    print(f"  built: {_CODEC_BIN}")
    return _CODEC_BIN


# ─── meshopt encode / decode ──────────────────────────────────────────────────

def meshopt_decode(compressed: bytes, vertex_count: int, vertex_size: int = 36) -> bytes:
    """Decompress vertex buffer using meshopt_codec."""
    codec = _ensure_codec()
    if codec is None:
        raise RuntimeError("meshopt_codec not available")
    proc = subprocess.run(
        [codec, 'decode', str(vertex_count), str(vertex_size)],
        input=struct.pack('<I', len(compressed)) + compressed,
        capture_output=True, timeout=120
    )
    if proc.returncode != 0:
        raise RuntimeError(f"meshopt decode failed: {proc.stderr.decode()}")
    return proc.stdout


def meshopt_encode(decompressed: bytes, vertex_count: int, vertex_size: int = 36) -> bytes:
    """Compress vertex buffer using meshopt_codec. Returns [u32 size][data]."""
    codec = _ensure_codec()
    if codec is None:
        raise RuntimeError("meshopt_codec not available")
    proc = subprocess.run(
        [codec, 'encode', str(vertex_count), str(vertex_size)],
        input=decompressed,
        capture_output=True, timeout=120
    )
    if proc.returncode != 0:
        raise RuntimeError(f"meshopt encode failed: {proc.stderr.decode()}")
    return proc.stdout  # [u32 compressed_size][compressed_data]


# ─── Vertex struct (36 bytes) ─────────────────────────────────────────────────

def pack_vertex(pos, normal, materials, material_weights, unk):
    """Pack a vertex dict into 36 bytes."""
    buf = struct.pack('<3f', pos[0], pos[1], pos[2])
    buf += bytes(normal[:4])
    buf += bytes(materials[:4])
    buf += bytes(material_weights[:4])
    for u in unk[:3]:
        buf += struct.pack('<I', u)
    return buf


def unpack_vertex(data: bytes, offset: int = 0):
    """Unpack a 36-byte vertex record into a dict."""
    x, y, z = struct.unpack_from('<3f', data, offset)
    normal = list(data[offset + 12:offset + 16])
    materials = list(data[offset + 16:offset + 20])
    weights = list(data[offset + 20:offset + 24])
    unk = [
        struct.unpack_from('<I', data, offset + 24)[0],
        struct.unpack_from('<I', data, offset + 28)[0],
        struct.unpack_from('<I', data, offset + 32)[0],
    ]
    return {
        'pos': [x, y, z],
        'normal': normal,
        'materials': materials,
        'materialWeights': weights,
        'unk': unk
    }


# ─── Chunk struct (56 bytes) ─────────────────────────────────────────────────

def pack_chunk(c):
    """Pack chunk dict into 56 bytes."""
    buf = struct.pack('<III', c['idxStart'], c['vtxStart'], c['areaStart'])
    buf += struct.pack('<H', c['idxCount'])
    buf += struct.pack('<B', c['vtxCount'])
    buf += struct.pack('<B', c['areaCount'])
    mn = c['min']
    mx = c['max']
    buf += struct.pack('<3f', mn[0], mn[1], mn[2])
    buf += struct.pack('<3f', mx[0], mx[1], mx[2])
    for u in c['unk']:
        buf += struct.pack('<I', u)
    return buf


def unpack_chunk(data: bytes, offset: int = 0):
    """Unpack a 56-byte chunk record into a dict."""
    idxStart = struct.unpack_from('<I', data, offset)[0]
    vtxStart = struct.unpack_from('<I', data, offset + 4)[0]
    areaStart = struct.unpack_from('<I', data, offset + 8)[0]
    idxCount = struct.unpack_from('<H', data, offset + 12)[0]
    vtxCount = data[offset + 14]
    areaCount = data[offset + 15]
    mn = list(struct.unpack_from('<3f', data, offset + 16))
    mx = list(struct.unpack_from('<3f', data, offset + 28))
    unk = [
        struct.unpack_from('<I', data, offset + 40)[0],
        struct.unpack_from('<I', data, offset + 44)[0],
        struct.unpack_from('<I', data, offset + 48)[0],
        struct.unpack_from('<I', data, offset + 52)[0],
    ]
    return {
        'idxStart': idxStart,
        'vtxStart': vtxStart,
        'areaStart': areaStart,
        'idxCount': idxCount,
        'vtxCount': vtxCount,
        'areaCount': areaCount,
        'min': mn,
        'max': mx,
        'unk': unk
    }


# ─── Subchunk struct (8 bytes) ────────────────────────────────────────────────

def pack_subchunk(s):
    """Pack subchunk dict into 8 bytes."""
    return struct.pack('<8B',
        s['materialId'], s['triangleCount'], s['vtxCount'],
        s['triangleStart'], s['triangleEnd'],
        s['vtxStart'], s['vtxEnd'], s['unk']
    )


def unpack_subchunk(data: bytes, offset: int = 0):
    """Unpack an 8-byte subchunk record into a dict."""
    return {
        'materialId': data[offset],
        'triangleCount': data[offset + 1],
        'vtxCount': data[offset + 2],
        'triangleStart': data[offset + 3],
        'triangleEnd': data[offset + 4],
        'vtxStart': data[offset + 5],
        'vtxEnd': data[offset + 6],
        'unk': data[offset + 7]
    }


# ─── GEO section ──────────────────────────────────────────────────────────────

def parse_geo_to_json(geo_data: bytes) -> dict:
    """Parse GEO section binary → JSON-serializable dict."""
    indexCount = struct.unpack_from('<I', geo_data, 0)[0]
    vertexCount = struct.unpack_from('<I', geo_data, 4)[0]
    chunkCount = struct.unpack_from('<I', geo_data, 8)[0]
    depthChunkCount = struct.unpack_from('<I', geo_data, 12)[0]
    subchunkCount = struct.unpack_from('<I', geo_data, 16)[0]

    total_chunks = chunkCount + depthChunkCount
    pos = 20
    vertices = []
    compressed_size = 0

    if vertexCount > 0:
        compressed_size = struct.unpack_from('<I', geo_data, pos)[0]
        pos += 4
        compressed = geo_data[pos:pos + compressed_size]
        pos += compressed_size

        print(f"  Decompressing {vertexCount} vertices ({compressed_size} bytes)...")
        decompressed = meshopt_decode(compressed, vertexCount, 36)
        for v in range(vertexCount):
            vertices.append(unpack_vertex(decompressed, v * 36))

    # Index buffer
    index_buffer = list(geo_data[pos:pos + indexCount])
    pos += indexCount

    # Chunks
    chunks = []
    for i in range(total_chunks):
        chunks.append(unpack_chunk(geo_data, pos + i * 56))
    pos += total_chunks * 56

    # Subchunks
    subchunks = []
    for i in range(subchunkCount):
        subchunks.append(unpack_subchunk(geo_data, pos + i * 8))
    pos += subchunkCount * 8

    return {
        'indexCount': indexCount,
        'vertexCount': vertexCount,
        'chunkCount': chunkCount,
        'depthChunkCount': depthChunkCount,
        'subchunkCount': subchunkCount,
        'compressedVertexSize': compressed_size,
        'vertices': vertices,
        'indices': index_buffer,
        'chunks': chunks,
        'subchunks': subchunks
    }


def build_geo_from_json(geo: dict) -> bytes:
    """Build GEO section binary from JSON dict (optimized for speed)."""
    vertexCount = geo['vertexCount']
    indexCount = geo['indexCount']
    chunkCount = geo['chunkCount']
    depthChunkCount = geo['depthChunkCount']
    subchunkCount = geo['subchunkCount']

    buf = struct.pack('<5I', indexCount, vertexCount, chunkCount,
                      depthChunkCount, subchunkCount)

    if vertexCount > 0:
        # 预分配 bytearray，避免反复拼接
        raw_verts = bytearray(vertexCount * 36)
        offset = 0
        for v in geo['vertices']:
            packed = pack_vertex(
                v['pos'], v['normal'],
                v['materials'], v['materialWeights'], v['unk']
            )
            raw_verts[offset:offset + 36] = packed
            offset += 36
        print(f"  Compressing {vertexCount} vertices...")
        compressed = meshopt_encode(bytes(raw_verts), vertexCount, 36)
        # meshopt_encode 返回的已经包含 [u32 size][data]
        buf += compressed
    else:
        buf += struct.pack('<I', 0)

    # Index buffer
    buf += bytes(geo['indices'])

    # Chunks
    for c in geo['chunks']:
        buf += pack_chunk(c)

    # Subchunks — 保持原有的范围校验
    for i, s in enumerate(geo['subchunks']):
        for field in ['materialId', 'triangleCount', 'vtxCount',
                      'triangleStart', 'triangleEnd', 'vtxStart', 'vtxEnd']:
            val = s.get(field, 0)
            if not (0 <= val <= 255):
                raise ValueError(
                    f"Subchunk[{i}].{field} = {val} (must be 0-255). "
                    f"JSON 中的 subchunk 数据溢出 u08 范围。"
                    f"请用 import-obj 重新导入 OBJ。")
        buf += pack_subchunk(s)

    return buf


# ─── TOC ──────────────────────────────────────────────────────────────────────

def parse_toc(data: bytes) -> tuple:
    """Parse TOC. Returns (version, entries, min_bound, max_bound, toc_end_pos)."""
    version = struct.unpack_from('<I', data, 4)[0]
    entry_count = data[8]
    entries = []
    for i in range(entry_count):
        base = 12 + i * 12
        name = data[base:base + 4].rstrip(b'\x00').decode('ascii', errors='replace')
        offset = struct.unpack_from('<I', data, base + 4)[0]
        size = struct.unpack_from('<I', data, base + 8)[0]
        entries.append({'type': name, 'offset': offset, 'size': size})
    # minBound and maxBound come after the last entry
    toc_items_end = 12 + entry_count * 12
    min_bound = list(struct.unpack_from('<3f', data, toc_items_end))
    max_bound = list(struct.unpack_from('<3f', data, toc_items_end + 12))
    toc_end = toc_items_end + 24
    return version, entries, min_bound, max_bound, toc_end


def build_toc(version: int, entries: list, min_bound: list, max_bound: list) -> bytes:
    """Build TOC binary."""
    buf = b'LVL0'
    buf += struct.pack('<I', version)
    buf += struct.pack('<B', len(entries))
    buf += b'\x00' * 3  # padding to align
    for e in entries:
        name = e['type'].ljust(4, '\x00')[:4]
        buf += name.encode('ascii')
        buf += struct.pack('<I', e['offset'])
        buf += struct.pack('<I', e['size'])
    buf += struct.pack('<3f', *min_bound)
    buf += struct.pack('<3f', *max_bound)
    return buf


# ─── Main converter ───────────────────────────────────────────────────────────

def meshes_to_json(inp: str, out: str):
    """Convert .meshes → JSON."""
    with open(inp, 'rb') as f:
        data = f.read()

    if data[0:4] != b'LVL0':
        print(f"Error: bad magic {data[0:4]}")
        sys.exit(1)

    version, entries, min_bound, max_bound, toc_end = parse_toc(data)
    print(f"Version: {version} (0x{version:x})")
    print(f"TOC entries: {len(entries)}")
    for e in entries:
        print(f"  {e['type']}: offset=0x{e['offset']:x} size=0x{e['size']:x}")

    result = {
        'magic': 'LVL0',
        'version': version,
        'minBound': min_bound,
        'maxBound': max_bound,
        '_sectionOrder': [e['type'] for e in entries],
        '_firstSectionOffset': entries[0]['offset'] if entries else 0x88,
        'sections': {},
    }

    for e in entries:
        name = e['type']
        offset = e['offset']
        size = e['size']
        if size == 0:
            result['sections'][name] = None
            continue

        raw = data[offset:offset + size]

        if name == 'GEO0':
            print(f"\nParsing GEO section ({size} bytes)...")
            geo = parse_geo_to_json(raw)
            result['sections'][name] = geo
            print(f"  GEO: {geo['vertexCount']} vertices, {geo['indexCount']} indices, "
                  f"{len(geo['chunks'])} chunks, {len(geo['subchunks'])} subchunks")

        elif name == 'LOD0':
            print(f"\nStoring LOD section ({size} bytes, LZ4-compressed)")
            try:
                import lz4.block
                decompressed = lz4.block.decompress(raw, uncompressed_size=0xC00000)
                result['sections'][name] = {
                    '_compressed': base64.b64encode(raw).decode('ascii'),
                    '_decompressedSize': len(decompressed),
                    '_note': 'LZ4-compressed; contains generic mesh refs and cloud data'
                }
            except Exception as e:
                result['sections'][name] = {
                    '_raw': base64.b64encode(raw).decode('ascii'),
                    '_note': f'Raw bytes (LZ4 decompress failed: {e})'
                }

        elif name == 'METR':
            print(f"\nStoring METR section ({size} bytes)")
            result['sections'][name] = {
                '_raw': base64.b64encode(raw).decode('ascii'),
                '_size': size
            }

        else:
            result['sections'][name] = {
                '_raw': base64.b64encode(raw).decode('ascii')
            }

    with open(out, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nJSON saved: {out}")


def json_to_meshes(inp: str, out: str):
    """Convert JSON → .meshes."""
    with open(inp, 'r', encoding='utf-8') as f:
        data = json.load(f)

    version = data['version']
    min_bound = data['minBound']
    max_bound = data['maxBound']
    sections = data['sections']
    section_order = data.get('_sectionOrder', list(sections.keys()))
    first_offset = data.get('_firstSectionOffset', None)

    # Build section binaries
    section_binaries = {}
    for name, sec in sections.items():
        if sec is None:
            section_binaries[name] = b''
            continue

        if name == 'GEO0':
            print(f"Building GEO section...")
            section_binaries[name] = build_geo_from_json(sec)

        elif name == 'LOD0':
            print(f"Building LOD section...")
            if '_compressed' in sec:
                section_binaries[name] = base64.b64decode(sec['_compressed'])
            elif '_raw' in sec:
                section_binaries[name] = base64.b64decode(sec['_raw'])
            else:
                raise ValueError("LOD section has no compressed/raw data")

        elif name == 'METR':
            if '_raw' in sec:
                section_binaries[name] = base64.b64decode(sec['_raw'])
            else:
                section_binaries[name] = b''

        else:
            if '_raw' in sec:
                section_binaries[name] = base64.b64decode(sec['_raw'])
            else:
                section_binaries[name] = b''

    # Build entries in preserved order
    entries = []
    current_offset = first_offset if first_offset else (12 + len(section_binaries) * 12 + 24)
    # Align
    current_offset = (current_offset + 3) & ~3

    for name in section_order:
        if name in section_binaries:
            bin_data = section_binaries[name]
            entries.append({'type': name, 'offset': current_offset, 'size': len(bin_data)})
            current_offset += len(bin_data)

    # Include any sections not in the order list
    for name in section_binaries:
        if name not in section_order:
            bin_data = section_binaries[name]
            entries.append({'type': name, 'offset': current_offset, 'size': len(bin_data)})
            current_offset += len(bin_data)

    # Build TOC
    toc = build_toc(version, entries, max_bound, min_bound)
    # Pad TOC so first section starts at the correct offset
    target = entries[0]['offset'] if entries else len(toc)
    while len(toc) < target:
        toc += b'\x00'

    if entries:
        assert entries[0]['offset'] >= len(toc), \
            f"TOC overflow: {len(toc)} > first offset {entries[0]['offset']}"

    # Assemble
    output = toc
    for e in entries:
        name = e['type']
        bin_data = section_binaries[name]
        output += bin_data
        print(f"  {name}: offset=0x{e['offset']:x} size=0x{e['size']:x} ({e['size']} bytes)")

    with open(out, 'wb') as f:
        f.write(output)
    print(f"\n.meshes saved: {out}")
    print(f"Total: {len(output)} bytes")


# ─── OBJ Import ───────────────────────────────────────────────────────────────

def load_obj(obj_path: str):
    """Parse Wavefront OBJ, return (vertices, faces).
    vertices: list of (x, y, z) tuples
    faces: list of (i0, i1, i2) 0-based vertex indices
    """
    verts = []
    faces = []
    with open(obj_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if parts[0] == 'v':
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif parts[0] == 'f':
                idxs = []
                for p in parts[1:]:
                    # handle f v/vt/vn or f v//vn or just f v
                    vi = int(p.split('/')[0])
                    idxs.append(vi - 1 if vi > 0 else len(verts) + vi)
                if len(idxs) >= 3:
                    faces.append((idxs[0], idxs[1], idxs[2]))
    return verts, faces


def compute_normals(verts, faces):
    """Compute per-vertex normals by averaging face normals."""
    import math
    normals = [(0.0, 0.0, 0.0)] * len(verts)
    for f in faces:
        i0, i1, i2 = f
        if i0 >= len(verts) or i1 >= len(verts) or i2 >= len(verts):
            continue
        p0, p1, p2 = verts[i0], verts[i1], verts[i2]
        u = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        v = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
        nx = u[1] * v[2] - u[2] * v[1]
        ny = u[2] * v[0] - u[0] * v[2]
        nz = u[0] * v[1] - u[1] * v[0]
        length = math.sqrt(nx * nx + ny * ny + nz * nz)
        if length > 0.0001:
            nx, ny, nz = nx / length, ny / length, nz / length
        normals[i0] = (normals[i0][0] + nx, normals[i0][1] + ny, normals[i0][2] + nz)
        normals[i1] = (normals[i1][0] + nx, normals[i1][1] + ny, normals[i1][2] + nz)
        normals[i2] = (normals[i2][0] + nx, normals[i2][1] + ny, normals[i2][2] + nz)
    # Normalize
    result = []
    for n in normals:
        length = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
        if length > 0.0001:
            result.append((n[0] / length, n[1] / length, n[2] / length))
        else:
            result.append((0.0, 0.0, 1.0))
    return result


def snorm_byte(f: float) -> int:
    """Convert float [-1,1] to R8_SNORM byte (signed 8-bit, binary complement)."""
    v = max(-1.0, min(1.0, f))
    scaled = round(v * 127.0)
    return scaled & 0xFF


def float_to_unorm8(f: float) -> int:
    """Convert float in [0,1] to UNORM8 byte (0-255)"""
    return max(0, min(255, int(round(f * 255.0))))


def import_obj_to_json(json_path: str, obj_path: str, out_path: str):
    """Import an OBJ mesh into a meshes JSON file, with proper lighting coefficients."""
    print(f"Loading JSON: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if 'GEO0' not in data.get('sections', {}) or data['sections']['GEO0'] is None:
        print("Error: JSON has no GEO0 section. Creating empty GEO section.")
        data['sections']['GEO0'] = {
            'indexCount': 0, 'vertexCount': 0,
            'chunkCount': 0, 'depthChunkCount': 0, 'subchunkCount': 0,
            'compressedVertexSize': 0, 'vertices': [], 'indices': [],
            'chunks': [], 'subchunks': []
        }

    geo = data['sections']['GEO0']

    print(f"Loading OBJ: {obj_path}")
    obj_verts, obj_faces = load_obj(obj_path)   # returns (vertices list, faces list of 3 indices)
    print(f"  OBJ: {len(obj_verts)} vertices, {len(obj_faces)} triangles")

    if not obj_verts or not obj_faces:
        print("Error: OBJ is empty")
        sys.exit(1)

    # ── Interactive material prompts ──
    print()
    print("── 导入几何体的材质设置 ──")
    try:
        mat_id = int(input("  主材质ID (0-255): ") or "0")
    except (EOFError, ValueError):
        mat_id = 0
    try:
        mat_id2 = int(input("  副材质ID (0=无): ") or "0")
    except (EOFError, ValueError):
        mat_id2 = 0
    # 材质权重固定为完全使用主材质
    print("  → materialWeights = [255, 0, 0, 0] (fixed)")
    print()

    # Compute vertex normals
    print("Computing vertex normals...")
    normals = compute_normals(obj_verts, obj_faces)

    # ── Lighting coefficients (based on game's typical values) ──
    # input2 = (0.99, 0.99, 0.99, 0.99)
    # input3 = (0.5,  0.5,  0.5,  0.5)
    # input4 = (0.04, 0.004,0.004,0.004)
    unk0 = (float_to_unorm8(0.99) << 24) | (float_to_unorm8(0.99) << 16) | (float_to_unorm8(0.99) << 8) | float_to_unorm8(0.99)
    unk1 = (float_to_unorm8(0.5)  << 24) | (float_to_unorm8(0.5)  << 16) | (float_to_unorm8(0.5)  << 8) | float_to_unorm8(0.5)
    unk2 = (float_to_unorm8(0.04) << 24) | (float_to_unorm8(0.004) << 16) | (float_to_unorm8(0.004) << 8) | float_to_unorm8(0.004)
    lighting_unk = [unk0, unk1, unk2]

    # Build per-vertex data (temporary, will be reordered per chunk later)
    new_vertices = []
    for i, pos in enumerate(obj_verts):
        n = normals[i]
        new_vertices.append({
            'pos': [pos[0], pos[1], pos[2]],
            'normal': [snorm_byte(n[0]), snorm_byte(n[1]), snorm_byte(n[2]), 0],
            'materials': [mat_id, mat_id2, 0, 0],
            'materialWeights': [255, 0, 0, 0],   # full weight on primary material
            'unk': lighting_unk
        })

    # ── Group faces into chunks (max 255 vertices, 255 triangles) ──
    MAX_VTX = 255
    MAX_TRI = 255

    # Spatial sort of faces (Z, then X, then Y)
    face_centroids = []
    for fi, f in enumerate(obj_faces):
        i0, i1, i2 = f
        if i0 < len(obj_verts) and i1 < len(obj_verts) and i2 < len(obj_verts):
            cx = (obj_verts[i0][0] + obj_verts[i1][0] + obj_verts[i2][0]) / 3.0
            cy = (obj_verts[i0][1] + obj_verts[i1][1] + obj_verts[i2][1]) / 3.0
            cz = (obj_verts[i0][2] + obj_verts[i1][2] + obj_verts[i2][2]) / 3.0
        else:
            cx = cy = cz = 0.0
        face_centroids.append((cx, cy, cz, fi))
    face_centroids.sort(key=lambda c: (c[2], c[0], c[1]))

    # Greedy packing
    chunk_faces = []      # list of list of face indices
    chunk_vert_sets = []  # list of set of vertex indices
    current_faces = []
    current_verts = set()
    for cx, cy, cz, fi in face_centroids:
        f = obj_faces[fi]
        f_verts = set(f)
        merged_verts = current_verts | f_verts
        merged_tris = len(current_faces) + 1
        if len(merged_verts) <= MAX_VTX and merged_tris <= MAX_TRI:
            current_faces.append(fi)
            current_verts = merged_verts
        else:
            if current_faces:
                chunk_faces.append(current_faces)
                chunk_vert_sets.append(current_verts)
            current_faces = [fi]
            current_verts = f_verts
    if current_faces:
        chunk_faces.append(current_faces)
        chunk_vert_sets.append(current_verts)

    print(f"  Packed into {len(chunk_vert_sets)} chunk(s) "
          f"(≤{MAX_VTX}v, ≤{MAX_TRI}t each)")

    # ── Build final vertex blocks (per chunk) and indices ──
    new_vertices_chunked = []   # vertices in chunk order
    new_indices = []
    new_chunks = []
    new_subchunks = []

    base_vtx = geo['vertexCount']
    base_idx = geo['indexCount']
    base_area = geo['subchunkCount']

    for ci, vset in enumerate(chunk_vert_sets):
        # Determine local vertex order (sorted deterministic)
        local_order = sorted(vset)
        local_index = {gvi: li for li, gvi in enumerate(local_order)}

        # Collect vertex data in local order
        chunk_vertices = [new_vertices[gvi] for gvi in local_order]
        vtx_start = base_vtx + len(new_vertices_chunked)
        new_vertices_chunked.extend(chunk_vertices)

        # Build index buffer (local indices)
        idx_buffer = []
        for fi in chunk_faces[ci]:
            i0, i1, i2 = obj_faces[fi]
            if i0 in local_index and i1 in local_index and i2 in local_index:
                idx_buffer.extend([local_index[i0], local_index[i1], local_index[i2]])

        tri_count = len(idx_buffer) // 3
        if tri_count == 0:
            print(f"  Warning: Chunk {ci} has no faces, skipping")
            continue

        # Compute AABB from original vertex positions
        positions = [obj_verts[gvi] for gvi in local_order]
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        zs = [p[2] for p in positions]
        aabb_min = [min(xs), min(ys), min(zs)]
        aabb_max = [max(xs), max(ys), max(zs)]

        new_chunks.append({
            'idxStart': base_idx + len(new_indices),
            'vtxStart': vtx_start,
            'areaStart': base_area + len(new_subchunks),
            'idxCount': len(idx_buffer),
            'vtxCount': len(chunk_vertices),
            'areaCount': 1,
            'min': aabb_min,
            'max': aabb_max,
            'unk': [0, 0, 0, 0],
        })
        new_indices.extend(idx_buffer)

        # Subchunk (one per chunk)
        new_subchunks.append({
            'materialId': mat_id,
            'triangleCount': tri_count,
            'vtxCount': len(chunk_vertices),
            'triangleStart': 0,
            'triangleEnd': tri_count - 1,
            'vtxStart': 0,
            'vtxEnd': len(chunk_vertices) - 1,
            'unk': 0,
        })

        print(f"  Chunk {ci}: {len(chunk_vertices)}v {tri_count}t  "
              f"min=[{aabb_min[0]:.1f},{aabb_min[1]:.1f},{aabb_min[2]:.1f}]")

    if not new_chunks:
        print("Error: no valid chunks generated")
        sys.exit(1)

    total_new_vtx = len(new_vertices_chunked)
    total_new_idx = len(new_indices)
    print(f"\nImporting {total_new_vtx} vertices, {total_new_idx} indices "
          f"→ {len(new_chunks)} chunks, {len(new_subchunks)} subchunks")

    # ── Append to existing GEO data ──
    geo['vertices'].extend(new_vertices_chunked)
    geo['indices'].extend(new_indices)
    geo['chunks'].extend(new_chunks)
    geo['subchunks'].extend(new_subchunks)

    # Update counts
    geo['vertexCount'] = len(geo['vertices'])
    geo['indexCount'] = len(geo['indices'])
    geo['chunkCount'] = len(geo['chunks'])
    geo['subchunkCount'] = len(geo['subchunks'])

    print(f"\nUpdated GEO: {geo['vertexCount']}v {geo['indexCount']}i "
          f"{geo['chunkCount']} chunks {geo['subchunkCount']} subchunks")

    # Write output JSON
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nJSON saved: {out_path}")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python 20.py to-json <input.meshes> [output.json]")
        print("  python 20.py to-meshes <input.json> [output.meshes]")
        print("  python 20.py import-obj <input.json> <input.obj> [output.json]")
        sys.exit(1)

    cmd = sys.argv[1]
    inp = sys.argv[2]

    if cmd == 'to-json':
        out = sys.argv[3] if len(sys.argv) > 3 else inp.rsplit('.', 1)[0] + '.json'
        meshes_to_json(inp, out)

    elif cmd == 'to-meshes':
        out = sys.argv[3] if len(sys.argv) > 3 else inp.rsplit('.', 1)[0] + '.meshes'
        json_to_meshes(inp, out)

    elif cmd == 'import-obj':
        if len(sys.argv) < 4:
            print("Usage: python 20.py import-obj <input.json> <input.obj> [output.json]")
            sys.exit(1)
        obj_path = sys.argv[3]
        out = sys.argv[4] if len(sys.argv) > 4 else inp.rsplit('.', 1)[0] + '_imported.json'
        import_obj_to_json(inp, obj_path, out)

    else:
        print(f"Unknown command: {cmd}")
        print("Use 'to-json', 'to-meshes', or 'import-obj'")
        sys.exit(1)


if __name__ == '__main__':
    main()
