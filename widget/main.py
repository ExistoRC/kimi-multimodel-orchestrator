from __future__ import annotations

import json
import sys
import urllib.request

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .config import RUNTIME_FILE, model_catalog, read_json
from .i18n import translate
from .server import StatusService
from .state import StateStore
from .ui import STYLE, Bridge, EngineeringWindow


def activate_existing() -> bool:
    try:
        runtime = read_json(RUNTIME_FILE)
        base = f"http://{runtime['host']}:{runtime['port']}"
        headers = {"Authorization": f"Bearer {runtime['token']}"}
        health = urllib.request.Request(base + "/health", headers=headers)
        with urllib.request.urlopen(health, timeout=1) as response:
            if json.loads(response.read()).get("ok") is not True:
                return False
        body = json.dumps({"action": "show"}).encode("utf-8")
        command = urllib.request.Request(base + "/command", data=body, headers={**headers, "Content-Type": "application/json"})
        with urllib.request.urlopen(command, timeout=1) as response:
            return json.loads(response.read()).get("ok") is True
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False


def tray_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#67e8f9"))
    painter.setBrush(QColor("#0c2233"))
    painter.drawRoundedRect(3, 3, 58, 58, 16, 16)
    painter.setPen(QColor("#ecfeff"))
    painter.setFont(QFont("Consolas", 27, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "M")
    painter.end()
    return QIcon(pixmap)


def retranslate_tray(
    tray: QSystemTrayIcon,
    show_action: QAction,
    settings_action: QAction,
    quit_action: QAction,
    language: str,
) -> None:
    tray.setToolTip(translate("Kimi 多模型工程状态 · 单击显示/隐藏", language))
    show_action.setText(translate("显示 / 隐藏悬浮窗", language))
    settings_action.setText(translate("打开子代理设置", language))
    quit_action.setText(translate("退出悬浮窗", language))


def main() -> int:
    if activate_existing():
        return 0
    app = QApplication(sys.argv)
    app.setApplicationName("Kimi Multimodel Orchestrator")
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    try:
        default_main_model = model_catalog()["main_model"]
    except (OSError, ValueError):
        default_main_model = ""
    store = StateStore(default_main_model=default_main_model)
    bridge = Bridge()
    service = StatusService(store, lambda kind, value: bridge.command_received.emit(value) if kind == "command" else bridge.event_received.emit())
    service.start()
    window = EngineeringWindow(bridge)
    window.setStyleSheet(STYLE)
    window.update_state(store.snapshot())
    tray = QSystemTrayIcon(tray_icon(), app)
    tray.setToolTip("Kimi 多模型工程状态 · 单击显示/隐藏")
    menu = QMenu()
    show_action = QAction("显示 / 隐藏悬浮窗", menu)
    show_action.triggered.connect(lambda: window.hide_window() if window.isVisible() else window.show_window())
    settings_action = QAction("打开子代理设置", menu)
    settings_action.triggered.connect(lambda: window.handle_command("settings"))
    quit_action = QAction("退出悬浮窗", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(show_action)
    menu.addAction(settings_action)
    menu.addSeparator()
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    retranslate_tray(tray, show_action, settings_action, quit_action, window.settings["language"])
    window.language_changed.connect(lambda language: retranslate_tray(tray, show_action, settings_action, quit_action, language))
    tray.activated.connect(lambda reason: window.hide_window() if reason == QSystemTrayIcon.ActivationReason.Trigger and window.isVisible() else window.show_window() if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick} else None)
    tray.show()
    position = window.settings.get("position")
    if position:
        window.move(int(position[0]), int(position[1]))
    else:
        geometry = app.primaryScreen().availableGeometry()
        window.move(geometry.right() - window.width() - 24, geometry.bottom() - window.height() - 24)
    bridge.event_received.connect(lambda: window.update_state(store.snapshot()))
    bridge.command_received.connect(lambda action: app.quit() if action == "quit" else None)
    window.show()
    app.aboutToQuit.connect(window.save_position)
    app.aboutToQuit.connect(service.stop)
    app.aboutToQuit.connect(tray.hide)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
