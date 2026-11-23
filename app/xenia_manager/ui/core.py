"""Small pygame UI toolkit: a stack of list screens driven by controller,
keyboard or mouse. Works fullscreen (Big Screen mode) or in a window (F1)."""

from __future__ import annotations

import os
import queue
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import pygame

# ---- actions -----------------------------------------------------------------
UP, DOWN, LEFT, RIGHT, ACCEPT, BACK, OPTIONS, PAGE_UP, PAGE_DOWN, QUIT = (
    "up", "down", "left", "right", "accept", "back", "options", "pgup", "pgdn", "quit")

KEYMAP = {
    pygame.K_UP: UP, pygame.K_DOWN: DOWN, pygame.K_LEFT: LEFT, pygame.K_RIGHT: RIGHT,
    pygame.K_RETURN: ACCEPT, pygame.K_KP_ENTER: ACCEPT, pygame.K_SPACE: ACCEPT,
    pygame.K_ESCAPE: BACK, pygame.K_BACKSPACE: BACK, pygame.K_TAB: OPTIONS, pygame.K_x: OPTIONS,
    pygame.K_PAGEUP: PAGE_UP, pygame.K_PAGEDOWN: PAGE_DOWN,
}

# ---- theme -------------------------------------------------------------------
BG = (16, 18, 20)
PANEL = (28, 31, 35)
ROW = (36, 40, 45)
ROW_SEL = (16, 124, 16)
TEXT = (232, 234, 237)
DIM = (150, 156, 163)
ACCENT = (82, 196, 82)
WARN = (232, 168, 56)
ERR = (232, 84, 84)


@dataclass
class Item:
    label: str
    action: Optional[Callable[[], Any]] = None      # ACCEPT
    value: Optional[Callable[[], str]] = None       # right-aligned text, re-evaluated each frame
    left: Optional[Callable[[], Any]] = None
    right: Optional[Callable[[], Any]] = None
    options: Optional[Callable[[], Any]] = None     # X / Tab
    hint: str = ""
    enabled: bool = True
    image: Optional[str] = None
    header: bool = False                            # non-selectable section title


class Screen:
    title = ""
    footer = "A Select   B Back"

    def __init__(self, app: "App"):
        self.app = app
        self.items: list[Item] = []
        self.sel = 0
        self.scroll = 0
        self.subtitle = ""

    # subclasses fill self.items here; called on push and after children close
    def build(self) -> None:
        pass

    def on_resume(self) -> None:
        keep = self.sel
        self.build()
        self.sel = min(keep, max(0, len(self.items) - 1))
        self._skip_headers(1)

    def _skip_headers(self, step: int) -> None:
        n = len(self.items)
        if not n:
            return
        for _ in range(n):
            if not self.items[self.sel].header:
                return
            self.sel = (self.sel + step) % n

    def current(self) -> Optional[Item]:
        if 0 <= self.sel < len(self.items):
            return self.items[self.sel]
        return None

    def move(self, step: int) -> None:
        if not self.items:
            return
        self.sel = (self.sel + step) % len(self.items)
        self._skip_headers(1 if step > 0 else -1)

    def handle(self, action: str) -> None:
        it = self.current()
        if action == UP:
            self.move(-1)
        elif action == DOWN:
            self.move(1)
        elif action == PAGE_UP:
            self.sel = max(0, self.sel - self.app.visible_rows())
            self._skip_headers(1)
        elif action == PAGE_DOWN:
            self.sel = min(len(self.items) - 1, self.sel + self.app.visible_rows())
            self._skip_headers(-1)
        elif action == BACK:
            self.app.pop()
        elif it is None or not it.enabled:
            return
        elif action == ACCEPT and it.action:
            self.app.call(it.action)
        elif action == LEFT and it.left:
            self.app.call(it.left)
        elif action == RIGHT and it.right:
            self.app.call(it.right)
        elif action == ACCEPT and it.right:
            self.app.call(it.right)
        elif action == OPTIONS and it.options:
            self.app.call(it.options)


