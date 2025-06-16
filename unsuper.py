#!/usr/bin/env python3

# unsuper, fastest Android super.img dumper

import argparse
import mmap
import os
import struct
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, List, Optional, Tuple
import time

VERSION = 1.0

# Constants
SPARSE_HEADER_MAGIC = 0xED26FF3A
SPARSE_HEADER_SIZE = 28
SPARSE_CHUNK_HEADER_SIZE = 12

LP_PARTITION_RESERVED_BYTES = 4096
LP_METADATA_GEOMETRY_MAGIC = 0x616c4467
LP_METADATA_GEOMETRY_SIZE = 4096
LP_METADATA_HEADER_MAGIC = 0x414C5030
LP_SECTOR_SIZE = 512

LP_TARGET_TYPE_LINEAR = 0

# Optimized buffer size for I/O operations (1MB)
BUFFER_SIZE = 1024 * 1024

class FastDumperError(Exception):
    # Custom exception for dumper errors
    pass

@dataclass
class ExtentInfo:
    # extent information
    offset: int
    size: int

@dataclass
class PartitionInfo:
    # partition information
    name: str
    extents: List[ExtentInfo]
    total_size: int

class SparseHeader:
    # Sparse image header parser
    def __init__(self, buffer: bytes):
        fmt = '<I4H4I'
        required_size = struct.calcsize(fmt)
        if len(buffer) < required_size:
            raise FastDumperError(f"Sparse header too short: got {len(buffer)} bytes, need {required_size}")
        
        (
            self.magic,
            self.major_version,
            self.minor_version,
            self.file_hdr_sz,
            self.chunk_hdr_sz,
            self.blk_sz,
            self.total_blks,
            self.total_chunks,
            self.image_checksum
        ) = struct.unpack(fmt, buffer[:required_size])

class SparseChunkHeader:
    # Sparse chunk header parser
    def __init__(self, buffer: bytes):
        fmt = '<2H2I'
        required_size = struct.calcsize(fmt)
        if len(buffer) < required_size:
            raise FastDumperError(f"Chunk header too short: got {len(buffer)} bytes, need {required_size}")
        
        (
            self.chunk_type,
            self.reserved,
            self.chunk_sz,
            self.total_sz,
        ) = struct.unpack(fmt, buffer[:required_size])

