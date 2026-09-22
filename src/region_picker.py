"""Native one-shot picker for the WeChat message area.

The picker deliberately stores geometry only.  It is shown over the selected
WeChat window, lets the user drag the *message list* (not the title or input
box), and writes normalized bounds to ``~/.config/jev-jarvis/region.json``.
No screen capture, OCR, or chat text is involved in this module.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import AppKit
import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFont,
    NSPanel,
    NSView,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSMakePoint, NSMakeRect, NSObject
from Quartz import CGDisplayBounds


REGION_FILE = Path.home() / ".config" / "jev-jarvis" / "region.json"
import os
if os.environ.get("SIDECHAT_MODE") == "1":
    from sidechat_providers import CONFIG_DIR
    REGION_FILE = CONFIG_DIR / "region.json"

MIN_WIDTH = 100.0
MIN_HEIGHT = 80.0
TOP_INSET = 0.015

_active_selection: "_RegionSelection | None" = None


def _clamped_rect(x1: float, y1: float, x2: float, y2: float,
                  width: float, height: float) -> tuple[float, float, float, float]:
    """Return a selection inside the window and below the reserved title strip.

    The tuple is ``left, bottom, right, top`` in Cocoa content coordinates.
    Keeping this independent of AppKit makes the critical geometry easy to
    verify without opening a window.
    """
    max_y = max(0.0, height * (1.0 - TOP_INSET))
    x1, x2 = sorted((max(0.0, min(width, x1)), max(0.0, min(width, x2))))
    y1, y2 = sorted((max(0.0, min(max_y, y1)), max(0.0, min(max_y, y2))))
    return x1, y1, x2, y2


def _normalised_region(left: float, bottom: float, right: float, top: float,
                       width: float, height: float) -> dict[str, float | int]:
    """Build the persisted geometry after clamping it to the picker content."""
    return {
        "version": 1,
        "width": round(width, 3),
        "height": round(height, 3),
        "left": round(left / width, 6),
        "top": round(1.0 - top / height, 6),
        "right": round(right / width, 6),
        "bottom": round(1.0 - bottom / height, 6),
    }


def _screen_for_window(window: dict):
    """Return the NSScreen containing most of a Quartz window's centre.

    CGWindow bounds use the Quartz global coordinate system (origin at the
    display's top-left); NSScreen uses Cocoa's bottom-left coordinate system.
    Matching by the display's CG bounds makes the conversion work on a second
    monitor too, including monitors placed above or left of the primary one.
    """
    cx = float(window["x"]) + float(window["w"]) / 2.0
    cy = float(window["y"]) + float(window["h"]) / 2.0
    closest = None
    closest_distance = float("inf")
    for screen in AppKit.NSScreen.screens():
        number = screen.deviceDescription().objectForKey_("NSScreenNumber")
        if number is None:
            continue
        bounds = CGDisplayBounds(int(number))
        left, top = bounds.origin.x, bounds.origin.y
        right, bottom = left + bounds.size.width, top + bounds.size.height
        if left <= cx <= right and top <= cy <= bottom:
            return screen, bounds
        dx = max(left - cx, 0.0, cx - right)
        dy = max(top - cy, 0.0, cy - bottom)
        distance = dx * dx + dy * dy
        if distance < closest_distance:
            closest, closest_distance = (screen, bounds), distance
    if closest:
        return closest
    screen = AppKit.NSScreen.mainScreen()
    if screen is None:
        raise RuntimeError("找不到可用显示器")
    number = screen.deviceDescription().objectForKey_("NSScreenNumber")
    return screen, CGDisplayBounds(int(number))


def _cocoa_frame(window: dict):
    """Convert one CGWindowList bounds dict into an NSScreen point rect."""
    screen, display = _screen_for_window(window)
    sf = screen.frame()
    sx = sf.size.width / display.size.width
    sy = sf.size.height / display.size.height
    x = sf.origin.x + (float(window["x"]) - display.origin.x) * sx
    y = sf.origin.y + (display.origin.y + display.size.height
                       - (float(window["y"]) + float(window["h"]))) * sy
    return NSMakeRect(x, y, float(window["w"]) * sx, float(window["h"]) * sy)


def _write_region(data: dict) -> None:
    """Persist only non-sensitive geometry with owner-only file permissions."""
    REGION_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGION_FILE.with_suffix(".json.tmp")
    encoded = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(encoded)
        os.replace(tmp, REGION_FILE)
        os.chmod(REGION_FILE, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class _PickerView(NSView):
    """Mouse and drawing surface for one selection session."""

    def initWithFrame_owner_(self, frame, owner):
        self = objc.super(_PickerView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.owner = owner
        self.start = None
        self.end = None
        self.error = ""
        return self

    def acceptsFirstResponder(self):
        return True

    def _local_point(self, event):
        return self.convertPoint_fromView_(event.locationInWindow(), None)

    def mouseDown_(self, event):
        point = self._local_point(event)
        self.start = point
        self.end = point
        self.error = ""
        self.setNeedsDisplay_(True)

    def mouseDragged_(self, event):
        if self.start is None:
            return
        self.end = self._local_point(event)
        self.setNeedsDisplay_(True)

    def mouseUp_(self, event):
        if self.start is None:
            return
        self.end = self._local_point(event)
        self.owner.finish(self._selection_rect())

    def keyDown_(self, event):
        if event.charactersIgnoringModifiers() == "\x1b":
            self.owner.cancel()
            return
        objc.super(_PickerView, self).keyDown_(event)

    def _selection_rect(self):
        if self.start is None or self.end is None:
            return None
        bounds = self.bounds()
        x1, y1, x2, y2 = _clamped_rect(
            self.start.x, self.start.y, self.end.x, self.end.y,
            bounds.size.width, bounds.size.height)
        return NSMakeRect(x1, y1, x2 - x1, y2 - y1)

    def drawRect_(self, _dirty):
        bounds = self.bounds()
        selection = self._selection_rect()
        dim = NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.38)
        if selection is None or selection.size.width < 1 or selection.size.height < 1:
            dim.setFill()
            NSBezierPath.fillRect_(bounds)
        else:
            # Four strips leave the selected chat area transparent and readable.
            x, y = selection.origin.x, selection.origin.y
            w, h = selection.size.width, selection.size.height
            dim.setFill()
            NSBezierPath.fillRect_(NSMakeRect(0, y + h, bounds.size.width, bounds.size.height - y - h))
            NSBezierPath.fillRect_(NSMakeRect(0, 0, bounds.size.width, y))
            NSBezierPath.fillRect_(NSMakeRect(0, y, x, h))
            NSBezierPath.fillRect_(NSMakeRect(x + w, y, bounds.size.width - x - w, h))
            blue = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.12, 0.55, 1.0, 1.0)
            blue.setStroke()
            path = NSBezierPath.bezierPathWithRect_(selection)
            path.setLineWidth_(2.0)
            path.stroke()

        message = self.error or "拖拽框选聊天消息区域（不含标题和输入框） · Esc 取消"
        attrs = {
            AppKit.NSFontAttributeName: NSFont.systemFontOfSize_(13),
            AppKit.NSForegroundColorAttributeName: NSColor.whiteColor(),
        }
        AppKit.NSAttributedString.alloc().initWithString_attributes_(message, attrs).drawAtPoint_(
            NSMakePoint(14, bounds.size.height - 28))


class _PickerPanel(NSPanel):
    """A borderless panel normally refuses key status; the picker needs Esc."""

    def canBecomeKeyWindow(self):
        return True


class _RegionSelection(NSObject):
    def initWithWindow_callback_(self, window, callback):
        self = objc.super(_RegionSelection, self).init()
        if self is None:
            return None
        self.window_info = dict(window)
        self.callback = callback
        self.panel = None
        self.view = None
        return self

    @objc.python_method
    def show(self):
        frame = _cocoa_frame(self.window_info)
        panel = _PickerPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered, False)
        panel.setLevel_(AppKit.NSFloatingWindowLevel + 1)
        panel.setOpaque_(False)
        panel.setHasShadow_(False)
        panel.setHidesOnDeactivate_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setIgnoresMouseEvents_(False)
        panel.setReleasedWhenClosed_(False)
        view = _PickerView.alloc().initWithFrame_owner_(
            NSMakeRect(0, 0, frame.size.width, frame.size.height), self)
        panel.setContentView_(view)
        self.panel, self.view = panel, view
        panel.makeKeyAndOrderFront_(None)
        panel.makeFirstResponder_(view)

    @objc.python_method
    def finish(self, rect):
        if rect is None or rect.size.width < MIN_WIDTH or rect.size.height < MIN_HEIGHT:
            if self.view is not None:
                self.view.error = (f"框选区域至少 {int(MIN_WIDTH)} × {int(MIN_HEIGHT)} 点，"
                                   "请重新拖拽")
                self.view.setNeedsDisplay_(True)
            return
        frame = self.panel.contentView().bounds()
        data = _normalised_region(
            rect.origin.x, rect.origin.y, rect.origin.x + rect.size.width,
            rect.origin.y + rect.size.height, frame.size.width, frame.size.height)
        try:
            _write_region(data)
        except OSError:
            # Keep the picker visible for a retry when the config directory is unavailable.
            if self.view is not None:
                self.view.error = "无法保存识别范围，请检查配置目录权限后重试"
                self.view.setNeedsDisplay_(True)
            return
        callback = self.callback
        self._close()
        if callback:
            callback(data)

    @objc.python_method
    def cancel(self):
        self._close()

    @objc.python_method
    def _close(self):
        global _active_selection
        if self.panel is not None:
            self.panel.orderOut_(None)
            self.panel.close()
        self.panel = None
        self.view = None
        _active_selection = None


def begin_selection(window_dict: dict, on_saved=None):
    """Show the native picker on the main thread and return its session object.

    ``window_dict`` is the WindowInfo mapping returned by perception.  Call this
    from the HUD's status-menu action; the supplied callback receives the saved
    geometry dictionary after a valid drag completes.
    """
    global _active_selection
    if _active_selection is not None:
        _active_selection.cancel()
    session = _RegionSelection.alloc().initWithWindow_callback_(window_dict, on_saved)
    _active_selection = session
    session.show()
    return session
