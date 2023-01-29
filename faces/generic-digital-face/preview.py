# Preview of generic digital faces

import time
import os
import gc
import json
import errno
import struct
import sys
import uasyncio
import lvgl as lv

from micropython import const

_USAGE = """
Before preview set MicroPython executable as $mp environment variable:
    mp=~/src/lv_micropython/ports/unix/micropython-dev

Usage:
    $mp preview.py
    $mp preview.py [face name] 
    $mp preview.py [face name] [snapshot file] [time tuple]
    $mp preview.py --help
    $mp preview.py --snapshot-for-all [snapshot name postfix] [snapshots path] [time tuple] 

    [face name]                 Preview given face. (Optional)
    [snapshot file]             Take snapshot of face preview and save as RAW file. (Optional)
    [time tuple]                Show given time instead of actaul time. Tuple: (YYYY, MM, DD, HH, mm, ss, weekday) (Optional)

    --help                      Show current usage help

    --snapshot-for-all          Take snapshot RAW files for all faces
    [snapshot name postfix]     Snapshot file postfix (example: "_preview.raw") (Required)
    [snapshots path]            Path to store snapshot RAW files (example: _previews) (Required)
    [time tuple]                Show given time instead of actaul time. Tuple: (YYYY, MM, DD, HH, mm, ss, weekday) (Required)

Snapshot files are generated as BGRA RAW images.
They can be converted to PNG/JPEG/WebP image format with the script: "[repo]/tools/convert_snapshot_to_image.py"
"""

_FACE_FILE = "face.json"
_WIDTH = const(240)
_HEIGHT = const(240)
_MARGIN_PERCENT = const(20)
_DRIVE_LETTER = const('S')
_FS_CACHE_SIZE = const(2048)
_IMG_CACHE_COUNT = const(32)

_TYPE_DIRECTORY = const(0x4000)

_MENU_ITEM_WIDTH = const(200)
_MENU_ITEM_HEIGHT = const(50)


# ************************************
# Face implementation
# ************************************
_FONTS_PATH = _DRIVE_LETTER + ":fonts/"

_WEEK_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_WEEK_DAYS_SHORT = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
_MONTHS_SHORT = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

_BATTERY_PERCENT = const(100)

_PLACEHOLDERS = {
    "{YYYY}": lambda time_tuple: f"{time_tuple[0]:04d}",
    "{MM}": lambda time_tuple: f"{time_tuple[1]:02d}",
    "{DD}": lambda time_tuple: f"{time_tuple[2]:02d}",
    "{HH}": lambda time_tuple: f"{time_tuple[3]:02d}",
    "{mm}": lambda time_tuple: f"{time_tuple[4]:02d}",
    "{ss}": lambda time_tuple: f"{time_tuple[5]:02d}",
    "{day}": lambda time_tuple: _WEEK_DAYS[time_tuple[6]],
    "{day_short}": lambda time_tuple: _WEEK_DAYS_SHORT[time_tuple[6]],
    "{month}": lambda time_tuple: _MONTHS[time_tuple[1] - 1],
    "{month_short}": lambda time_tuple: _MONTHS_SHORT[time_tuple[1] - 1],
    "{battery_percent}": lambda time_tuple: str(_BATTERY_PERCENT)
}


