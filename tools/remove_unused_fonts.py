# Remove unused font files

import os
import sys
from pathlib import Path

_USAGE = """
Usage:

    python3 remove_unused_fonts.py [fonts_path] [search_path]

    [fonts_path]        Path of font files (example: "../fonts")
    [search_path]       Path to search for files containing font file names (example: "../")

Script collects font file names, then searches for them in all ".py" and ".json" files.
"""

try:
    fonts_dir = sys.argv[1]
    rootdir = sys.argv[2]
except:
    print(_USAGE)
    sys.exit(1)

search_file_extensions = ["py", "json"]
font_files = [name for name in os.listdir(fonts_dir) if name.endswith(".font")]
used_font_files = []
original_font_files_count = len(font_files)

for currentdir, subdirs, files in os.walk(rootdir):
    for file_name in files:
        # Skip files we are not interested in
        parts = file_name.rsplit(".", 2)
        if len(parts) < 2 or parts[1] not in search_file_extensions:
            continue

        file_full_path = os.path.join(currentdir, file_name)
        file_content = Path(file_full_path).read_text()

        # Check for font file usage:
        for font_file in font_files:
            if font_file in file_content:
                used_font_files.append(font_file)

        # Remove used fonts:
        for font_file in used_font_files:
            if font_file in font_files:
                font_files.remove(font_file)

unused_font_files_count = len(font_files)
used_font_files_count = len(used_font_files)
print(
    f"Font files count: {original_font_files_count}, used: {used_font_files_count}, NOT used: {unused_font_files_count}")
print("Remove NOT used fonts: ", font_files)

for font_file in font_files:
    os.remove(os.path.join(fonts_dir, font_file))
