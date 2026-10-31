# unsuper
The fastest Android super.img dumper, made in Python.

![GitHub Release](https://img.shields.io/github/v/release/codefl0w/unsuper?style=for-the-badge&color=ff8ff5&link=https%3A%2F%2Fgithub.com%2Fcodefl0w%2Funsuper)
![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/codefl0w/unsuper/total?style=for-the-badge)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/codefl0w/unsuper/build-multiplatform.yml?style=for-the-badge&label=Executable%20binary%20build%20status)


## Features

- **Direct sparse streaming** - Streams partitions directly from sparse images without writing temporary unsparse files to disk
- **Zero dependencies** - Built entirely with standard library Python, no external packages required
- **Smart extraction** - Automatically skips empty partitions and merges contiguous extents
- **Selective usage** - Extract specific partitions, inspect metadata, or unsparse the full image

# Installation

## Directly running the script
Download the script, or clone into the repository if you want to contribute / fork.

Download and install [Python](https://www.python.org/downloads/) (3.6 and later) and add it to PATH.

Follow [Usage](#usage). You'll need to type "python" before calling the script, the directions don't include that for simplicity.

## Using pip

Simply run `pip install unsuper` to install the latest version globally.

## Executables

If you don't want to install Python, download and use the latest executable binary for your operating system from the [releases page](https://github.com/codefl0w/unsuper/releases).

# Speed

Extraction streams directly from sparse chunks to partition files in a single pass without allocating temporary images on storage.

Performance depends primarily on drive write throughput and thread allocation. Benchmark metrics will be published once standardized comparative testing against `lpunpack` is finalized.

# Usage

unsuper's usage is straightforward: state the path to your super.img and start. If no output directory is stated, unsuper will create an "extracted_partitions" folder in the current directory and use it as default.

Extra arguments come AFTER the positional arguments.

    positional arguments:
      super_image           Path to super.img file
      output_dir            Output directory for extracted partitions (default: extracted_partitions)

    options:
      -h, --help            show this help message and exit
      --version             show program's version number and exit
      -p, --partitions PARTITIONS [PARTITIONS ...]
                            Specific partition names to extract (vendor, product etc.) (default: extract all)
      -j, --jobs JOBS       Number of parallel extraction threads (default: 4)
      -q, --quiet           Suppress progress output
      --list                List available partitions and exit
      --temp-dir TEMP_DIR   Directory for temporary unsparse file if --unsparse is used (default: system temp directory)
      --unsparse            Unsparse image and save to output directory
      --dump-metadata       Dump partition metadata to metadata.json in output directory
      --use-metadata METADATA_FILE
                            Use existing metadata.json file for partition information
      --create-metadata IMAGE [IMAGE ...]
                            Create metadata.json from individual partition images

For example, if you want to extract the system_a partition using 6 threads:

    unsuper.py /path/to/super.img /output_path --partitions system_a --jobs 6

And so on.

unsuper can also simply unsparse an image and save it to a specified directory:

    unsuper.py /path/to/super.img /output_path --unsparse

Or list all available partitions and exit:

    unsuper.py /path/to/super.img --list

### Notes
If the --list argument is used with --partitions, it will calculate the specified partitions' sizes and exit.

If the --unsparse argument is used along with --partitions or --list, the unsparse image will be saved to the output directory and used for extraction.

### Extras

Enjoy my work? Please consider a small donation!

<a href="https://buymeacoffee.com/fl0w" target="_blank" rel="noopener noreferrer">
  <img width="350" alt="yellow-button" src="https://github.com/user-attachments/assets/2e6d44c8-9640-4cb3-bcc8-989595d6b7e9"/>
</a>
