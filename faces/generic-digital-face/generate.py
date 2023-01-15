# Generate faces list JSON and preview images

import json
import os
import sys
import subprocess

_USAGE = """
Usage:
    python3 generate.py [micropython executable] [face name]

    [micropython executable]    Path of Unix port MicroPython executable. 
                                For example: "~/src/lv_micropython/ports/unix/micropython-dev"
    [face name]                 (Optional) Face to generate preview for.
"""

_LIST_FILE = "faces.json"
_FACE_FILE = "face.json"

_PREVIEW_TIME_TUPLE = str((2023, 1, 1, 12, 0, 0, 0))

_PREVIEWS_DIRECTORY = "_previews"
_PREVIEW_POSTFIX = "_preview"
_PREVIEW_EXTENSION = ".jpg"

_PYTHON_COMMAND = "python3"
_PREVIEW_MPY_FILE = "preview.py"

_SNAPSHOT_CONVERTER = "../../tools/convert_snapshot_to_image.py"
_SNAPSHOT_WIDTH = 240
_SNAPSHOT_HEIGHT = 240

_THUMBNAIL_CONVERTER = "../../tools/resize_image.py"
_THUMBNAIL_WIDTH = 60
_THUMBNAIL_HEIGHT = 60
_THUMBNAIL_POSTFIX = "_thumbnail"
_THUMBNAIL_EXTENSION = ".jpg"

# Get MicroPython executable file path
try:
    mpy = sys.argv[1]
except:
    print(_USAGE)
    sys.exit(1)

names = []
process_names = []

# Check if optional face name is passed as argument
if len(sys.argv) > 2:
    # Optional face name was given, so generate preview only for that face, and append to existing faces list
    face_name = sys.argv[2]
    process_names = [face_name]
    try:
        with open(_LIST_FILE, "r") as f:
            faces = json.load(f)
            names = faces.get("names", [])
            if face_name not in names:
                names.append(face_name)
            names.sort()
    except:
        pass

else:
    # Get list of faces
    names = [e.name for e in os.scandir(".") if e.is_dir() and not e.name.startswith("_")]
    names.sort()
    process_names = names

faces = {
    "previews":{
        "directory": _PREVIEWS_DIRECTORY,
        "name_postfix": _PREVIEW_POSTFIX + _PREVIEW_EXTENSION,
        "width": _SNAPSHOT_WIDTH,
        "height": _SNAPSHOT_HEIGHT,
    },
    "thumbnails":{
        "directory": _PREVIEWS_DIRECTORY,
        "name_postfix": _THUMBNAIL_POSTFIX + _THUMBNAIL_EXTENSION,
        "width": _THUMBNAIL_WIDTH,
        "height": _THUMBNAIL_HEIGHT,
    },
    "names": names
}

# Generate preview images
for name in process_names:
    try:
        print(f"Generate preview for face: {name}")

        snapshot_name = f"{_PREVIEWS_DIRECTORY}/{name}{_PREVIEW_POSTFIX}.raw"
        image_name = f"{_PREVIEWS_DIRECTORY}/{name}{_PREVIEW_POSTFIX}{_PREVIEW_EXTENSION}"
        thumbnail_name = f"{_PREVIEWS_DIRECTORY}/{name}{_THUMBNAIL_POSTFIX}{_THUMBNAIL_EXTENSION}"
        
        # Generate face and take RAW snapshot
        subprocess.run([mpy, _PREVIEW_MPY_FILE, name, snapshot_name, _PREVIEW_TIME_TUPLE], stdout=subprocess.PIPE)

        # Convert RAW snapshot to image file
        subprocess.run([_PYTHON_COMMAND, _SNAPSHOT_CONVERTER, snapshot_name, image_name, str(_SNAPSHOT_WIDTH), str(_SNAPSHOT_HEIGHT)], stdout=subprocess.PIPE)

        # Create thumbnail image
        subprocess.run([_PYTHON_COMMAND, _THUMBNAIL_CONVERTER, image_name, thumbnail_name, str(_THUMBNAIL_WIDTH), str(_THUMBNAIL_HEIGHT)], stdout=subprocess.PIPE)

        # Delete RAW file
        os.remove(snapshot_name)

    except Exception as e:
        print(f"Error generating face preview: {name}", e)

# Save faces list JSON
with open(_LIST_FILE, "w") as f:
    json.dump(faces, f)