class Dialog:
    """Modal box with buttons (message, confirm, progress)."""

    def __init__(self, title: str, text: str, buttons: list[tuple[str, Optional[Callable]]]):
        self.title, self.text, self.buttons = title, text, buttons
        self.sel = 0
        self.closed = False

    def handle(self, app: "App", action: str) -> None:
        if not self.buttons:
            return
        if action in (LEFT, UP):
            self.sel = (self.sel - 1) % len(self.buttons)
        elif action in (RIGHT, DOWN):
            self.sel = (self.sel + 1) % len(self.buttons)
        elif action == BACK:
            self.closed = True
            cb = self.buttons[-1][1] if len(self.buttons) > 1 else self.buttons[0][1]
            if cb and len(self.buttons) == 1:
                app.call(cb)
        elif action == ACCEPT:
            self.closed = True
            cb = self.buttons[self.sel][1]
            if cb:
                app.call(cb)


class Task(Dialog):
    """Runs work on a thread with a progress bar; result goes to on_done."""

    def __init__(self, title: str, work: Callable[[Callable[[float, str], None]], Any],
                 on_done: Optional[Callable[[Any], None]] = None):
        super().__init__(title, "Working...", [])
        self.progress = -1.0
        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.on_done = on_done

        def report(frac: float, text: str = "") -> None:
            self.q.put(("p", frac, text))

        def runner() -> None:
            try:
                res = work(report)
                self.q.put(("ok", res))
            except Exception as e:  # shown to the user
                traceback.print_exc()
                self.q.put(("err", e))
        threading.Thread(target=runner, daemon=True).start()

    def poll(self, app: "App") -> None:
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "p":
                    self.progress, self.text = msg[1], msg[2] or self.text
                elif msg[0] == "ok":
                    self.closed = True
                    if self.on_done:
                        app.call(lambda: self.on_done(msg[1]))
                    app.refresh()
                else:
                    self.closed = True
                    app.message("Something went wrong", str(msg[1]), error=True)
                    app.refresh()
        except queue.Empty:
            pass


