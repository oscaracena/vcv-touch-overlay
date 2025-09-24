#!/usr/bin/env python

# (C) 2025, Oscar Aceña

import sys
import signal
import logging
import time
from argparse import ArgumentParser
from threading import Thread

from PyQt5.QtWidgets import QApplication, QWidget, QTapAndHoldGesture
from PyQt5.QtCore import Qt, QPoint, QEvent, QRect
from PyQt5.QtGui import QPainter, QPen, QColor
from Xlib.protocol import event
from Xlib import display, X


# https://doc.qt.io/archives/qt-5.15/gestures-overview.html
# https://utcc.utoronto.ca/~cks/space/blog/unix/XTwoWaysToSendEvents


# VCV Rack 2 required settings:
# - Mouse wheel: zoom
# - Lock cursor while dragging: false
# - Knob mode: relative rotary
# - Control knobs with mouse wheel: true
# - VCV app maximized (not in fullscreen), without topbar (see unite gnome-shell ext.)


log = logging.getLogger()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


class VCVRackProxy:
    def __init__(self, win_name="vcv rack", on_ready_cb=None):
        self._display = display.Display()
        self._root = self._display.screen().root
        self._win = self._get_window(self._root, win_name)

        if self._win is None:
            log.warning("VCV Rack 2 app not found!! Is it running? I'll keep searching...")
            self._send_event = self._no_window_warn
            Thread(target=self._find_vcv_app, args=[win_name, on_ready_cb], daemon=True).start()
        else:
            self._send_event = self._send_event_to_win
            if callable(on_ready_cb):
                on_ready_cb()

    def _no_window_warn(self, *args, **kwargs):
        log.warning(" No window defined, nothing can be done.")

    def _get_window(self, parent, name):
        if name in (parent.get_wm_name() or "").lower():
            return parent

        for child in parent.query_tree().children:
            if result := self._get_window(child, name):
                return result
        return None

    def _find_vcv_app(self, win_name, on_ready):
        while True:
            self._win = self._get_window(self._root, win_name)
            if self._win is not None:
                self._send_event = self._send_event_to_win
                log.info("VCV Rack 2 app finally found!")
                if callable(on_ready):
                    on_ready()
                return
            time.sleep(1)

    def _send_event_to_win(self, EventType, x, y, state=0, detail=0, sync=True):
        ev = EventType(
            time = X.CurrentTime,
            root = self._root,
            window = self._win,
            same_screen = 1,
            child = X.NONE,
            root_x = int(x),
            root_y = int(y),
            event_x = int(x),
            event_y = int(y),
            state = state,
            detail = detail,
        )
        self._win.send_event(ev, propagate=True)
        if sync:
            self._display.sync()

    @property
    def ready(self):
        return self._win is not None

    def left_press(self, x, y):
        log.debug(f"___ left press ({x}, {y})")
        self._send_event(event.ButtonPress, x, y, detail=1)

    def left_release(self, x, y):
        log.debug(f"___ left release ({x}, {y})")
        self._send_event(event.ButtonRelease, x, y, detail=1)

    def middle_press(self, x, y):
        log.debug(f"___ middle press ({x}, {y})")
        self._send_event(event.ButtonPress, x, y, detail=2)

    def middle_release(self, x, y):
        log.debug(f"___ middle release ({x}, {y})")
        self._send_event(event.ButtonRelease, x, y, detail=2)

    def right_press(self, x, y):
        log.debug(f"___ right press ({x}, {y})")
        self._send_event(event.ButtonPress, x, y, detail=3)

    def right_release(self, x, y):
        log.debug(f"___ right release ({x}, {y})")
        self._send_event(event.ButtonRelease, x, y, detail=3)

    def right_click(self, x, y):
        log.debug(f"___ right click ({x}, {y})")
        self._send_event(event.ButtonPress, x, y, detail=3)
        self._send_event(event.ButtonRelease, x, y, detail=3)

    def wheel_up(self, x, y):
        log.debug(f"___ wheel up ({x}, {y})")
        self._send_event(event.ButtonPress, x, y, detail=4)
        self._send_event(event.ButtonRelease, x, y, detail=4)

    def wheel_down(self, x, y):
        log.debug(f"___ wheel down ({x}, {y})")
        self._send_event(event.ButtonPress, x, y, detail=5)
        self._send_event(event.ButtonRelease, x, y, detail=5)

    def key_press(self, keysym, mask=0, sync=True):
        log.debug(f"___ key press (keysym: {keysym}, mask: {mask})")
        code = self._display.keysym_to_keycode(keysym)
        self._send_event(event.KeyPress, 0, 0, sync=sync, state=mask, detail=code)

    def key_release(self, keysym, mask=0, sync=True):
        log.debug(f"___ key release (keysym: {keysym}, mask: {mask})")
        code = self._display.keysym_to_keycode(keysym)
        self._send_event(event.KeyRelease, 0, 0, sync=sync, state=mask, detail=code)


