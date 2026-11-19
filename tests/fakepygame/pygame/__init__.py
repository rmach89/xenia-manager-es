"""Tiny stand-in for pygame so the UI can be smoke-tested without a display.
Only what xenia_manager.ui uses is implemented; drawing calls do nothing."""

import itertools

_ids = itertools.count(1000)
QUIT, VIDEORESIZE, KEYDOWN, KEYUP, JOYBUTTONDOWN, JOYHATMOTION, JOYAXISMOTION, JOYDEVICEADDED, \
    MOUSEWHEEL, MOUSEBUTTONDOWN, CONTROLLERBUTTONDOWN, CONTROLLERBUTTONUP, CONTROLLERAXISMOTION, \
    CONTROLLERDEVICEADDED = (next(_ids) for _ in range(14))
FULLSCREEN = RESIZABLE = SRCALPHA = 1
KMOD_CTRL = 64
(K_UP, K_DOWN, K_LEFT, K_RIGHT, K_RETURN, K_KP_ENTER, K_SPACE, K_ESCAPE, K_BACKSPACE, K_TAB, K_x,
 K_PAGEUP, K_PAGEDOWN, K_q) = range(1, 15)
(CONTROLLER_BUTTON_A, CONTROLLER_BUTTON_B, CONTROLLER_BUTTON_X, CONTROLLER_BUTTON_Y,
 CONTROLLER_BUTTON_DPAD_UP, CONTROLLER_BUTTON_DPAD_DOWN, CONTROLLER_BUTTON_DPAD_LEFT,
 CONTROLLER_BUTTON_DPAD_RIGHT, CONTROLLER_BUTTON_LEFTSHOULDER, CONTROLLER_BUTTON_RIGHTSHOULDER,
 CONTROLLER_BUTTON_START, CONTROLLER_BUTTON_BACK) = range(12)
CONTROLLER_AXIS_LEFTX, CONTROLLER_AXIS_LEFTY = 0, 1

QUEUE = []


class Surface:
    def __init__(self, size=(1280, 720), *a):
        self._s = size

    def get_size(self): return self._s
    def get_width(self): return self._s[0]
    def get_height(self): return self._s[1]
    def fill(self, *a): pass
    def blit(self, *a): pass
    def convert_alpha(self): return self


class _Display:
    def init(self): pass
    def set_mode(self, size, *a): return Surface((1280, 720) if size == (0, 0) else size)
    def set_caption(self, *a): pass
    def flip(self): pass


class Font:
    def __init__(self, name, size): self.sz = size
    def size(self, text): return (int(len(text) * self.sz * 0.5), self.sz)
    def get_height(self): return self.sz
    def render(self, text, aa, col): return Surface(self.size(text))


class _FontMod:
    Font = Font
    def init(self): pass


class _Joy:
    def init(self): pass
    def get_count(self): return 0


class _Event:
    def get(self):
        out = list(QUEUE)
        QUEUE.clear()
        return out


class Ev:
    def __init__(self, type, **kw):
        self.type = type
        self.__dict__.update(kw)


class _Draw:
    def rect(self, *a, **k): pass


class _Mouse:
    def set_visible(self, *a): pass


class _Image:
    def load(self, p): return Surface((300, 400))


class _Transform:
    def smoothscale(self, s, size): return Surface(size)


class Clock:
    hook = None

    def tick(self, fps):
        if Clock.hook:
            Clock.hook()


class _Time:
    Clock = Clock


display, font, joystick, event = _Display(), _FontMod(), _Joy(), _Event()
draw, mouse, image, transform, time = _Draw(), _Mouse(), _Image(), _Transform(), _Time()


def quit(): pass
