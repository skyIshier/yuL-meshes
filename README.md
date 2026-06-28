本仓库所有脚本文件都是鱼L制作，我只负责发布

Sky: Children of the Light - .meshes 转换工具

概述

这是一个用于解析、转换和编辑《光·遇》(Sky: Children of the Light) 游戏 .meshes 模型文件的工具集。支持将二进制模型文件转换为可读的 JSON 格式，以及从 Wavefront OBJ 文件导入模型。

---

功能特性

· 解析 .meshes 文件 → 完整的 JSON 表示
· 生成 .meshes 文件 → 从 JSON 重建二进制文件
· OBJ 导入 → 将标准 Wavefront OBJ 模型转换为 Sky 格式
· 完整的几何数据保留：顶点位置、法线、材质分配、光照系数、AABB 包围盒、区块结构
· 自动构建依赖：首次运行时自动编译 meshoptimizer 编解码器

---

文件结构

```
├── 20.py              # 核心转换器（主程序）
├── 27.py              # OBJ → .meshes 一键转换脚本
├── meshoptimizer.h    # meshoptimizer 头文件
├── meshopt_codec.c    # 编解码器 CLI 包装
├── vertexcodec.cpp    # meshoptimizer 顶点编解码实现
└── 1.txt              # 材质 ID 参考表
```

---

依赖

Python 包

```
# 仅 LZ4 解压需要（LOD0 部分），核心功能不需要
pip install lz4
```

编译依赖

· GCC / Clang（用于编译 meshopt_codec）

---

安装

```bash
# 克隆或下载所有文件到同一目录
# 首次运行任何命令时会自动编译 meshopt_codec
```

---

使用方法

1. .meshes → JSON 转换

```bash
python 20.py to-json input.meshes [output.json]
```

示例：

```bash
python 20.py to-json BstBaked.meshes model.json
```

输出： 包含完整几何数据的 JSON 文件

---

2. JSON → .meshes 转换

```bash
python 20.py to-meshes input.json [output.meshes]
```

示例：

```bash
python 20.py to-meshes model.json output.meshes
```

---

3. OBJ 导入到 JSON

```bash
python 20.py import-obj input.json input.obj [output.json]
```

示例：

```bash
python 20.py import-obj model.json model.obj model_imported.json
```

交互式提示：

· 主材质 ID：输入 0-255 的整数（参考下方材质表）
· 副材质 ID：输入 0-255（通常为 0）

导入特性：

· 自动计算顶点法线
· 自动计算 AABB 包围盒
· 自动将面分组到区块（≤255 顶点，≤255 三角形）
· 使用游戏标准光照系数（输入漫反射、光照强度等）

---

4. OBJ → .meshes 一键转换

```bash
python 27.py input.obj
```

交互式提示：

· 材质 ID（参考材质表）
· 版本（3C 或 3D）

输出： BstBaked.meshes（当前目录）

---

JSON 数据结构

顶层结构

```json
{
  "magic": "LVL0",
  "version": 60,
  "minBound": [-10.5, -5.2, -8.1],
  "maxBound": [10.5, 5.2, 8.1],
  "_sectionOrder": ["GEO0", "LOD0"],
  "_firstSectionOffset": 136,
  "sections": {
    "GEO0": { ... },
    "LOD0": { ... }
  }
}
```

GEO0 章节（几何数据）

```json
{
  "indexCount": 12345,
  "vertexCount": 6789,
  "chunkCount": 30,
  "depthChunkCount": 0,
  "subchunkCount": 30,
  "vertices": [
    {
      "pos": [1.0, 2.0, 3.0],
      "normal": [127, 0, 0, 0],
      "materials": [5, 0, 0, 0],
      "materialWeights": [255, 0, 0, 0],
      "unk": [3204448256, 2151677952, 101711872]
    }
  ],
  "indices": [0, 1, 2, ...],
  "chunks": [...],
  "subchunks": [...]
}
```

顶点格式（36 字节）

偏移 大小 字段 说明
0 12 pos 位置 (float3)
12 4 normal 法线 (R8_SNORM × 4)
16 4 materials 材质 ID (UNORM8 × 4)
20 4 materialWeights 材质权重 (UNORM8 × 4)
24 12 unk 光照系数 (uint32 × 3)