class TransparentOverlay(QWidget):

    GS_TAP    = "tap"
    GS_DRAG   = "drag"
    GS_SCROLL = "scroll"
    GS_ZOOM   = "zoom"
    GS_RCLICK = "right click"

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.showFullScreen()

        # widgets and event setups
        self._close_btn = None
        self._label_btn = None
        self._vcv_ready = False
        self._compact = False

        self.grabGesture(Qt.TapGesture)
        self.grabGesture(Qt.TapAndHoldGesture)
        self.grabGesture(Qt.PanGesture)
        self.grabGesture(Qt.PinchGesture)
        QTapAndHoldGesture.setTimeout(500)

        self.__current_gesture = None
        self._current_pos = (0, 0)
        self._current_zoom = 0.0
        self._touch_start = (0, 0)
        self._touch_ts = 0

        self._prx = VCVRackProxy(on_ready_cb=self._on_vcv_ready)
        if not self._prx.ready:
            self._on_toggle_mode()

        log.info("Ready. Wait for events...")

    @property
    def _current_gesture(self):
        return self.__current_gesture

    @_current_gesture.setter
    def _current_gesture(self, value):
        log.debug(" " * 25 + f"GESTURE: {value}")
        self.__current_gesture = value

    def _on_vcv_ready(self):
        self._vcv_ready = True
        if self._compact:
            self._on_toggle_mode()

    def _get_menu_label(self):
        label_text = "touch overlay"
        fm = self.fontMetrics()
        text_width = fm.width(label_text)
        text_height = fm.height()
        margin = 10
        rect_width = text_width + 2 * margin + 20
        rect_height = text_height + 8
        return label_text, rect_width, rect_height

    def _on_toggle_mode(self):
        if not self._compact:
            _, rect_width, rect_height = self._get_menu_label()
            self.showNormal()
            self.setFixedSize(rect_width, rect_height)
            screen = QApplication.desktop().screenGeometry()
            self.move((screen.width() - rect_width) // 2, 0)
        else:
            self.setFixedSize(QApplication.desktop().screenGeometry().size())
            self.showFullScreen()

        self._compact = not self._compact
        self.update()

    def paintEvent(self, event):
        color = QColor(78, 129, 218, 150)
        if not self._vcv_ready:
            color = QColor(80, 80, 80, 150)
        if self._compact:
            color = QColor(255, 120, 120, 150)
        painter = QPainter(self)
        pen = QPen(color, 1)
        painter.setPen(pen)

        if not self._compact:
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        label_text, rect_width, rect_height = self._get_menu_label()
        rect_x = (self.width() - rect_width) // 2
        rect_y = 0
        rect = QRect(rect_x, rect_y, rect_width, rect_height)

        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRect(rect)

        painter.setPen(QColor(0, 0, 0))
        self._label_btn = QRect(rect_x, rect_y, rect_width - 20, rect_height)
        painter.drawText(self._label_btn, Qt.AlignCenter, label_text)

        self._close_btn = QRect(rect.right() - 25, rect_y + 4, 20, rect_height - 8)
        painter.drawText(self._close_btn, Qt.AlignCenter, "✕")

    def keyPressEvent(self, ev):
        # if key up/down, then do a mouse scroll (to go up/down in menus)
        x, y = self._touch_start
        if ev.key() == Qt.Key_Up:
            return self._prx.wheel_up(x, y)
        if ev.key() == Qt.Key_Down:
            return self._prx.wheel_down(x, y)

        ks = ev.nativeVirtualKey()
        sc = ev.nativeScanCode()
        log.debug(f"recived key press (keysym: {ks}, sc: {sc})")
        self._prx.key_press(ks, mask=ev.nativeModifiers())

    def keyReleaseEvent(self, ev):
        if ev.key() in (Qt.Key_Up, Qt.Key_Down):
            return

        ks = ev.nativeVirtualKey()
        sc = ev.nativeScanCode()
        log.debug(f"recived key release (keysym: {ks}, sc: {sc})")
        self._prx.key_release(ks, mask=ev.nativeModifiers())

    def wheelEvent(self, ev):
        if ev.source() != Qt.MouseEventNotSynthesized:
            return

        log.debug(f"mouse wheel event (delta: {ev.angleDelta()})")
        x, y = (p := ev.globalPosition()) and int(p.x()), int(p.y())
        if ev.angleDelta().y() > 0:
            self._prx.wheel_up(x, y)
        else:
            self._prx.wheel_down(x, y)

    def mousePressEvent(self, ev):
        # skip own widget area
        if self._close_btn and self._close_btn.contains(ev.pos()):
            return QApplication.quit()
        if self._label_btn and self._label_btn.contains(ev.pos()):
            return self._on_toggle_mode()

        log.debug("mouse press event")
        self._touch_start = int(ev.globalX()), int(ev.globalY())
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        x, y = ev.globalX(), ev.globalY()
        log.debug("mouse release event")

        if self._current_gesture in (self.GS_TAP, self.GS_DRAG):
            self._prx.left_release(x, y)
            self._current_gesture = None

        log.debug("-" * 40 + "\n")

    def mouseMoveEvent(self, ev):
        x, y = ev.globalX(), ev.globalY()

        delta = (QPoint(x, y) - QPoint(*self._touch_start)).manhattanLength()
        if delta > 5:

            # delayed click
            if self._current_gesture == self.GS_TAP:
                log.debug(f"mouse move event ({x}, {y}, ts: {time.monotonic()})")
                self._current_gesture = self.GS_DRAG
                self._prx.left_press(x, y)

        self._current_pos = (int(x), int(y))

    def tapGestureEvent(self, ev):
        x, y = (p := ev.position()) and int(p.x()), int(p.y())

        if ev.state() == Qt.GestureStarted:
            log.debug("tap started")
            self._current_gesture = self.GS_TAP
            self._touch_ts = time.monotonic()

        elif ev.state() == Qt.GestureFinished:
            log.debug("tap finished")

            # run single click
            if self._current_gesture == self.GS_TAP:
                self._prx.left_press(x, y)
                self._prx.left_release(x, y)
                self._current_gesture = None

            elif self._current_gesture == self.GS_DRAG:
                self._prx.left_release(x, y)
                self._current_gesture = None

        elif ev.state() == Qt.GestureCanceled:
            log.debug("tap canceled")

        return True

    def tapAndHoldGestureEvent(self, ev):
        x, y = (p := ev.position()) and int(p.x()), int(p.y())

        if ev.state() == Qt.GestureStarted:
            log.debug("tap and hold started")

            if self._current_gesture == self.GS_TAP:
                self._current_gesture = self.GS_RCLICK
                self._prx.right_press(x, y)

        elif ev.state() == Qt.GestureFinished:
            log.debug("tap and hold finished")
            if self._current_gesture == self.GS_RCLICK:
                self._prx.right_release(x, y)
                self._current_gesture = None

        elif ev.state() == Qt.GestureCanceled:
            log.debug("tap and hold canceled")

        elif ev.state() == Qt.GestureUpdated:
            log.debug("tap and hold updated")

        return True

    def panGestureEvent(self, ev):
        x, y = self._current_pos

        if ev.state() == Qt.GestureStarted:
            log.debug("pan started")
            if self._current_gesture == self.GS_DRAG:
                self._prx.left_release(x, y)
                self._prx.middle_press(x, y)
                self._current_gesture = self.GS_SCROLL

            elif self._current_gesture is None:
                self._prx.middle_press(x, y)
                self._current_gesture = self.GS_SCROLL

        elif ev.state() == Qt.GestureFinished:
            log.debug("pan finished")
            if self._current_gesture == self.GS_SCROLL:
                self._prx.middle_release(x, y)
                self._current_gesture = None

        elif ev.state() == Qt.GestureCanceled:
            log.debug("pan canceled")

        return True

    def pinchGestureEvent(self, ev):
        x, y = (p := ev.centerPoint()) and int(p.x()), int(p.y())

        if ev.state() == Qt.GestureStarted:
            log.debug(f"pinch started (ts: {time.monotonic()}")

        elif ev.state() == Qt.GestureFinished:
            log.debug("pinch finished")
            self._current_zoom = 0

        elif ev.state() == Qt.GestureCanceled:
            log.debug("pinch canceled")

        elif ev.state() == Qt.GestureUpdated:
            threshold = 0.15
            easing = threshold * 3

            if self._current_gesture == self.GS_SCROLL:
                # avoid zooming too soon
                if (time.monotonic() - self._touch_ts) * 1000 > 20:
                    # avoid zooming until a minimal distance is pinched
                    if abs(ev.totalScaleFactor() - 1.0) > easing:

                        delta = ev.scaleFactor() - 1.0
                        self._current_zoom += delta

                        if self._current_zoom - easing > threshold:
                            log.debug(f"pinch updated (zoom +1, total: {ev.totalScaleFactor()})")
                            self._current_zoom = 0
                            self._prx.wheel_up(x, y)

                        elif self._current_zoom + easing < -threshold:
                            log.debug(f"pinch updated (zoom -1, total: {ev.totalScaleFactor()})")
                            self._current_zoom = 0
                            self._prx.wheel_down(x, y)

        return True

    def event(self, ev):
        # NOTE: several possible events may be active at the same time
        if ev.type() == QEvent.Gesture:
            handled = []
            if tap := ev.gesture(Qt.TapGesture):
                handled.append(self.tapGestureEvent(tap))
            if hold := ev.gesture(Qt.TapAndHoldGesture):
                handled.append(self.tapAndHoldGestureEvent(hold))
            # pinch has precedence, so run it first
            if pinch := ev.gesture(Qt.PinchGesture):
                handled.append(self.pinchGestureEvent(pinch))
            if pan := ev.gesture(Qt.PanGesture):
                handled.append(self.panGestureEvent(pan))
            return any(handled)

        return super().event(ev)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--debug", action="store_true",
        help="set logging level to debug")

    args = parser.parse_args()
    if args.debug:
        log.setLevel(logging.DEBUG)

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    overlay = TransparentOverlay()
    try:
        app.exec_()
    except Exception as err:
        pass
    log.info("Application finished.")
    sys.exit()