class Face:
    def __init__(self, screen, base_path, name):
        self._screen = screen
        self._base_path = base_path
        self._name = name
        self._container = self._screen
        self._labels = []
        self._fonts = {}

    def show(self, time_tuple = None):
        try:
            face_path = f"{self._base_path}/{self._name}"
            with open(f"{face_path}/{_FACE_FILE}", "r") as f:
                face_config = json.load(f)

            if face_config["version"] != "1":
                print(f"Unknown face config version: {face_config['version']}")
                return

            self._load_background(face_config, face_path)
            self._load_labels(face_config)
            self._update_labels(time_tuple)
        except Exception as e:
            print(f"Failed to load face: {self._name}", e)

    def dispose(self):
        self._screen.clean()
        self._labels.clear()
        for font in self._fonts.values():
            font.free()
            del font
        self._fonts.clear()

        lv.img.cache_invalidate_src(None)
        gc.collect()

    def _load_background(self, face_config, face_path):
        if "background" not in face_config:
            return

        cfg = face_config["background"]
        if "color" in cfg:
            color = self._hex_color(cfg.get("color"))
            self._screen.set_style_bg_color(color, lv.STATE.DEFAULT)

        if "image" in cfg:
            image_path = f"{face_path}/{cfg.get('image')}"
            try:
                with open(image_path, "rb") as f:
                    image_data = f.read()

                image_desc = lv.img_dsc_t({
                    "data_size": len(image_data),
                    "data": image_data
                })

                image = lv.img(self._screen)
                image.set_src(image_desc)
                image.center()
                self._container = image
            except:
                print(f"Failed to background image: {image_path}")

    def _load_labels(self, face_config):
        if "labels" not in face_config:
            return

        __part_main = lv.PART.MAIN
        __default_align = lv.ALIGN.TOP_LEFT
        __default_textalign = lv.TEXT_ALIGN.LEFT
        __hex_to_color = self._hex_color
        __create_label = lv.label
        __lv_align = lv.ALIGN
        __lv_textalign = lv.TEXT_ALIGN
        __font_load = lv.font_load
        __labels = face_config["labels"]

        for cfg in __labels:
            __cfg_get = cfg.get
            text = __cfg_get("text", "")
            color = __hex_to_color(__cfg_get("color", "#000"))
            font_name = __cfg_get("font", None)
            x = __cfg_get("x", 0)
            y = __cfg_get("y", 0)
            
            align_text = __cfg_get("align", None)
            align = __lv_align.__dict__.get(align_text, __default_align)

            align_text = __cfg_get("textalign", None)
            textalign = __lv_textalign.__dict__.get(align_text, __default_textalign)

            label = __create_label(self._container)
            label.set_style_text_color(color, __part_main)
            label.set_style_text_align(textalign, __part_main)
            label.set_recolor(True)
            label.align(align, x, y)
            label.set_text("")

            if font_name:
                font_name = _FONTS_PATH + font_name
                try:
                    font = self._fonts.get(font_name, None)
                    if not font:
                        font = __font_load(font_name)
                        self._fonts[font_name] = font
                    label.set_style_text_font(font, __part_main)
                except Exception as e:
                    print(f"Failed to load font: {font_name}", e)

            self._labels.append({
                "lv_label": label,
                "text": text,
                "value": ""
            })

    def _hex_color(self, value):
        color_int = int(value.lstrip("#"), 16)
        return lv.color_hex(color_int)

    def _update_labels(self, time_tuple = None):
        time_tuple = time_tuple or time.localtime()
        for label in self._labels:
            text = label["text"]

            for key, transform_cb in _PLACEHOLDERS.items():
                if key in text:
                    text = text.replace(key, transform_cb(time_tuple))

            if text != label["value"]:
                label["value"] = text
                label["lv_label"].set_text(text)


# ************************************
# LVGL FS Driver
# ************************************
_RET_OK = lv.FS_RES.OK
_RET_FS_ERR = lv.FS_RES.FS_ERR


class LVGL_FS_File:
    def __init__(self, file, path):
        self.file = file
        self.path = path


