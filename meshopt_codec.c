/* meshopt vertex buffer codec helper (decode + encode)
 * Usage:
 *   meshopt_codec decode <vertex_count> <vertex_size>
 *     stdin:  [u32 compressed_size][compressed data...]
 *     stdout: decompressed vertex buffer
 *
 *   meshopt_codec encode <vertex_count> <vertex_size>
 *     stdin:  decompressed vertex buffer (vertex_count * vertex_size bytes)
 *     stdout: [u32 compressed_size][compressed data...]
 */

#include "meshoptimizer.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif

int main(int argc, char** argv) {
#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    if (argc != 4) {
        fprintf(stderr, "Usage: %s <decode|encode> <vertex_count> <vertex_size>\n", argv[0]);
        return 1;
    }

    int decode = (strcmp(argv[1], "decode") == 0);
    size_t vertex_count = (size_t)atoll(argv[2]);
    size_t vertex_size = (size_t)atoll(argv[3]);

    if (vertex_size == 0 || vertex_size > 256 || vertex_size % 4 != 0) {
        fprintf(stderr, "Invalid vertex_size: %zu\n", vertex_size);
        return 1;
    }

    if (decode) {
        uint32_t compressed_size;
        if (fread(&compressed_size, 1, 4, stdin) != 4) {
            fprintf(stderr, "Failed to read compressed size\n");
            return 1;
        }
        unsigned char* compressed = (unsigned char*)malloc(compressed_size);
        if (!compressed || fread(compressed, 1, compressed_size, stdin) != compressed_size) {
            fprintf(stderr, "Failed to read compressed data\n");
            free(compressed);
            return 1;
        }
        size_t out_size = vertex_count * vertex_size;
        unsigned char* output = (unsigned char*)malloc(out_size);
        if (!output) {
            fprintf(stderr, "Failed to allocate output\n");
            free(compressed);
            return 1;
        }
        int r = meshopt_decodeVertexBuffer(output, vertex_count, vertex_size,
                                            compressed, compressed_size);
        if (r != 0) {
            fprintf(stderr, "meshopt_decodeVertexBuffer failed: %d\n", r);
            free(compressed); free(output);
            return 1;
        }
        fwrite(output, 1, out_size, stdout);
        fflush(stdout);
        free(compressed); free(output);
    } else {
        size_t in_size = vertex_count * vertex_size;
        unsigned char* input = (unsigned char*)malloc(in_size);
        if (!input || fread(input, 1, in_size, stdin) != in_size) {
            fprintf(stderr, "Failed to read input data\n");
            free(input);
            return 1;
        }
        // worst-case compressed size
        size_t max_comp = in_size + in_size / 4 + 256;
        unsigned char* compressed = (unsigned char*)malloc(max_comp);
        if (!compressed) {
            fprintf(stderr, "Failed to allocate compression buffer\n");
            free(input);
            return 1;
        }
        size_t comp_size = meshopt_encodeVertexBuffer(compressed, max_comp,
                                                       input, vertex_count, vertex_size);
        if (comp_size == 0) {
            fprintf(stderr, "meshopt_encodeVertexBuffer failed\n");
            free(input); free(compressed);
            return 1;
        }
        uint32_t sz = (uint32_t)comp_size;
        fwrite(&sz, 1, 4, stdout);
        fwrite(compressed, 1, comp_size, stdout);
        fflush(stdout);
        free(input); free(compressed);
    }
    return 0;
}
