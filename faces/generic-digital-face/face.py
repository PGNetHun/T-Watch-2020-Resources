import utime
import gc
import lvgl as lv
import uasyncio
import ujson
from micropython import const

from system.classes.face import FaceBase
import system.device as device
from system.hw.interfaces.pmu import IPMU

import system.path_helper as path_helper
import libraries.lvgl_helper.color_helper as color_helper

_CONFIG_FILE = "generic-digital-face.config"
_FACE_FILE = "face.json"

_EVENT_LOAD_FACE = const(1)
_EVENT_FACE_TICK = const(2)
_EVENT_CLEANUP = const(3)

_SLEEP_MS = const(1000)

_MARGIN_PERCENT = const(20)

_FONTS_PATH = "S:fonts/"

_WEEK_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_WEEK_DAYS_SHORT = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
_MONTHS_SHORT = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

_PLACEHOLDERS = {
    "{YYYY}": lambda app, time_tuple: f"{time_tuple[0]:04d}",
    "{MM}": lambda app, time_tuple: f"{time_tuple[1]:02d}",
    "{DD}": lambda app, time_tuple: f"{time_tuple[2]:02d}",
    "{HH}": lambda app, time_tuple: f"{time_tuple[3]:02d}",
    "{mm}": lambda app, time_tuple: f"{time_tuple[4]:02d}",
    "{ss}": lambda app, time_tuple: f"{time_tuple[5]:02d}",
    "{day}": lambda app, time_tuple: _WEEK_DAYS[time_tuple[6]],
    "{day_short}": lambda app, time_tuple: _WEEK_DAYS_SHORT[time_tuple[6]],
    "{month}": lambda app, time_tuple: _MONTHS[time_tuple[1] - 1],
    "{month_short}": lambda app, time_tuple: _MONTHS_SHORT[time_tuple[1] - 1],
    "{battery_percent}": lambda app, time_tuple: str(app._pmu.get_battery_percent()) if app._pmu else ""
}