class LVGL_FS_Driver():
    def __init__(self, base_path, fs_drv, letter, cache_size):
        self._base_path = base_path

        fs_drv.init()
        fs_drv.letter = ord(letter)
        fs_drv.cache_size = cache_size
        fs_drv.open_cb = self.open_cb
        fs_drv.read_cb = self.read_cb
        fs_drv.write_cb = self.write_cb
        fs_drv.seek_cb = self.seek_cb
        fs_drv.tell_cb = self.tell_cb
        fs_drv.close_cb = self.close_cb
        fs_drv.register()

    def open_cb(self, drv, path, mode):
        if mode == lv.FS_MODE.WR:
            p_mode = 'wb'
        elif mode == lv.FS_MODE.RD:
            p_mode = 'rb'
        elif mode == lv.FS_MODE.WR | lv.FS_MODE.RD:
            p_mode = 'rb+'
        else:
            raise RuntimeError(
                f"open_cb('{path}', {mode}) - open mode error, '{mode}' is invalid mode")

        try:
            f = open(f"{self._base_path}/{path}", p_mode)
        except Exception as e:
            raise RuntimeError(
                f"open_cb('{path}', '{p_mode}') error: ", errno.errorcode[e.args[0]])

        return LVGL_FS_File(f, path)

    def close_cb(self, drv, fs_file):
        try:
            fs_file.__cast__().file.close()
        except Exception as e:
            print(f"close_cb('{fs_file.__cast__().path}') error: {errno.errorcode[e.args[0]]}", e)
            return _RET_FS_ERR

        return _RET_OK

    def read_cb(self, drv, fs_file, buf, btr, br):
        try:
            tmp_data = buf.__dereference__(btr)
            bytes_read = fs_file.__cast__().file.readinto(tmp_data)
            br.__dereference__(4)[0:4] = struct.pack("<L", bytes_read)
        except Exception as e:
            print(f"read_cb('{fs_file.__cast__().path}', {btr}) error: {errno.errorcode[e.args[0]]}", e)
            return _RET_FS_ERR

        return _RET_OK

    def seek_cb(self, drv, fs_file, pos, whence):
        try:
            fs_file.__cast__().file.seek(pos, whence)
        except Exception as e:
            print(f"seek_cb('{fs_file.__cast__().path}', {pos}, {whence}) error: {errno.errorcode[e.args[0]]}", e)
            return _RET_FS_ERR

        return _RET_OK

    def tell_cb(self, drv, fs_file, pos):
        try:
            tpos = fs_file.__cast__().file.tell()
            pos.__dereference__(4)[0:4] = struct.pack("<L", tpos)
        except Exception as e:
            print(f"tell_cb('{fs_file.__cast__().path}') error: {errno.errorcode[e.args[0]]}", e)
            return _RET_FS_ERR

        return _RET_OK

    def write_cb(self, drv, fs_file, buf, btw, bw):
        try:
            wr = fs_file.__cast__().file.write(buf[0:btw])
            bw.__dereference__(4)[0:4] = struct.pack("<L", wr)
        except Exception as e:
            print(f"write_cb('{fs_file.__cast__().path}', {btw}) error: {errno.errorcode[e.args[0]]}", e)
            return _RET_FS_ERR

        return _RET_OK

# ************************************
# Main app
# ************************************