class App:
    def __init__(self, title: str, bigscreen: bool):
        os.environ.setdefault("SDL_VIDEO_ALLOW_SCREENSAVER", "0")
        pygame.display.init()
        pygame.font.init()
        pygame.joystick.init()
        self.bigscreen = bigscreen
        if bigscreen:
            self.surf = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            pygame.mouse.set_visible(False)
        else:
            self.surf = pygame.display.set_mode((1280, 760), pygame.RESIZABLE)
        pygame.display.set_caption(title)
        self.title = title
        self.stack: list[Screen] = []
        self.dialog: Optional[Dialog] = None
        self.running = True
        self.pads: dict[int, Any] = {}
        self.axis_state: dict[tuple, int] = {}
        self.repeat_action: Optional[str] = None
        self.repeat_at = 0.0
        self.images: dict[str, Any] = {}
        self.toast_text = ""
        self.toast_until = 0.0
        self.held: set[str] = set()
        try:
            from pygame._sdl2 import controller as ctl
            ctl.init()
            self.ctl = ctl
        except Exception:
            self.ctl = None
        self._fonts()
        self._open_pads()

    # ---- setup ----
    def _fonts(self) -> None:
        h = self.surf.get_height()
        self.row_h = max(34, int(h * 0.058))
        self.f_title = pygame.font.Font(None, int(self.row_h * 1.25))
        self.f_row = pygame.font.Font(None, int(self.row_h * 0.78))
        self.f_small = pygame.font.Font(None, int(self.row_h * 0.6))

    def _open_pads(self) -> None:
        for i in range(pygame.joystick.get_count()):
            self._add_pad(i)

    def _add_pad(self, index: int) -> None:
        try:
            if self.ctl and self.ctl.is_controller(index):
                pad = self.ctl.Controller(index)
                self.pads[pad.as_joystick().get_instance_id()] = pad
            else:
                js = pygame.joystick.Joystick(index)
                js.init()
                self.pads[js.get_instance_id()] = js
        except Exception:
            pass

    # ---- stack ----
    def push(self, screen: Screen) -> None:
        screen.build()
        screen._skip_headers(1)
        self.stack.append(screen)

    def pop(self) -> None:
        if len(self.stack) > 1:
            self.stack.pop()
            self.stack[-1].on_resume()
        else:
            self.confirm("Exit", "Close Xenia Manager?", self.quit)

    def refresh(self) -> None:
        if self.stack:
            self.stack[-1].on_resume()

    def quit(self) -> None:
        self.running = False

    def call(self, fn: Callable) -> None:
        try:
            fn()
        except Exception as e:
            traceback.print_exc()
            self.message("Something went wrong", str(e), error=True)
        if self.stack and self.dialog is None:
            self.stack[-1].on_resume()

    def run_external(self, fn: Callable[[], Any]) -> Any:
        """Hand the screen to another program (e.g. Xenia Netplay), then come back."""
        pygame.display.quit()
        try:
            rc = fn()
        finally:
            pygame.display.init()
            if self.bigscreen:
                self.surf = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            else:
                self.surf = pygame.display.set_mode((1280, 760), pygame.RESIZABLE)
            pygame.display.set_caption(self.title)
            self.images.clear()
            self._fonts()
        return rc

    # ---- dialogs ----
    def message(self, title: str, text: str, error: bool = False, then: Optional[Callable] = None) -> None:
        self.dialog = Dialog(("! " if error else "") + title, text, [("OK", then)])

    def confirm(self, title: str, text: str, yes: Callable, yes_label: str = "Yes") -> None:
        self.dialog = Dialog(title, text, [(yes_label, yes), ("Cancel", None)])

    def task(self, title: str, work, on_done=None) -> None:
        self.dialog = Task(title, work, on_done)

    def toast(self, text: str) -> None:
        self.toast_text, self.toast_until = text, time.monotonic() + 2.5

    def visible_rows(self) -> int:
        return max(3, (self.surf.get_height() - self._list_top() - self.row_h * 2) // (self.row_h + 6))

    def _list_top(self) -> int:
        return int(self.row_h * 2.9)

    # ---- input ----
    def _pad_button(self, button: int, is_ctl: bool) -> Optional[str]:
        if is_ctl:
            m = {
                pygame.CONTROLLER_BUTTON_A: ACCEPT, pygame.CONTROLLER_BUTTON_B: BACK,
                pygame.CONTROLLER_BUTTON_X: OPTIONS, pygame.CONTROLLER_BUTTON_Y: OPTIONS,
                pygame.CONTROLLER_BUTTON_DPAD_UP: UP, pygame.CONTROLLER_BUTTON_DPAD_DOWN: DOWN,
                pygame.CONTROLLER_BUTTON_DPAD_LEFT: LEFT, pygame.CONTROLLER_BUTTON_DPAD_RIGHT: RIGHT,
                pygame.CONTROLLER_BUTTON_LEFTSHOULDER: PAGE_UP,
                pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: PAGE_DOWN,
            }
            if button == pygame.CONTROLLER_BUTTON_START:
                self.held.add("start")
            if button == pygame.CONTROLLER_BUTTON_BACK:
                self.held.add("select")
            if {"start", "select"} <= self.held:
                return QUIT
            return m.get(button)
        return {0: ACCEPT, 1: BACK, 2: OPTIONS, 3: OPTIONS, 4: PAGE_UP, 5: PAGE_DOWN}.get(button)

    def _events(self) -> list[str]:
        acts: list[str] = []
        for ev in pygame.event.get():
            t = ev.type
            if t == pygame.QUIT:
                acts.append(QUIT)
            elif t == pygame.VIDEORESIZE and not self.bigscreen:
                self.surf = pygame.display.set_mode((max(800, ev.w), max(500, ev.h)), pygame.RESIZABLE)
                self._fonts()
            elif t == pygame.KEYDOWN:
                a = KEYMAP.get(ev.key)
                if ev.key == pygame.K_q and (ev.mod & pygame.KMOD_CTRL):
                    a = QUIT
                if a:
                    acts.append(a)
                    if a in (UP, DOWN, LEFT, RIGHT):
                        self._start_repeat(a)
            elif t == pygame.KEYUP:
                self.repeat_action = None
            elif t == getattr(pygame, "CONTROLLERBUTTONDOWN", -1):
                a = self._pad_button(ev.button, True)
                if a:
                    acts.append(a)
                    if a in (UP, DOWN, LEFT, RIGHT):
                        self._start_repeat(a)
            elif t == getattr(pygame, "CONTROLLERBUTTONUP", -1):
                self.repeat_action = None
                self.held.discard({pygame.CONTROLLER_BUTTON_START: "start",
                                   pygame.CONTROLLER_BUTTON_BACK: "select"}.get(ev.button, ""))
            elif t == getattr(pygame, "CONTROLLERAXISMOTION", -1):
                acts += self._axis(("c", ev.instance_id, ev.axis), ev.value / 32767.0,
                                   ev.axis in (pygame.CONTROLLER_AXIS_LEFTY,), ev.axis in (pygame.CONTROLLER_AXIS_LEFTX,))
            elif t == pygame.JOYBUTTONDOWN and not self._is_ctl(ev.instance_id):
                a = self._pad_button(ev.button, False)
                if a:
                    acts.append(a)
            elif t == pygame.JOYHATMOTION and not self._is_ctl(ev.instance_id):
                x, y = ev.value
                a = UP if y > 0 else DOWN if y < 0 else LEFT if x < 0 else RIGHT if x > 0 else None
                if a:
                    acts.append(a)
                    self._start_repeat(a)
                else:
                    self.repeat_action = None
            elif t == pygame.JOYAXISMOTION and not self._is_ctl(ev.instance_id):
                acts += self._axis(("j", ev.instance_id, ev.axis), ev.value, ev.axis == 1, ev.axis == 0)
            elif t in (pygame.JOYDEVICEADDED, getattr(pygame, "CONTROLLERDEVICEADDED", -2)):
                self._add_pad(ev.device_index)
            elif t == pygame.MOUSEWHEEL:
                acts.append(UP if ev.y > 0 else DOWN)
            elif t == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
                acts += self._click(ev.pos, ev.button)
        return acts

    def _is_ctl(self, instance_id: int) -> bool:
        pad = self.pads.get(instance_id)
        return pad is not None and self.ctl is not None and isinstance(pad, self.ctl.Controller)

    def _axis(self, key: tuple, value: float, vertical: bool, horizontal: bool) -> list[str]:
        prev = self.axis_state.get(key, 0)
        cur = 1 if value > 0.6 else -1 if value < -0.6 else 0
        if cur == prev:
            return []
        self.axis_state[key] = cur
        if cur == 0:
            self.repeat_action = None
            return []
        a = None
        if vertical:
            a = DOWN if cur > 0 else UP
        elif horizontal:
            a = RIGHT if cur > 0 else LEFT
        if a:
            self._start_repeat(a)
            return [a]
        return []

    def _start_repeat(self, a: str) -> None:
        self.repeat_action, self.repeat_at = a, time.monotonic() + 0.4

    def _click(self, pos, button) -> list[str]:
        if button == 3:
            return [BACK]
        if self.dialog:
            return [ACCEPT]
        scr = self.stack[-1]
        idx = self._row_at(pos)
        if idx is None:
            return []
        if idx == scr.sel:
            return [ACCEPT]
        scr.sel = idx
        return []

    def _row_at(self, pos) -> Optional[int]:
        scr = self.stack[-1]
        x, y = pos
        top = self._list_top()
        if x > self._list_width() + 40:
            return None
        i = (y - top) // (self.row_h + 6)
        idx = scr.scroll + i
        if y >= top and 0 <= idx < len(scr.items) and not scr.items[idx].header:
            return idx
        return None

    # ---- drawing ----
    def _list_width(self) -> int:
        w = self.surf.get_width()
        scr = self.stack[-1] if self.stack else None
        has_img = scr and any(it.image for it in scr.items)
        return int(w * (0.62 if has_img else 1.0)) - 80

    def _text(self, font, text: str, color, pos, max_w: Optional[int] = None, right: bool = False):
        if max_w is not None:
            while text and font.size(text)[0] > max_w:
                text = text[:-4] + "..." if len(text) > 4 else ""
        img = font.render(text, True, color)
        x, y = pos
        if right:
            x -= img.get_width()
        self.surf.blit(img, (x, y))
        return img.get_width()

    def _image(self, path: str):
        if path in self.images:
            return self.images[path]
        img = None
        try:
            img = pygame.image.load(path).convert_alpha()
        except Exception:
            img = None
        self.images[path] = img
        return img

    def draw(self) -> None:
        s = self.surf
        W, H = s.get_size()
        s.fill(BG)
        scr = self.stack[-1]
        rh = self.row_h
        # header
        self._text(self.f_title, scr.title, TEXT, (40, int(rh * 0.6)), W - 300)
        self._text(self.f_small, self.title, ACCENT, (W - 40, int(rh * 0.75)), right=True)
        if scr.subtitle:
            self._text(self.f_small, scr.subtitle, DIM, (42, int(rh * 1.85)), W - 80)
        # rows
        top = self._list_top()
        lw = self._list_width()
        vis = self.visible_rows()
        if scr.sel < scr.scroll:
            scr.scroll = scr.sel
        elif scr.sel >= scr.scroll + vis:
            scr.scroll = scr.sel - vis + 1
        scr.scroll = max(0, min(scr.scroll, max(0, len(scr.items) - vis)))
        y = top
        for idx in range(scr.scroll, min(len(scr.items), scr.scroll + vis)):
            it = scr.items[idx]
            if it.header:
                self._text(self.f_small, it.label.upper(), ACCENT, (48, y + rh * 0.35), lw)
                y += rh + 6
                continue
            selected = idx == scr.sel
            pygame.draw.rect(s, ROW_SEL if selected else ROW, (40, y, lw, rh), border_radius=8)
            col = TEXT if it.enabled else DIM
            val = ""
            if it.value:
                try:
                    val = it.value() or ""
                except Exception:
                    val = "?"
            vw = self.f_row.size(val)[0] + 30 if val else 0
            ty = y + (rh - self.f_row.get_height()) // 2
            self._text(self.f_row, it.label, col, (58, ty), lw - 40 - vw)
            if val:
                arrows = it.left is not None or it.right is not None
                shown = f"<  {val}  >" if arrows and selected else val
                self._text(self.f_row, shown, TEXT if selected else DIM, (40 + lw - 18, ty), right=True)
            y += rh + 6
        if len(scr.items) > vis:
            frac = scr.scroll / max(1, len(scr.items) - vis)
            bar_h = max(30, int((H - top - rh * 2) * vis / len(scr.items)))
            by = top + int((H - top - rh * 2 - bar_h) * frac)
            pygame.draw.rect(s, ROW, (44 + lw, by, 6, bar_h), border_radius=3)
        # side image (box art)
        cur = scr.current()
        if cur and cur.image:
            img = self._image(cur.image)
            if img:
                pw, ph = W - lw - 140, H - top - rh * 2
                iw, ih = img.get_size()
                k = min(pw / iw, ph / ih)
                scaled = pygame.transform.smoothscale(img, (max(1, int(iw * k)), max(1, int(ih * k))))
                s.blit(scaled, (lw + 100 + (pw - scaled.get_width()) // 2, top))
        # footer: hint + controls
        if cur and cur.hint:
            self._text(self.f_small, cur.hint, DIM, (42, H - int(rh * 1.6)), W - 80)
        self._text(self.f_small, scr.footer, DIM, (W - 40, H - int(rh * 0.85)), right=True)
        if self.toast_text and time.monotonic() < self.toast_until:
            tw = self.f_row.size(self.toast_text)[0] + 40
            pygame.draw.rect(s, PANEL, ((W - tw) // 2, H - rh * 3, tw, rh), border_radius=10)
            self._text(self.f_row, self.toast_text, ACCENT, ((W - tw) // 2 + 20, H - rh * 3 + rh * 0.18))
        if self.dialog:
            self._draw_dialog()
        pygame.display.flip()

    def _wrap(self, text: str, font, width: int) -> list[str]:
        out: list[str] = []
        for para in text.split("\n"):
            line = ""
            for word in para.split(" "):
                trial = (line + " " + word).strip()
                if font.size(trial)[0] <= width or not line:
                    line = trial
                else:
                    out.append(line)
                    line = word
            out.append(line)
        return out

    def _draw_dialog(self) -> None:
        d = self.dialog
        s = self.surf
        W, H = s.get_size()
        rh = self.row_h
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        s.blit(shade, (0, 0))
        dw = min(W - 80, int(rh * 18))
        lines = self._wrap(d.text, self.f_row, dw - 60)[:14]
        dh = int(rh * 2.2 + len(lines) * self.f_row.get_height() * 1.1 + rh * 1.6)
        x, y = (W - dw) // 2, (H - dh) // 2
        pygame.draw.rect(s, PANEL, (x, y, dw, dh), border_radius=14)
        col = ERR if d.title.startswith("!") else TEXT
        self._text(self.f_title, d.title.lstrip("! "), col, (x + 30, y + 20), dw - 60)
        ty = y + int(rh * 1.6)
        for ln in lines:
            self._text(self.f_row, ln, TEXT, (x + 30, ty), dw - 60)
            ty += int(self.f_row.get_height() * 1.1)
        if isinstance(d, Task):
            bw = dw - 60
            pygame.draw.rect(s, ROW, (x + 30, y + dh - rh * 1.1, bw, rh * 0.4), border_radius=6)
            if d.progress >= 0:
                fill = int(bw * min(1.0, d.progress))
            else:
                fill = int(bw * 0.25)
                off = int((time.monotonic() * 300) % (bw - fill))
                pygame.draw.rect(s, ROW_SEL, (x + 30 + off, y + dh - rh * 1.1, fill, rh * 0.4), border_radius=6)
                fill = 0
            if fill:
                pygame.draw.rect(s, ROW_SEL, (x + 30, y + dh - rh * 1.1, fill, rh * 0.4), border_radius=6)
            return
        bx = x + dw - 30
        for i in range(len(d.buttons) - 1, -1, -1):
            label = d.buttons[i][0]
            bw = self.f_row.size(label)[0] + 40
            bx -= bw
            pygame.draw.rect(s, ROW_SEL if i == d.sel else ROW, (bx, y + dh - rh * 1.3, bw, rh), border_radius=8)
            self._text(self.f_row, label, TEXT, (bx + 20, y + dh - rh * 1.3 + (rh - self.f_row.get_height()) // 2))
            bx -= 16

    # ---- main loop ----
    def run(self) -> int:
        clock = pygame.time.Clock()
        while self.running:
            acts = self._events()
            now = time.monotonic()
            if self.repeat_action and now >= self.repeat_at:
                acts.append(self.repeat_action)
                self.repeat_at = now + 0.08
            for a in acts:
                if a == QUIT:
                    self.running = False
                    break
                if self.dialog:
                    if isinstance(self.dialog, Task):
                        continue
                    d = self.dialog
                    d.handle(self, a)
                    if d.closed and self.dialog is d:
                        self.dialog = None
                        self.refresh()
                else:
                    self.stack[-1].handle(a)
            if isinstance(self.dialog, Task):
                d = self.dialog
                d.poll(self)
                if d.closed and self.dialog is d:
                    self.dialog = None
            self.draw()
            clock.tick(60)
        pygame.quit()
        return 0
