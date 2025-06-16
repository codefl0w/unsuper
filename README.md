
# unsuper
The fastest Android super.img dumper, made in Python.

![Version](https://img.shields.io/github/v/release/codefl0w/unsuper) ![Downloads](https://img.shields.io/github/downloads/codefl0w/unsuper/total)


## Features

-  **Extremely fast** - Best in its class, see speeds below
- **Unsparse support** - Automatically unsparses images without any dependancies
- **Smart extraction** - Automatically skips empty partitions
- **Selective usage** - unsuper can extract only specific partitions or just unsparse the image



# Speed
unsuper can can unsparse a 6.67GB super.img in only 11 seconds, and dump all available partitions in ~12 seconds on an average NVMe disk with the default of 4 threads. This puts the total extraction time to under 25 seconds, faster than any other competitor. This also means that V2.0 extracts partitions up to 2.5 times faster compared to V1.0.

Performance may vary based on the amount of threads and disk speeds. More threads doesn't always equal to higher speeds.

# Usage

unsuper's usage is extremely easy: just state the path to your super.img and start. If no output directory is stated, unsuper will create an "extracted_partitions" folder under your home directory and use it as default.

 Extra arguements come AFTER the positional arguements.

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
      --temp-dir TEMP_DIR   Directory for temporary unsparse file (default: system temp directory)
      --unsparse            Unsparse image and save to output directory

For example, if you want to extract the system_a partition using 6 threads:

    unsuper.py /path/to/super.img /output_path --partitions system_a --jobs 6

And so on.

unsuper can also simply unsparse an image and save it to a specified directory:

    unsuper.py /path/to/super.img /output_path --unsparse
    
Or list all available partitions and clean after:

    unsuper.py /path/to/super.img --list

### Notes
If the --list arguement is used with --partitions, it will calculate the specified partitions' sizes and exit.

If the --unsparse arguement is used along with --partitions or --list, the unsparse image will be saved to the output directory and reused for extraction rather than creating a temporary one.

### Extras

Enjoy my work? Please consider a small donation!

<a href="https://buymeacoffee.com/fl0w" target="_blank" rel="noopener noreferrer">
  <img width="350" alt="yellow-button" src="https://github.com/user-attachments/assets/2e6d44c8-9640-4cb3-bcc8-989595d6b7e9"/>
</a>

