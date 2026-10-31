# Changelog
The changelog only includes what's new. To read feature descriptions, see [Features](https://github.com/codefl0w/unsuper?tab=readme-ov-file#features).

# [3.0.0] - 01.11.2026

### Added

- Direct Sparse Streaming: Stream partition extents directly from sparse images without writing intermediate unsparse files to disk
- In-memory chunk index for sparse containers, enabling sub-millisecond LP metadata inspection
- Contiguous extent merging to reduce seek and write syscalls during partition dumping

### Changed

- Replaced external NumPy dependency with pure standard library Python, eliminating runtime dependencies
- Replaced multiprocessing pool with in-process ThreadPoolExecutor for GIL-releasing disk I/O
- Increased stream buffer size from 1MB to 4MB for high-throughput sequential writes

### Fixed

- CLI: Fix unhandled `--use-metadata` argument by wiring it to the metadata loader
- Extractor: Fix negative seek crash on 0-byte or empty partitions by utilizing file truncation
- Metadata Parser: Fix partition name parsing by splitting at null terminator before decoding UTF-8 bytes

### Improved

- Metadata Parser: Optimize table parsing using `struct.unpack_from` to eliminate substring slice allocations
- Unpacker: Clean up duplicated extraction and sparse conversion logic across the codebase
- Memory: Significantly reduce RAM overhead during fill chunk generation by streaming pre-allocated pattern templates

# [2.3.0] - 31.10.2026

### Added

- In-process `OptimizedLpUnpack` class and `unpack_super()` helper for embedding into GUI tools without spawning subprocesses

### Improved

- Deduplicated LP metadata parser logic

# [2.2.0] - 20.06.2025

### Added

- `--dump-metadata` flag to export partition table layout into `metadata.json`
- Support for creating metadata files from existing partition images

# [2.1.0] - 18.06.2025

### Improved

- Output file preallocation for improved write throughput
- Additional buffer I/O optimizations

# [2.0.0] - 17.06.2025

### Added

- Parallel partition extraction using multiple worker threads
- Vectorized fill chunk handling

### Improved

- Overall extraction performance improvements

# [1.0.0] - 16.06.2025

### Added

- Initial release of unsuper
- Sparse image decompression and Android LP partition extraction