class Face(FaceBase):
    def init(self):
        super().init()

        self._face_names = self._get_face_names()
        self._face_name = None
        self._is_face_loaded = False
        self._is_font_loading = False
        self._container = None
        self._labels = []
        self._fonts = {}
        self._pmu: IPMU = device.get_module(device.ModuleType.PMU)
        self._is_gesture_in_progress = False

        self._init_screen()

        self.subscribe_event(_EVENT_LOAD_FACE, self._load_face)
        self.subscribe_event(_EVENT_FACE_TICK, self._face_tick)
        self.subscribe_event(_EVENT_CLEANUP, self._cleanup)

    async def run(self):
        if len(self._face_names) == 0:
            self.log.error(f"No faces found!")
            return

        self._face_name = self._get_last_face_name()
        if not self._face_name in self._face_names:
            self._face_name = self._face_names[0]
            self._set_last_face_name(self._face_name)

        self.publish_event(_EVENT_LOAD_FACE)
        self._loop_task = uasyncio.create_task(self._inner_loop())
        await super().run()

    def terminate(self):
        self._loop_task.cancel()
        if self._face_name != self._get_last_face_name():
            self._set_last_face_name(self._face_name)
        self._cleanup()
        super().terminate()

    def _init_screen(self):
        self.screen.add_event_cb(self._click_cb, lv.EVENT.CLICKED, None)
        self.screen.add_event_cb(self._gesture_cb, lv.EVENT.GESTURE, None)

    def _cleanup(self):
        if not self._container:
            return

        self.screen.clean()
        self._labels.clear()
        for font in self._fonts.values():
            font.free()
            del font
        self._fonts.clear()

        lv.img.cache_invalidate_src(None)
        gc.collect()

    def _load_face(self):
        self._is_face_loaded = False

        try:
            self._container = self.screen

            self.log.info(f"Load face: {self._face_name} (Free memory: {gc.mem_free():,} bytes)")

            face_path = path_helper.join(self.base_path, self._face_name)
            with open(f"{face_path}/{_FACE_FILE}", "r") as f:
                face_config = ujson.load(f)

            if face_config["version"] != "1":
                self.log.warning("Unknown face config version:", face_config["version"])
                return

            self._load_background(face_config, face_path)
            self._load_labels(face_config)

            self._is_face_loaded = True
        except Exception as e:
            self.log.exc(e, f"Failed to load face: {self._face_name}")

    def _load_background(self, face_config, face_path):
        if "background" not in face_config:
            return

        cfg = face_config["background"]
        if "color" in cfg:
            color = color_helper.LV_HEX_COLOR(cfg.get("color"))
            self.screen.set_style_bg_color(color, lv.STATE.DEFAULT)

        if "image" in cfg:
            import libraries.lvgl_helper.image_helper as image_helper
            image_path = f"{face_path}/{cfg.get('image')}"
            try:
                image = image_helper.show(self.screen, image_path, lv.ALIGN.CENTER, 0, 0)
                self._container = image
            except:
                self.log.error(f"Failed to background image: {image_path}")

    def _load_labels(self, face_config):
        if "labels" not in face_config:
            return

        self._is_font_loading = True

        __part_main = lv.PART.MAIN
        __default_align = lv.ALIGN.TOP_LEFT
        __hex_to_color = color_helper.LV_HEX_COLOR
        __create_label = lv.label
        __lv_align = lv.ALIGN
        __font_load = lv.font_load
        __labels = face_config["labels"]

        for cfg in __labels:
            __cfg_get = cfg.get
            text = __cfg_get("text", "")
            color = __hex_to_color(__cfg_get("color", "#000"))
            font_name = __cfg_get("font", None)
            x = __cfg_get("x", 0)
            y = __cfg_get("y", 0)
            align_text = __cfg_get("align", "TOP_LEFT")
            align = __lv_align.__dict__[align_text] if hasattr(__lv_align, align_text) else __default_align

            label = __create_label(self._container)
            label.set_style_text_color(color, __part_main)
            label.set_recolor(True)
            label.align(align, x, y)
            label.set_text("")

            if font_name:
                font_name = _FONTS_PATH + font_name
                try:
                    # TODO: Slow line:
                    font = self._fonts.get(font_name, None)
                    if not font:
                        font = __font_load(font_name)
                        self._fonts[font_name] = font
                    label.set_style_text_font(font, __part_main)
                except Exception as e:
                    self.log.exc(e, f"Failed to load font: {font_name}")

            self._labels.append({
                "lv_label": label,
                "text": text,
                "value": ""
            })

        self._is_font_loading = False

    async def _inner_loop(self):
        event_tick = _EVENT_FACE_TICK
        sleep = uasyncio.sleep_ms
        sleep_ms = _SLEEP_MS
        while 1:
            self.publish_event(event_tick)
            await sleep(sleep_ms)

    def _face_tick(self):
        if self._is_face_loaded:
            self._update_labels()

    def _update_labels(self):
        if self._is_font_loading:
            return

        time_tuple = utime.localtime()
        for label in self._labels:
            text = label["text"]

            for key, transform_cb in _PLACEHOLDERS.items():
                if key in text:
                    text = text.replace(key, transform_cb(self, time_tuple))

            if text != label["value"]:
                label["value"] = text
                label["lv_label"].set_text(text)

    def _click_cb(self, event):
        if self._is_gesture_in_progress:
            self._is_gesture_in_progress = False
            return
        
        # If left or right side is touched, then show previous/next face
        w = self.screen.get_width()
        m = int(w * _MARGIN_PERCENT / 100)
        p = lv.point_t()
        event.get_indev().get_point(p)
        if p.x < m:
            self._previous_face()
            return
        elif p.x > w - m:
            self._next_face()
            return

        self.exit()

    def _gesture_cb(self, event: lv.event_t):
        self._is_gesture_in_progress = True
        indev = event.get_indev()
        direction = indev.get_gesture_dir()
        if direction == lv.DIR.LEFT:
            self._next_face()
        elif direction == lv.DIR.RIGHT:
            self._previous_face()

    def _previous_face(self):
        index = self._face_names.index(self._face_name)
        index -= 1
        if index < 0:
            index = len(self._face_names) - 1
        self._face_name = self._face_names[index]
        self.publish_event(_EVENT_CLEANUP)
        self.publish_event(_EVENT_LOAD_FACE)

    def _next_face(self):
        index = self._face_names.index(self._face_name)
        index += 1
        if index >= len(self._face_names):
            index = 0
        self._face_name = self._face_names[index]
        self.publish_event(_EVENT_CLEANUP)
        self.publish_event(_EVENT_LOAD_FACE)

    def _get_face_names(self):
        names = [face for face in path_helper.get_directories(self.base_path) if face[0].isalpha() or face[0].isdigit()]
        names.sort()
        return names

    def _get_last_face_name(self):
        import system.services.config as config_service
        config = config_service.load(_CONFIG_FILE)
        return config.get("face") if config else None

    def _set_last_face_name(self, face):
        import system.services.config as config_service
        config = dict({"face": face})
        config_service.save(_CONFIG_FILE, config)
