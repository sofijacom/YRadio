#!/usr/bin/env python3

"""
yradio_tray.py - native tray icon (StatusNotifierItem, works on Wayland/KDE) for the yradio script.

Options:  --icon ICON  --text TOOLTIP
Needs PyQt6 or PySide6.
"""
import argparse
import os
import select
import subprocess
import sys

QT = None
try:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QAction, QIcon
    from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
    QT = "PyQt6"
except ImportError:
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QAction, QIcon
        from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
        QT = "PySide6"
    except ImportError:
        QT = None


def parse_menu(spec):
    """'Label! cmd!icon|Label2! cmd2' -> [(label, cmd, icon), ...]; '---' / '-' = separator"""
    items = []
    for item in spec.split("|"):
        item = item.strip()
        if not item:
            continue
        parts = [p.strip() for p in item.split("!")]
        label = parts[0]
        cmd = parts[1] if len(parts) > 1 else ""
        icon = parts[2] if len(parts) > 2 else ""
        items.append((label, cmd, icon))
    return items


def make_icon(name):
    if name and os.path.isfile(name):
        return QIcon(name)
    icon = QIcon.fromTheme(name) if name else QIcon()
    if icon.isNull():
        icon = QIcon.fromTheme("audio-x-generic")
    return icon


def run(cmd):
    # stdin must not be inherited: it is the command pipe of this helper
    subprocess.Popen(cmd, shell=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


class Helper:
    def __init__(self, app, args):
        self.app = app
        self.click_cmd = args.command
        self.buf = b""
        self.menu = None
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(make_icon(args.icon))
        self.tray.setToolTip(args.text)
        self.tray.activated.connect(self.on_activated)
        self.tray.show()
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("yradio_tray: no system tray available", file=sys.stderr)
        # poll stdin (works the same with PyQt6 and PySide6)
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll)
        self.timer.start(150)

    def on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger and self.click_cmd:
            run(self.click_cmd)

    def set_menu(self, spec):
        menu = QMenu()
        for label, cmd, icon in parse_menu(spec):
            if label in ("-", "---"):
                menu.addSeparator()
                continue
            act = QAction(label, menu)
            if icon:
                act.setIcon(make_icon(icon))
            if cmd:
                act.triggered.connect(lambda checked=False, c=cmd: run(c))
            menu.addAction(act)
        self.tray.setContextMenu(menu)
        self.menu = menu            # keep a reference (the old menu is freed after this)

    def handle(self, line):
        if line.startswith("tooltip:"):
            self.tray.setToolTip(line[len("tooltip:"):])
        elif line.startswith("icon:"):
            self.tray.setIcon(make_icon(line[len("icon:"):].strip()))
        elif line.startswith("menu:"):
            self.set_menu(line[len("menu:"):])
        elif line.strip() == "quit":
            self.app.quit()

    def poll(self):
        fd = sys.stdin.fileno()
        try:
            while select.select([fd], [], [], 0)[0]:
                data = os.read(fd, 65536)
                if not data:                      # EOF: the yradio script is gone
                    self.app.quit()
                    return
                self.buf += data
        except OSError:
            self.app.quit()
            return
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            self.handle(line.decode("utf-8", "replace").rstrip("\r"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--icon", default="audio-x-generic")
    ap.add_argument("--text", default="YRadio")
    ap.add_argument("--command", default="")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if QT is None:
        print("yradio_tray: PyQt6 or PySide6 is not installed", file=sys.stderr)
        return 1
    if args.check:
        return 0

    app = QApplication(sys.argv[:1])
    app.setApplicationName("YRadio")
    app.setDesktopFileName("yradio")
    app.setQuitOnLastWindowClosed(False)
    helper = Helper(app, args)   # noqa: F841 (must stay alive)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
