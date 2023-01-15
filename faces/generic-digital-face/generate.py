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

if len(sys.argv) > 2:
    # Optional face name was given, 
    # so generate preview only for that face, 
    # and append to existing faces list
    names = [sys.argv[2]]
    try:
        with open(_LIST_FILE, "r") as f:
            faces = json.load(f)
    except:
        faces = {}

else:
    # Get list of faces
    names = [e.name for e in os.scandir(".") if e.is_dir() and not e.name.startswith("_")]
    names.sort()

    # Faces list
    faces = {}
    

# Generate list and preview images
for name in names:
    try:
        print(f"Generate preview for face: {name}")

        raw_name = f"{_PREVIEWS_DIRECTORY}/{name}{_PREVIEW_POSTFIX}.raw"
        image_name = f"{_PREVIEWS_DIRECTORY}/{name}{_PREVIEW_POSTFIX}{_PREVIEW_EXTENSION}"
        thumbnail_name = f"{_PREVIEWS_DIRECTORY}/{name}{_THUMBNAIL_POSTFIX}{_THUMBNAIL_EXTENSION}"
        
        # Generate face and take RAW snapshot
        subprocess.run([mpy, _PREVIEW_MPY_FILE, "--snapshot", name, raw_name], stdout=subprocess.PIPE)

        # Convert RAW snapshot to image file
        subprocess.run([_PYTHON_COMMAND, _SNAPSHOT_CONVERTER, raw_name, image_name, str(_SNAPSHOT_WIDTH), str(_SNAPSHOT_HEIGHT)], stdout=subprocess.PIPE)

        # Create thumbnail image
        subprocess.run([_PYTHON_COMMAND, _THUMBNAIL_CONVERTER, image_name, thumbnail_name, str(_THUMBNAIL_WIDTH), str(_THUMBNAIL_HEIGHT)], stdout=subprocess.PIPE)

        # Delete RAW file
        os.remove(raw_name)

        # Get list of face files from directory
        files = [e.name for e in os.scandir(name) if e.is_file() and not e.name.startswith(".")]

        # Get additional face files from the face JSON file
        with open(f"{name}/{_FACE_FILE}", "r") as f:
            face: dict = json.load(f)
            if "background" in face:
                background_file = face.get("background").get("image", None)
                if background_file and background_file not in files:
                    files.append(background_file)
            if "labels" in face:
                labels = face.get("labels", [])
                for label in labels:
                    font_file = label.get("font", None)
                    if font_file and font_file not in files:
                        files.append(font_file)

        # Add face info to list
        faces[name] = {
            "preview": f"{name}{_PREVIEW_POSTFIX}{_PREVIEW_EXTENSION}",
            "thumbnail": f"{name}{_THUMBNAIL_POSTFIX}{_THUMBNAIL_EXTENSION}",
            "files": files
        }
    except Exception as e:
        print(f"Error generating face preview: {name}", e)

# Save faces list JSON
with open(_LIST_FILE, "w") as f:
    json.dump(faces, f)