class App():
    def __init__(self):
        self._faces_path = os.getcwd()
        self._root_path = self._faces_path.rsplit("/", 2)[0]
        self._face: Face = None
        self._faces = []
        self._menu_screen: lv.obj = None
        self._face_screen: lv.obj = None
        self._face_selector_dropdown: lv.dropdown = None
        self._is_running = False

        self._load_faces_list()
        self._init_lvgl()
        self._init_lvgl_fs()
        self._init_lvgl_image_decoders()
        self._init_menu_screen()
        self._init_face_screen()

    async def loop(self, face_name=None):
        if face_name and face_name in self._faces and self._path_exists(f"{self._faces_path}/{face_name}"):
            self._face_selector_dropdown.set_selected(self._faces.index(face_name))
            self._show_face(face_name)
        else:
            self._show_menu()
        self._is_running = True
        while self._is_running:
            await uasyncio.sleep_ms(200)
    
    def snapshot_all(self, snapshot_name_postfix, snapshots_path, time_tuple):
        for face_name in self._faces:
            snapshot_file_name = f"{snapshots_path}/{face_name}{snapshot_name_postfix}"
            self.snapshot(face_name, snapshot_file_name, time_tuple)
            gc.collect()

    def snapshot(self, face_name, snapshot_file_name, time_tuple):
        if not face_name or not self._path_exists(f"{self._faces_path}/{face_name}"):
            print(f"Face does not exist: {face_name}")
            return
        
        self._face_screen.clean()
        self._show_face(face_name, time_tuple)
        snapshot = lv.snapshot_take(self._face_screen, lv.img.CF.TRUE_COLOR_ALPHA)
        size = self._face_screen.get_width() * self._face_screen.get_height() * 4
        data = snapshot.data.__dereference__(size)
        with open(snapshot_file_name, "wb") as f:
            f.write(data)

        lv.snapshot_free(snapshot)
        self._face.dispose()
        print(f"Snapshot file: {snapshot_file_name} ({size} bytes)")

    def _init_lvgl(self):
        lv.init()

        import SDL as SDL
        SDL.init(w=_WIDTH, h=_HEIGHT, auto_refresh=False)

        import lv_utils as lv_utils
        lv_utils.event_loop(refresh_cb=SDL.refresh, asynchronous=True)

        # Register SDL display driver
        factor = 4
        buffer_size = (_WIDTH * _HEIGHT * lv.color_t.__SIZE__) // factor
        disp_buf = lv.disp_draw_buf_t()
        buffer1 = bytearray(buffer_size)
        disp_buf.init(buffer1, None, buffer_size // lv.color_t.__SIZE__)
        disp_drv = lv.disp_drv_t()
        disp_drv.init()
        disp_drv.draw_buf = disp_buf
        disp_drv.flush_cb = SDL.monitor_flush
        disp_drv.hor_res = _WIDTH
        disp_drv.ver_res = _HEIGHT
        display = disp_drv.register()
        display.set_default()

        # Register SDL mouse driver
        indev_drv = lv.indev_drv_t()
        indev_drv.init()
        indev_drv.type = lv.INDEV_TYPE.POINTER
        indev_drv.read_cb = SDL.mouse_read
        indev_drv.disp = lv.disp_get_default()
        indev_drv.register()

    def _init_lvgl_fs(self):
        lv_fs_drv = lv.fs_drv_t()
        LVGL_FS_Driver(self._root_path, lv_fs_drv, _DRIVE_LETTER, _FS_CACHE_SIZE)

    def _init_lvgl_image_decoders(self):
        lv.img.cache_set_size(_IMG_CACHE_COUNT)
        lv.split_jpeg_init()

    def _create_screen(self):
        screen = lv.obj()
        screen.remove_style_all()
        screen.set_style_bg_color(lv.color_black(), 0)
        screen.set_style_bg_opa(lv.OPA.COVER, 0)
        screen.set_style_text_color(lv.color_white(), 0)
        return screen

    def _init_menu_screen(self):
        self._menu_screen = self._create_screen()
        screen = self._menu_screen
        screen.set_size(lv.pct(100), lv.pct(100))
        screen.set_style_pad_ver(10, 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        screen.set_style_pad_row(10, lv.STATE.DEFAULT)

        # Faces dropdown
        dd = lv.dropdown(screen)
        dd.set_width(_MENU_ITEM_WIDTH)
        dd.set_options("\n".join(self._faces))
        self._face_selector_dropdown = dd

        # Show button
        button = lv.btn(screen)
        button.set_size(_MENU_ITEM_WIDTH, _MENU_ITEM_HEIGHT)
        button.add_event_cb(self._show_button_cb, lv.EVENT.CLICKED, None)
        label = lv.label(button)
        label.set_text("Show")
        label.center()

        # Reload list button
        button = lv.btn(screen)
        button.set_size(_MENU_ITEM_WIDTH, _MENU_ITEM_HEIGHT)
        button.set_style_bg_color(lv.color_hex(0x00CC00), 0)
        button.add_event_cb(self._reload_button_cb, lv.EVENT.CLICKED, None)
        label = lv.label(button)
        label.set_text("Reload list")
        label.center()

        # Exit button
        button = lv.btn(screen)
        button.set_size(_MENU_ITEM_WIDTH, _MENU_ITEM_HEIGHT)
        button.set_style_bg_color(lv.color_hex(0xFF0000), 0)
        button.add_event_cb(self._exit_button_cb, lv.EVENT.CLICKED, None)
        label = lv.label(button)
        label.set_text("Exit")
        label.center()

    def _init_face_screen(self):
        self._face_screen = self._create_screen()
        self._face_screen.add_event_cb(self._face_screen_click_cb, lv.EVENT.CLICKED, None)
    
    def _load_faces_list(self):
        faces = [entry[0] for entry in os.ilistdir(self._faces_path) if entry[1] == _TYPE_DIRECTORY and not entry[0].startswith("_")]
        faces.sort()
        self._faces = faces

    def _show_button_cb(self, event):
        face_name = self._faces[self._face_selector_dropdown.get_selected()]
        self._show_face(face_name)
    
    def _reload_button_cb(self, event):
        current_face_name = self._faces[self._face_selector_dropdown.get_selected()]
        self._load_faces_list()
        if current_face_name in self._faces:
            self._face_selector_dropdown.set_selected(self._faces.index(current_face_name))

    def _exit_button_cb(self, event):
        self._is_running = False

    def _show_menu(self):
        lv.scr_load(self._menu_screen)

    def _show_face(self, name, time_tuple = None):
        lv.scr_load(self._face_screen)
        self._face = Face(self._face_screen, self._faces_path, name)
        self._face.show(time_tuple)

    def _face_screen_click_cb(self, event):
        if self._face:
            self._face.dispose()
        self._face = None

        # If left or right side is touched, then show previous/next face
        show_other_face = False
        w = self._face_screen.get_width()
        m = int(w * _MARGIN_PERCENT / 100)
        p = lv.point_t()
        event.get_indev().get_point(p)
        index = self._face_selector_dropdown.get_selected()
        if p.x < m:
            index = max(0, index - 1)
            show_other_face = True
        elif p.x > w - m:
            index = min(len(self._faces) - 1, index + 1)
            show_other_face = True

        if show_other_face:
            self._face_selector_dropdown.set_selected(index)
            self._show_face(self._faces[index])
        else:
            self._show_menu()

    def _path_exists(self, path):
        try:
            stat = os.stat(path)
            return stat[0] & _TYPE_DIRECTORY > 0
        except:
            return False


# ************************************
# Program entry point
# ************************************
app = App()

def get_time_tuple(arg):
    return tuple(map(lambda x: int(x), arg.strip("()").replace(" ", "").split(",")))

arg1 = sys.argv[1] if len(sys.argv) > 1 else None

# No argument: show preview screen
if arg1 == None:
    uasyncio.run(app.loop())
    sys.exit()

# Show help
if arg1 == "--help":
    print(_USAGE)
    sys.exit()

# Take snapshot of all faces
if arg1 == "--snapshot-for-all":
    try:
        snapshot_name_postfix = sys.argv[2]
        snapshots_path = sys.argv[3]
        time_tuple = get_time_tuple(sys.argv[4]) if len(sys.argv) > 3 else None
    except:
        print(_USAGE)
        sys.exit(1)

    app.snapshot_all(snapshot_name_postfix, snapshots_path, time_tuple)
    sys.exit(0)
    
# Show or take snapshot of a given face
face_name = arg1
snapshot_file_name = sys.argv[2] if len(sys.argv) > 2 else None
time_tuple = get_time_tuple(sys.argv[3]) if len(sys.argv) > 3 else None
if snapshot_file_name:
    app.snapshot(face_name, snapshot_file_name, time_tuple)
else:
    uasyncio.run(app.loop(face_name))