class FastSparseConverter:
    # sparse image converter
    
    def __init__(self, input_file: str, temp_dir: Optional[str] = None):
        self.input_file = input_file
        self.temp_dir = temp_dir
        
    def convert(self) -> str:
        
        # Create output file in temp directory
        if self.temp_dir:
            temp_dir = Path(self.temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
            output_file = temp_dir / f"{Path(self.input_file).stem}.unsparse.img"
        else:
            # Use OS temp directory
            fd, output_file = tempfile.mkstemp(
                suffix='.unsparse.img',
                prefix=f"{Path(self.input_file).stem}_",
                dir=None
            )
            os.close(fd)  # Close the file descriptor, we'll open it normally
            output_file = str(output_file)
        
        try:
            with open(self.input_file, 'rb') as infile, open(output_file, 'wb') as outfile:
                # Read and validate header
                header_data = infile.read(SPARSE_HEADER_SIZE)
                if len(header_data) < SPARSE_HEADER_SIZE:
                    raise FastDumperError(f"File too short: cannot read sparse header ({len(header_data)} < {SPARSE_HEADER_SIZE})")
                
                header = SparseHeader(header_data)
                
                if header.magic != SPARSE_HEADER_MAGIC:
                    raise FastDumperError(f"Invalid sparse image magic: 0x{header.magic:08x} (expected 0x{SPARSE_HEADER_MAGIC:08x})")
                
                # Validate header values
                if header.file_hdr_sz < SPARSE_HEADER_SIZE:
                    raise FastDumperError(f"Invalid file header size: {header.file_hdr_sz}")
                
                if header.chunk_hdr_sz < SPARSE_CHUNK_HEADER_SIZE:
                    raise FastDumperError(f"Invalid chunk header size: {header.chunk_hdr_sz}")
                
                if header.blk_sz == 0:
                    raise FastDumperError("Invalid block size: 0")
                
                # Skip to chunk data
                infile.seek(header.file_hdr_sz)
                
                # Process chunks efficiently
                for chunk_idx in range(header.total_chunks):
                    try:
                        # Read chunk header with bounds checking
                        chunk_header_data = infile.read(SPARSE_CHUNK_HEADER_SIZE)
                        if len(chunk_header_data) < SPARSE_CHUNK_HEADER_SIZE:
                            raise FastDumperError(f"Unexpected EOF while reading chunk {chunk_idx + 1}/{header.total_chunks} header: got {len(chunk_header_data)} bytes")
                        
                        chunk_header = SparseChunkHeader(chunk_header_data)
                        
                        # Validate chunk header
                        if chunk_header.total_sz < header.chunk_hdr_sz:
                            raise FastDumperError(f"Invalid chunk {chunk_idx + 1} total size: {chunk_header.total_sz} < {header.chunk_hdr_sz}")
                        
                        # Skip extra header data if present
                        if header.chunk_hdr_sz > SPARSE_CHUNK_HEADER_SIZE:
                            extra_bytes = header.chunk_hdr_sz - SPARSE_CHUNK_HEADER_SIZE
                            skipped = infile.read(extra_bytes)
                            if len(skipped) < extra_bytes:
                                raise FastDumperError(f"Unexpected EOF while reading chunk {chunk_idx + 1} extra header data")
                        
                        chunk_data_size = chunk_header.total_sz - header.chunk_hdr_sz
                        output_size = chunk_header.chunk_sz * header.blk_sz
                        
                        if chunk_header.chunk_type == 0xCAC1:  # Raw data
                            # Copy data in large chunks for better performance
                            remaining = chunk_data_size
                            while remaining > 0:
                                chunk_size = min(BUFFER_SIZE, remaining)
                                data = infile.read(chunk_size)
                                if len(data) == 0:
                                    raise FastDumperError(f"Unexpected EOF while reading chunk {chunk_idx + 1} raw data")
                                outfile.write(data)
                                remaining -= len(data)
                                
                        elif chunk_header.chunk_type == 0xCAC2:  # Fill data
                            if chunk_data_size < 4:
                                raise FastDumperError(f"Incomplete fill chunk {chunk_idx + 1}: data size {chunk_data_size} < 4")
                            
                            fill_data = infile.read(4)
                            if len(fill_data) < 4:
                                raise FastDumperError(f"Unexpected EOF while reading chunk {chunk_idx + 1} fill data")
                            
                            # Skip remaining fill chunk data if any
                            if chunk_data_size > 4:
                                remaining_fill = chunk_data_size - 4
                                skipped = infile.read(remaining_fill)
                                if len(skipped) < remaining_fill:
                                    raise FastDumperError(f"Unexpected EOF while reading chunk {chunk_idx + 1} remaining fill data")
                            
                            # Write fill pattern efficiently
                            if output_size > 0:
                                pattern = fill_data * (BUFFER_SIZE // 4)
                                remaining = output_size
                                while remaining > 0:
                                    write_size = min(len(pattern), remaining)
                                    outfile.write(pattern[:write_size])
                                    remaining -= write_size
                                
                        elif chunk_header.chunk_type == 0xCAC3:  # Don't care
                            # Skip chunk data and write zeros/seek
                            if chunk_data_size > 0:
                                skipped = infile.read(chunk_data_size)
                                if len(skipped) < chunk_data_size:
                                    raise FastDumperError(f"Unexpected EOF while skipping chunk {chunk_idx + 1} don't care data")
                            
                            # Seek forward in output file (creates sparse file if supported)
                            current_pos = outfile.tell()
                            outfile.seek(current_pos + output_size)
                            
                        elif chunk_header.chunk_type == 0xCAC4:  # CRC32
                            # Skip CRC chunk data
                            if chunk_data_size > 0:
                                skipped = infile.read(chunk_data_size)
                                if len(skipped) < chunk_data_size:
                                    raise FastDumperError(f"Unexpected EOF while skipping chunk {chunk_idx + 1} CRC data")
                            # CRC chunks don't contribute to output
                            
                        else:
                            # Unknown chunk type, skip data and output
                            print(f"Warning: Unknown chunk type 0x{chunk_header.chunk_type:04x} in chunk {chunk_idx + 1}, skipping...")
                            if chunk_data_size > 0:
                                skipped = infile.read(chunk_data_size)
                                if len(skipped) < chunk_data_size:
                                    raise FastDumperError(f"Unexpected EOF while skipping chunk {chunk_idx + 1} unknown data")
                            
                            # Seek forward in output
                            current_pos = outfile.tell()
                            outfile.seek(current_pos + output_size)
                    
                    except FastDumperError:
                        raise
                    except Exception as e:
                        raise FastDumperError(f"Error processing chunk {chunk_idx + 1}: {e}")
        
        except Exception as e:
            # Clean up partial output file on error
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                except:
                    pass
            raise
        
        return output_file

class FastMetadataParser:
    # Optimized metadata parser
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_size = os.path.getsize(file_path)
        
    def parse_partitions(self, partition_names: Optional[List[str]] = None) -> List[PartitionInfo]:
        # Parse partition metadata efficiently
        
        with open(self.file_path, 'rb') as f:
            # Use memory mapping for better performance on large files
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                return self._parse_with_mmap(mm, partition_names)
    
    def _parse_with_mmap(self, mm: mmap.mmap, partition_names: Optional[List[str]]) -> List[PartitionInfo]:
            # Parse metadata using memory mapping
            
            # Check minimum file size
            if len(mm) < LP_PARTITION_RESERVED_BYTES + 40:
                raise FastDumperError("File too small to contain valid metadata")
            
            # Read geometry
            mm.seek(LP_PARTITION_RESERVED_BYTES)
            geometry_data = mm.read(40)  # Only read what we need
            if len(geometry_data) < 40:
                raise FastDumperError("Cannot read geometry data")
            
            magic, struct_size = struct.unpack('<2I', geometry_data[:8])
            
            if magic != LP_METADATA_GEOMETRY_MAGIC:
                raise FastDumperError(f"Invalid geometry magic: 0x{magic:08x}")
            
            # Read remaining geometry fields
            if len(geometry_data) < 44:
                mm.seek(LP_PARTITION_RESERVED_BYTES + 32)
                extra_data = mm.read(12)
                if len(extra_data) < 12:
                    raise FastDumperError("Cannot read complete geometry data")
                geometry_data = geometry_data[:32] + extra_data
            
            metadata_max_size, metadata_slot_count, logical_block_size = struct.unpack(
                '<3I', geometry_data[32:44]
            )
            
            # Validate geometry values
            if metadata_max_size == 0 or metadata_slot_count == 0:
                raise FastDumperError("Invalid metadata geometry")
            
            # Calculate header offset
            base_offset = LP_PARTITION_RESERVED_BYTES + (LP_METADATA_GEOMETRY_SIZE * 2)
            header_offset = base_offset
            
            # Check if we have enough space for metadata
            if header_offset + 128 > len(mm):
                raise FastDumperError("File too small for metadata header")
            
            # Read metadata header
            mm.seek(header_offset)
            header_data = mm.read(128)  # Read enough for header + table descriptors
            if len(header_data) < 128:
                raise FastDumperError("Cannot read metadata header")
            
            magic = struct.unpack('<I', header_data[:4])[0]
            if magic != LP_METADATA_HEADER_MAGIC:
                # Try backup header
                backup_offset = base_offset + metadata_max_size * metadata_slot_count
                if backup_offset + 128 > len(mm):
                    raise FastDumperError("File too small for backup metadata header")
                
                mm.seek(backup_offset)
                header_data = mm.read(128)
                if len(header_data) < 128:
                    raise FastDumperError("Cannot read backup metadata header")
                
                magic = struct.unpack('<I', header_data[:4])[0]
                if magic != LP_METADATA_HEADER_MAGIC:
                    raise FastDumperError(f"Invalid metadata header magic: 0x{magic:08x}")
                header_offset = backup_offset
            
            # Parse header and table descriptors
            header_size, tables_size = struct.unpack('<2I', header_data[8:16])
            
            if header_size < 80 or tables_size == 0:
                raise FastDumperError("Invalid metadata header values")
            
            # Parse table descriptors (starting at offset 80 in header)
            tables_start = header_offset + header_size
            
            # Check bounds for table descriptors
            if len(header_data) < 104:
                raise FastDumperError("Header too small for table descriptors")
            
            # Partition table descriptor
            part_offset, part_count, part_entry_size = struct.unpack('<3I', header_data[80:92])
            
            # Extent table descriptor  
            extent_offset, extent_count, extent_entry_size = struct.unpack('<3I', header_data[92:104])
            
            # Validate table parameters
            if part_entry_size < 52 or extent_entry_size < 24:
                raise FastDumperError("Invalid table entry sizes")
            
            # Check bounds for partition table
            part_table_start = tables_start + part_offset
            part_table_size = part_count * part_entry_size
            if part_table_start + part_table_size > len(mm):
                raise FastDumperError("Partition table extends beyond file")
            
            # Check bounds for extent table
            extent_table_start = tables_start + extent_offset
            extent_table_size = extent_count * extent_entry_size
            if extent_table_start + extent_table_size > len(mm):
                raise FastDumperError("Extent table extends beyond file")
            
            # Read partition table
            mm.seek(part_table_start)
            partitions_data = mm.read(part_table_size)
            if len(partitions_data) < part_table_size:
                raise FastDumperError("Cannot read complete partition table")
            
            # Read extent table
            mm.seek(extent_table_start)
            extents_data = mm.read(extent_table_size)
            if len(extents_data) < extent_table_size:
                raise FastDumperError("Cannot read complete extent table")
            
            # Parse partitions and extents efficiently
            partitions = []
            
            for i in range(part_count):
                part_start = i * part_entry_size
                part_data = partitions_data[part_start:part_start + part_entry_size]
                
                if len(part_data) < 52:
                    continue  # Skip malformed entries
                
                # Parse partition entry
                name_bytes = part_data[:36]
                name = name_bytes.decode('utf-8').strip('\x00')
                
                # Skip empty partition names
                if not name:
                    continue
                
                # Skip if not in requested partitions
                if partition_names and name not in partition_names:
                    continue
                
                attributes, first_extent_idx, num_extents = struct.unpack(
                    '<3I', part_data[36:48]
                )
                
                # Check for various empty partition conditions
                if num_extents == 0:
                    print(f"Warning: Partition {name} has no extents, skipping...")
                    continue
                
                # Validate extent indices
                if first_extent_idx >= extent_count or first_extent_idx + num_extents > extent_count:
                    print(f"Warning: Invalid extent indices for partition {name}, skipping...")
                    continue
                
                # Parse extents for this partition
                extents = []
                total_size = 0
                skipped_extents = 0
                
                for j in range(num_extents):
                    extent_idx = first_extent_idx + j
                    extent_start = extent_idx * extent_entry_size
                    extent_data = extents_data[extent_start:extent_start + extent_entry_size]
                    
                    if len(extent_data) < 24:
                        skipped_extents += 1
                        continue  # Skip malformed extents
                    
                    num_sectors, target_type, target_data = struct.unpack(
                        '<QIQ', extent_data[:20]
                    )
                    
                    if target_type != LP_TARGET_TYPE_LINEAR:
                        skipped_extents += 1
                        continue
                    
                    offset = target_data * LP_SECTOR_SIZE
                    size = num_sectors * LP_SECTOR_SIZE
                    
                    # Validate extent bounds
                    if offset + size > len(mm):
                        print(f"Warning: Extent for {name} extends beyond file, truncating...")
                        size = max(0, len(mm) - offset)
                    
                    if size > 0:
                        extents.append(ExtentInfo(offset, size))
                        total_size += size
                    else:
                        skipped_extents += 1
                
                # Check if partition ended up empty after processing extents
                if not extents:
                    if skipped_extents > 0:
                        print(f"Warning: Partition {name} has no valid extents (skipped {skipped_extents} invalid extents), skipping...")
                    else:
                        print(f"Warning: Partition {name} has zero-sized extents, skipping...")
                    continue
                
                # Only add partitions with valid extents
                partitions.append(PartitionInfo(name, extents, total_size))
            
            return partitions

class FastExtractor:
    # High-performance partition extractor
    
    def __init__(self, input_file: str, output_dir: str, max_workers: int = 4):
        self.input_file = input_file
        self.output_dir = Path(output_dir)
        self.max_workers = max_workers
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def extract_partition(self, partition: PartitionInfo) -> Tuple[str, float]:
        # Extract a single partition
        start_time = time.time()
        output_file = self.output_dir / f"{partition.name}.img"
        
        try:
            with open(self.input_file, 'rb') as infile, open(output_file, 'wb') as outfile:
                # Use memory mapping for input file if it's large
                if os.path.getsize(self.input_file) > 100 * 1024 * 1024:  # 100MB threshold
                    with mmap.mmap(infile.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                        self._extract_with_mmap(mm, outfile, partition)
                else:
                    self._extract_with_seek(infile, outfile, partition)
        except Exception as e:
            # Clean up partial output file on error
            if output_file.exists():
                output_file.unlink()
            raise FastDumperError(f"Failed to extract {partition.name}: {e}")
        
        elapsed = time.time() - start_time
        return partition.name, elapsed
    
    def _extract_with_mmap(self, mm: mmap.mmap, outfile: BinaryIO, partition: PartitionInfo):
        # Extract using memory mapping
        for extent in partition.extents:
            # Validate extent bounds
            if extent.offset >= len(mm):
                continue
            
            mm.seek(extent.offset)
            remaining = min(extent.size, len(mm) - extent.offset)
            
            while remaining > 0:
                chunk_size = min(BUFFER_SIZE, remaining)
                data = mm.read(chunk_size)
                if not data:
                    break
                outfile.write(data)
                remaining -= len(data)
    
    def _extract_with_seek(self, infile: BinaryIO, outfile: BinaryIO, partition: PartitionInfo):
        # Extract using classic file operations
        file_size = os.path.getsize(self.input_file)
        
        for extent in partition.extents:
            # Validate extent bounds
            if extent.offset >= file_size:
                continue
            
            infile.seek(extent.offset)
            remaining = min(extent.size, file_size - extent.offset)
            
            while remaining > 0:
                chunk_size = min(BUFFER_SIZE, remaining)
                data = infile.read(chunk_size)
                if not data:
                    break
                outfile.write(data)
                remaining -= len(data)
    
    def extract_all(self, partitions: List[PartitionInfo], show_progress: bool = True) -> None:
        # Extract all partitions in parallel
        
        if show_progress:
            print(f"Extracting {len(partitions)} partitions using {self.max_workers} threads...")
        
        # Use thread pool for parallel extraction
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all extraction tasks
            future_to_partition = {
                executor.submit(self.extract_partition, partition): partition 
                for partition in partitions
            }
            
            # Process completed tasks
            completed = 0
            total_time = 0
            
            for future in as_completed(future_to_partition):
                partition = future_to_partition[future]
                
                try:
                    name, elapsed = future.result()
                    completed += 1
                    total_time += elapsed
                    
                    if show_progress:
                        size_mb = partition.total_size / (1024 * 1024)
                        speed_mb = size_mb / elapsed if elapsed > 0 else 0
                        print(f"[{completed}/{len(partitions)}] {name}: "
                              f"{size_mb:.1f}MB in {elapsed:.2f}s ({speed_mb:.1f}MB/s)")
                        
                except Exception as e:
                    print(f"Error extracting {partition.name}: {e}")
        
        if show_progress and len(partitions) > 1:
            avg_time = total_time / len(partitions)
            print(f"\nCompleted! Average extraction time: {avg_time:.2f}s per partition")
            print(f"Total extraction time: {total_time:.2f}s")


def main():
    ascii = r"""
                                       
 /\ /\ _ __  ___ _   _ _ __   ___ _ __ 
/ / \ \ '_ \/ __| | | | '_ \ / _ \ '__|
\ \_/ / | | \__ \ |_| | |_) |  __/ |   
 \___/|_| |_|___/\__,_| .__/ \___|_|   
                      |_|              
   Fastest super.img dumper ever
    
     """

    parser = argparse.ArgumentParser(
        description=ascii,
        usage="%(prog)s super_image [output_dir] [-h] [-p PARTITIONS [PARTITIONS ...]] [-j JOBS] [-q] [--list] [--temp-dir TEMP_DIR] [--version] [--unsparse]",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s V{VERSION}'
    )
    
    parser.add_argument(
        'super_image',
        help='Path to super.img file'
    )
    
    parser.add_argument(
        'output_dir',
        nargs='?',
        default='extracted_partitions',
        help='Output directory for extracted partitions (default: extracted_partitions)'
    )
    
    parser.add_argument(
        '-p', '--partitions',
        nargs='+',
        help='Specific partition names to extract (vendor, product etc.) (default: extract all)'
    )
    
    parser.add_argument(
        '-j', '--jobs',
        type=int,
        default=4,
        help='Number of parallel extraction threads (default: 4)'
    )
    
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Suppress progress output'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available partitions and exit'
    )
    
    parser.add_argument(
        '--temp-dir',
        help='Directory for temporary unsparse file (default: system temp directory)'
    )
    
    parser.add_argument(
        '--unsparse',
        action='store_true',
        help='Unsparse image and save to output directory'
    )
    
    args = parser.parse_args()
    
    # Validate input file
    input_path = Path(args.super_image)
    if not input_path.exists():
        print(f"Error: {args.super_image} not found")
        sys.exit(1)
    
    if input_path.stat().st_size == 0:
        print(f"Error: {args.super_image} is empty")
        sys.exit(1)
    
    unsparse_file = None  # Track unsparse file for cleanup
    
    try:
        input_file = args.super_image
        unsparse_created_by_flag = False  # Track if unsparse file was created by --unsparse flag
        
        # Check if input is sparse and convert if needed
        with open(input_file, 'rb') as f:
            magic_data = f.read(4)
            if len(magic_data) < 4:
                raise FastDumperError("File too small to determine format")
            magic = struct.unpack('<I', magic_data)[0]
            
        if magic == SPARSE_HEADER_MAGIC:
            if not args.quiet:
                print("Sparse image detected, converting...")
            
            # If --unsparse flag is used, save to output directory and use for extraction
            if args.unsparse:
                output_path = Path(args.output_dir)
                output_path.mkdir(parents=True, exist_ok=True)
                unsparse_output = output_path / f"{Path(args.super_image).stem}.unsparse.img"
                
                converter = FastSparseConverter(input_file, str(output_path))
                converted_file = converter.convert()
                
                # Move/rename to desired location if needed
                if converted_file != str(unsparse_output):
                    import shutil
                    shutil.move(converted_file, unsparse_output)
                
                # Use the unsparsed file for further processing
                input_file = str(unsparse_output)
                unsparse_file = str(unsparse_output)
                unsparse_created_by_flag = True
                
                if not args.quiet:
                    print(f"Unsparsed image saved to: {unsparse_output}")
            else:
                # Normal temp conversion for extraction
                converter = FastSparseConverter(input_file, args.temp_dir)
                unsparse_file = converter.convert()
                input_file = unsparse_file
                
                if not args.quiet:
                    print(f"Converted to temporary file: {input_file}")
        elif args.unsparse:
            # Image is already unsparsed, just copy it to output directory
            output_path = Path(args.output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            unsparse_output = output_path / f"{Path(args.super_image).stem}.unsparse.img"
            
            import shutil
            shutil.copy2(args.super_image, unsparse_output)
            
            # Use the copied file for further processing
            input_file = str(unsparse_output)
            unsparse_file = str(unsparse_output)
            unsparse_created_by_flag = True
            
            if not args.quiet:
                print(f"Image copied to: {unsparse_output} (was already unsparsed)")
        
        # If --unsparse is used without any extraction arguments, exit after unsparsing
        if args.unsparse and not args.partitions and not args.list:
            if not args.quiet:
                print("Unsparsing complete! Use --partitions to also extract partitions.")
            return
        
        # Parse metadata
        if not args.quiet:
            print("Parsing metadata...")
        
        parser_obj = FastMetadataParser(input_file)
        partitions = parser_obj.parse_partitions(args.partitions)
        
        if not partitions:
            if args.partitions:
                print(f"No matching partitions found for: {', '.join(args.partitions)}")
            else:
                print("No partitions found in image")
            sys.exit(1)
        
        # List partitions if requested
        if args.list:
            print(f"\nFound {len(partitions)} partitions:")
            total_size = 0
            for partition in partitions:
                size_mb = partition.total_size / (1024 * 1024)
                total_size += partition.total_size
                print(f"  {partition.name}: {size_mb:.1f}MB ({len(partition.extents)} extents)")
            
            total_mb = total_size / (1024 * 1024)
            print(f"\nTotal size: {total_mb:.1f}MB")
            return
        
        # Extract partitions
        extractor = FastExtractor(input_file, args.output_dir, args.jobs)
        extractor.extract_all(partitions, not args.quiet)
        
        if not args.quiet:
            print(f"\nExtraction complete! Files saved to: {args.output_dir}")
            if args.unsparse:
                print(f"Unsparsed image saved to: {input_file}")
        
    except FastDumperError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        # Clean up temporary unsparse file only if it wasn't created by --unsparse flag
        if unsparse_file and os.path.exists(unsparse_file) and not unsparse_created_by_flag:
            try:
                os.remove(unsparse_file)
                if not args.quiet:
                    print(f"Temporary sparse image cleaned successfully.")
            except Exception as e:
                print(f"Warning: Could not remove temporary file {unsparse_file}: {e}")

if __name__ == "__main__":
    main()