---

材质 ID 参考表

ID 名称
0 kMaterial_None
2 kMaterial_Transparent
3 kMaterial_Void
4 kMaterial_Particle
5 kMaterial_WoodSlippery
6 kMaterial_VoidMinor
7 kMaterial_WoodPlank
16 kMaterial_Cliff
17 kMaterial_Soil
18 kMaterial_CliffLight
19 kMaterial_WallDamaged
20 kMaterial_Wall
21 kMaterial_Gold
22 kMaterial_Glacier
23 kMaterial_TileCeiling
24 kMaterial_TileFloor
25 kMaterial_TileWall
26 kMaterial_WallBrick
27 kMaterial_SoilWet
28 kMaterial_CliffWet
29 kMaterial_Bone
30 kMaterial_Wood
31 kMaterial_Ceramics
32 kMaterial_Sand
33 kMaterial_SandWet
34 kMaterial_SandLight
35 kMaterial_Snow
36 kMaterial_SandDeep
37 kMaterial_Mud
48 kMaterial_Grass
49 kMaterial_GrassWet
50 kMaterial_GrassLight
51 kMaterial_GrassMoss
52 kMaterial_Cloth
80 kMaterial_Cloud

---

文件格式说明

TOC（目录表）

```
+0x00: "LVL0" (4B)
+0x04: version (4B, uint32)
+0x08: entry_count (1B)
+0x09: padding (3B)
+0x0C: entries[] (12B each)
  +0x00: type (4B, e.g. "GEO0")
  +0x04: offset (4B)
  +0x08: size (4B)
+...: minBound (12B, float3)
+...: maxBound (12B, float3)
```

GEO0 章节

```
+0x00: indexCount (4B)
+0x04: vertexCount (4B)
+0x08: chunkCount (4B)
+0x0C: depthChunkCount (4B)
+0x10: subchunkCount (4B)
+0x14: compressedSize (4B) [if vertexCount > 0]
+0x18: compressed vertex data (meshopt)
+...: index buffer (indexCount bytes)
+...: chunks[] (56B each)
+...: subchunks[] (8B each)
```

Chunk 结构（56 字节）

偏移 大小 字段
0 4 idxStart
4 4 vtxStart
8 4 areaStart
12 2 idxCount
14 1 vtxCount
15 1 areaCount
16 12 min (float3)
28 12 max (float3)
40 16 unk (uint32 × 4)

Subchunk 结构（8 字节）

偏移 大小 字段
0 1 materialId
1 1 triangleCount
2 1 vtxCount
3 1 triangleStart
4 1 triangleEnd
5 1 vtxStart
6 1 vtxEnd
7 1 unk

---

编译细节

工具会自动编译 meshopt_codec 用于顶点数据的编解码：

```bash
gcc -c -O2 -o _vtxcodec.o vertexcodec.cpp
gcc -O2 -o meshopt_codec meshopt_codec.c _vtxcodec.o
```

编译产物保存在系统临时目录（$TMPDIR / $TMP / $HOME / /tmp）。

---

注意事项

1. 顶点大小固定为 36 字节（Sky 的标准顶点格式）
2. 区块限制：每个区块最多 255 个顶点和 255 个三角形
3. 索引大小为 1 字节（uint8_t），因此每个区块的顶点数不能超过 255
4. LOD0 章节目前仅作为占位数据保留
5. 版本 0x3C（60）和 0x3D（61）经过测试均可工作
6. OBJ 导入时会自动进行空间排序以提高区块效率

---

故障排除

"meshopt_codec not available"

· 确保 GCC 已安装
· 确保所有源文件（.c、.cpp、.h）在同一目录
· 首次运行时会自动编译

"Subchunk field must be 0-255"

· JSON 中的 subchunk 数据溢出 8 位范围
· 使用 import-obj 重新导入 OBJ 文件

LZ4 解压失败

· 安装 lz4 包：pip install lz4
· LOD0 数据仅作为占位，不影响模型几何

---

许可证

本项目为独立工具，基于 meshoptimizer（MIT 许可证）。

---

参考资料

· meshoptimizer - 顶点/索引缓冲区的压缩与优化库
· 光·遇 - 游戏官方网站
