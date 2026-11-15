from __future__ import annotations

import math
import threading
from copy import deepcopy
from typing import Any

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .config import load_routing, load_settings, model_catalog, routing_tiers, save_routing, save_settings
from .i18n import translate

PHASES = {
    "idle": ("空闲", "等待新的工程任务"),
    "planning": ("主代理规划中", "正在理解目标与拆分任务"),
    "working": ("工程进行中", "子代理正在执行分配的工作"),
    "waiting": ("等待授权", "需要处理权限请求后继续"),
    "review": ("待主代理验收", "子代理交付不等于验收通过"),
    "finished": ("本轮结束", "主代理已结束本轮响应"),
    "error": ("执行出错", "请返回 Kimi Code 查看详情"),
    "interrupted": ("已中断", "本轮由用户中断"),
}
PHASE_COLORS = {
    "idle": "#64748b",
    "planning": "#a78bfa",
    "working": "#22d3ee",
    "waiting": "#fbbf24",
    "review": "#34d399",
    "finished": "#94a3b8",
    "error": "#fb7185",
    "interrupted": "#fbbf24",
}
STATUS_TEXT = {
    "working": "工作中",
    "delivered": "待验收",
    "closed": "本轮结束",
    "error": "出错",
    "stopped": "已停止",
}


def retranslate_tree(root: QWidget, language: str) -> None:
    for widget in (root, *root.findChildren(QWidget)):
        if isinstance(widget, (QLabel, QAbstractButton)):
            widget.setText(translate(widget.text(), language))
        if isinstance(widget, QComboBox):
            for index in range(widget.count()):
                widget.setItemText(index, translate(widget.itemText(index), language))
        if widget.toolTip():
            widget.setToolTip(translate(widget.toolTip(), language))


STYLE = """
QWidget {
    color: #dbe7f3;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 12px;
}
QFrame#root {
    background: rgba(8, 14, 27, 248);
    border: 1px solid #2b8091;
    border-radius: 16px;
}
QFrame#topRule {
    background: #1a3a4d;
    border: none;
    max-height: 1px;
}
QLabel#eyebrow {
    color: #67e8f9;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
}
QLabel#phase {
    color: #f3f8fc;
    font-size: 21px;
    font-weight: 650;
}
QLabel#section {
    color: #7dd3e5;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 10px;
    font-weight: 600;
}
QLabel#muted, QLabel#detail {
    color: #8fa6ba;
}
QLabel#mono, QLabel#metricValue {
    font-family: "Cascadia Mono", "Consolas", monospace;
}
QLabel#metricValue {
    color: #ecfeff;
    font-size: 20px;
    font-weight: 600;
}
QLabel#metricLabel {
    color: #6f8ca3;
    font-size: 10px;
}
QFrame#metric, QFrame#taskCard, QFrame#settingsGroup {
    background: rgba(18, 31, 49, 220);
    border: 1px solid #203b4c;
    border-radius: 10px;
}
QFrame#taskCard[status="delivered"] {
    border-color: #285e58;
}
QLabel#taskTitle {
    color: #e6f1f8;
    font-size: 12px;
    font-weight: 600;
}
QLabel#taskMeta {
    color: #7f9fb3;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 10px;
}
QLabel#taskStatus {
    color: #67e8f9;
    font-size: 10px;
}
QPushButton {
    background: #14283a;
    border: 1px solid #2a5265;
    border-radius: 7px;
    color: #d9f7fb;
    padding: 6px 10px;
    min-height: 18px;
}
QPushButton:hover {
    background: #1b3b4d;
    border-color: #52c4d5;
}
QPushButton:pressed {
    background: #102231;
}
QPushButton#primary {
    background: #164e63;
    border-color: #22d3ee;
    color: #ecfeff;
    font-weight: 600;
}
QPushButton#ghost {
    background: transparent;
    border-color: #294252;
    color: #a9c0cf;
}
QComboBox {
    background: #101f30;
    border: 1px solid #2b4556;
    border-radius: 6px;
    padding: 6px 8px;
    min-height: 18px;
    color: #e1edf5;
}
QComboBox:hover { border-color: #45b7c8; }
QComboBox QAbstractItemView {
    background: #101f30;
    border: 1px solid #2b6575;
    selection-background-color: #1b6172;
    selection-color: #ecfeff;
    outline: none;
}
QComboBox QAbstractItemView::item {
    min-height: 26px;
    padding: 4px 8px;
    border-left: 3px solid transparent;
}
QComboBox QAbstractItemView::item:hover {
    background: rgba(34, 211, 238, 45);
    color: #ecfeff;
}
QComboBox QAbstractItemView::item:selected {
    background: rgba(34, 211, 238, 72);
    border-left-color: #22d3ee;
    color: #ecfeff;
}
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical {
    background: transparent;
    width: 7px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #315467;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSlider::groove:horizontal {
    height: 4px;
    background: #243e4f;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: #67e8f9;
}
QCheckBox { spacing: 8px; color: #c6d8e4; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #3b6576;
    border-radius: 4px;
    background: #101f30;
}
QCheckBox::indicator:checked { background: #1593a7; border-color: #67e8f9; }
QToolTip {
    background: #102535;
    color: #e7f6fb;
    border: 1px solid #3b8293;
    padding: 5px;
}
"""


class Bridge(QObject):
    event_received = Signal()
    command_received = Signal(str)


class DropdownComboBox(QComboBox):
    def showPopup(self) -> None:
        super().showPopup()
        popup = self.view().window()
        position = self.mapToGlobal(QPoint(0, self.height() + 4))
        screen = self.screen()
        if screen is None:
            popup.move(position)
            return
        available = screen.availableGeometry()
        width = max(self.width(), popup.width())
        height = max(1, min(popup.height(), available.bottom() - position.y() + 1))
        popup.setGeometry(position.x(), position.y(), width, height)


class StatusOrb(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._phase = "idle"
        self._tick = 0
        self.setFixedSize(18, 18)

    def set_phase(self, phase: str) -> None:
        self._phase = phase
        self.update()

    def advance(self) -> None:
        self._tick += 1
        if self._phase in {"working", "planning"}:
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(PHASE_COLORS.get(self._phase, "#64748b"))
        pulse = (math.sin(self._tick / 3.0) + 1) / 2 if self._phase in {"working", "planning"} else 0.4
        halo = QColor(color)
        halo.setAlphaF(0.10 + pulse * 0.15)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(self.rect())
        painter.setBrush(color)
        painter.drawEllipse(self.rect().center(), 4.5, 4.5)


class TaskCard(QFrame):
    def __init__(self, task: dict[str, Any], language: str) -> None:
        super().__init__()
        self.language = language
        self.setObjectName("taskCard")
        self.task_id = task["task_id"]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 9, 11, 9)
        layout.setSpacing(5)
        top = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("taskStatus")
        title = QLabel(task["summary"] or task["task_id"])
        title.setObjectName("taskTitle")
        title.setWordWrap(True)
        top.addWidget(title, 1)
        top.addWidget(self.status, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)
        self.meta = QLabel()
        self.meta.setObjectName("taskMeta")
        self.meta.setWordWrap(True)
        layout.addWidget(self.meta)
        self.update_task(task)

    def update_task(self, task: dict[str, Any], language: str | None = None) -> None:
        if language is not None:
            self.language = language
        self.setProperty("status", task["status"])
        self.status.setText(translate(STATUS_TEXT.get(task["status"], task["status"]), self.language))
        elapsed = format_duration(task["elapsed"])
        uncertainty = translate(" · 关联不确定", self.language) if task.get("uncertain") else ""
        self.meta.setText(f"{task['task_id']}  ·  {task['profile']}  ·  {task['tier']}\n{task['model']}  ·  {task['modality']}  ·  {elapsed}{uncertainty}")
        self.style().unpolish(self)
        self.style().polish(self)


class SettingsPage(QWidget):
    preferences_changed = Signal(dict)
    language_changed = Signal(str)
    save_succeeded = Signal(object)
    save_failed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.catalog = model_catalog()
        self.routing = deepcopy(load_routing())
        self.settings = load_settings()
        self.combos: dict[tuple[str, str], QComboBox] = {}
        self.saving = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(1, 1, 8, 24)
        self.content_layout.setSpacing(10)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        self._build_identity()
        self._build_routes()
        self._build_profiles()
        self._build_preferences()
        self.content_layout.addStretch(1)
        self.save_button = QPushButton("保存设置")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save)
        outer.addWidget(self.save_button)
        self.message = QLabel("路由变更从下一次子代理分派生效")
        self.message.setObjectName("muted")
        self.message.setWordWrap(True)
        outer.addWidget(self.message)
        self.save_succeeded.connect(self._save_succeeded)
        self.save_failed.connect(self._save_failed)
        retranslate_tree(self, self.settings["language"])
        self.retranslate_dynamic()

    @property
    def language(self) -> str:
        return self.settings["language"]

    def tr(self, text: str) -> str:
        return translate(text, self.language)

    def _group(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        group = QFrame()
        group.setObjectName("settingsGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(9)
        heading = QLabel(title)
        heading.setObjectName("section")
        layout.addWidget(heading)
        self.content_layout.addWidget(group)
        return group, layout

    def _build_identity(self) -> None:
        _, layout = self._group("CURRENT / 当前运行配置")
        self.main_model_value = QLabel()
        self.main_model_value.setObjectName("mono")
        self.main_model_value.setWordWrap(True)
        layout.addWidget(self.main_model_value)
        self.identity_note = QLabel()
        self.identity_note.setObjectName("muted")
        self.identity_note.setWordWrap(True)
        layout.addWidget(self.identity_note)
        self._update_identity()

    def _update_identity(self) -> None:
        main_model = self.catalog["main_model"]
        available = len(self.catalog["available"])
        pooled = len(self.catalog["pool"])
        if self.language == "en":
            self.main_model_value.setText(f"Main model: {main_model}")
            self.identity_note.setText(f"Model library {available} / pool {pooled}; aliases join on save. Main model: /\u2060model.")
        else:
            self.main_model_value.setText(f"主模型：{main_model}")
            self.identity_note.setText(f"模型库 {available} / 已入池 {pooled}；新选择保存时入池。主模型用 /\u2060model 管理。")

    def _build_routes(self) -> None:
        _, layout = self._group("ROUTING / 等级与模态模型")
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("编排模式"))
        self.mode_combo = DropdownComboBox()
        for text, value in (("两级：简单 / 复杂", "two-tier"), ("单级：统一执行", "single"), ("仅按模态", "modality"), ("自动分配（资料 + 规则）", "auto")):
            self.mode_combo.addItem(text, value)
        mode = self.routing.get("mode") if self.routing.get("version") == 2 else "two-tier"
        index = self.mode_combo.findData(mode if mode in {"two-tier", "single", "modality", "auto"} else "two-tier")
        self.mode_combo.setCurrentIndex(max(0, index))
        mode_row.addWidget(self.mode_combo, 1)
        layout.addLayout(mode_row)
        self.route_grid = QGridLayout()
        self.route_grid.setHorizontalSpacing(7)
        self.route_grid.setVerticalSpacing(8)
        layout.addLayout(self.route_grid)
        self.route_note = QLabel()
        self.route_note.setObjectName("muted")
        self.route_note.setWordWrap(True)
        layout.addWidget(self.route_note)
        self._populate_route_rows()
        self.mode_combo.currentIndexChanged.connect(self._populate_route_rows)

    def _eligible(self, modality: str) -> list[str]:
        required = {"image": "image_in", "video": "video_in"}.get(modality)
        aliases = []
        for alias in self.catalog["available"]:
            capabilities = self.catalog["models"][alias]["capabilities"]
            if "tool_use" not in capabilities:
                continue
            if required and required not in capabilities:
                continue
            aliases.append(alias)
        return aliases

    def _route_value(self, tier: str, modality: str) -> str:
        eligible = self._eligible(modality)
        route_key = "autoRoutes" if self.mode_combo.currentData() == "auto" else "routes"
        routes = self.routing.setdefault(route_key, {})
        current = routes.get(tier, {}).get(modality)
        if current in eligible:
            return current
        candidates = {
            "L1": ("L1", "L2", "L3", "any"),
            "L2": ("L2", "L3", "L1", "any"),
            "any": ("L2", "L3", "L1"),
        }[tier]
        for candidate in candidates:
            alias = routes.get(candidate, {}).get(modality)
            if alias in eligible:
                routes.setdefault(tier, {})[modality] = alias
                return alias
        return eligible[0] if eligible else ""

    def _update_route_note(self) -> None:
        if self.mode_combo.currentData() == "auto":
            self.route_note.setText(self.tr("自动分配按任务与模型资料选模型；以下仅作为缺少资料时的回退。可用 /kimi-multimodel-orchestrator:evaluate-models 更新公开参考分。"))
        else:
            self.route_note.setText(self.tr("同一模型可以复用于多个等级或模态，不要求每个选项不同。"))

    def _pool_display(self, alias: str) -> str:
        if alias in self.catalog["pool"]:
            return alias
        return f"{alias} (not in pool)" if self.language == "en" else f"{alias}（未入池）"

    def _populate_route_rows(self) -> None:
        self._update_route_note()
        while self.route_grid.count():
            item = self.route_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.combos = {}
        mode = self.mode_combo.currentData()
        tiers = routing_tiers({"version": 2, "mode": mode})
        for column, text in enumerate(("任务", "模型别名")):
            label = QLabel(text)
            label.setObjectName("metricLabel")
            self.route_grid.addWidget(label, 0, column)
        row = 1
        for tier in tiers:
            for modality in ("text", "image", "video"):
                label = "任意等级" if tier == "any" else tier
                self.route_grid.addWidget(QLabel(f"{label} · {modality}"), row, 0)
                combo = DropdownComboBox()
                for alias in self._eligible(modality):
                    model = self.catalog["models"][alias]
                    combo.addItem(self._pool_display(alias), alias)
                    combo.setItemData(combo.count() - 1, f"{model['display_name']}\n{model['model']}", Qt.ItemDataRole.ToolTipRole)
                current = self._route_value(tier, modality)
                index = combo.findData(current)
                if index >= 0:
                    combo.setCurrentIndex(index)
                combo.setMinimumContentsLength(12)
                self.route_grid.addWidget(combo, row, 1)
                self.route_grid.setRowMinimumHeight(row, 34)
                self.combos[(tier, modality)] = combo
                row += 1
        retranslate_tree(self, self.language)

    def retranslate_dynamic(self) -> None:
        self._update_identity()
        self._update_route_note()
        if not self.saving:
            self.message.setText(self.tr("路由变更从下一次子代理分派生效"))
        for combo in self.combos.values():
            for index in range(combo.count()):
                combo.setItemText(index, self._pool_display(combo.itemData(index)))

    def _build_profiles(self) -> None:
        _, layout = self._group("PROFILES / 固定权限档")
        profiles = self.routing.get("managedAgents", {})
        for name, permission in profiles.items():
            label = QLabel(f"{name}  ·  {permission}")
            label.setObjectName("mono")
            layout.addWidget(label)
        note = QLabel("权限档由 Agent 文件中的工具白名单强制执行；此页面不会动态放开工具。")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)

    def _build_preferences(self) -> None:
        _, layout = self._group("WIDGET / 悬浮窗")
        language_row = QHBoxLayout()
        language_row.addWidget(QLabel("界面语言"))
        self.language_combo = DropdownComboBox()
        self.language_combo.addItem("中文", "zh-CN")
        self.language_combo.addItem("English", "en")
        self.language_combo.setCurrentIndex(0 if self.language == "zh-CN" else 1)
        self.language_combo.currentIndexChanged.connect(lambda: self.language_changed.emit(self.language_combo.currentData()))
        language_row.addWidget(self.language_combo, 1)
        layout.addLayout(language_row)
        self.auto_start = QCheckBox("新会话自动启动悬浮窗")
        self.auto_start.setChecked(self.settings["auto_start"])
        layout.addWidget(self.auto_start)
        self.on_top = QCheckBox("窗口始终置顶")
        self.on_top.setChecked(self.settings["always_on_top"])
        layout.addWidget(self.on_top)
        row = QHBoxLayout()
        row.addWidget(QLabel("不透明度"))
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(65, 100)
        self.opacity.setValue(round(self.settings["opacity"] * 100))
        row.addWidget(self.opacity, 1)
        self.opacity_value = QLabel(f"{self.opacity.value()}%")
        self.opacity_value.setObjectName("mono")
        self.opacity.valueChanged.connect(lambda value: self.opacity_value.setText(f"{value}%"))
        row.addWidget(self.opacity_value)
        layout.addLayout(row)

    def save(self) -> None:
        if self.saving:
            return
        routing = deepcopy(self.routing)
        routing["version"] = 2
        routing["mode"] = self.mode_combo.currentData()
        route_key = "autoRoutes" if routing["mode"] == "auto" else "routes"
        for (tier, modality), combo in self.combos.items():
            alias = combo.currentData()
            if not alias:
                self.message.setText(f"{tier}/{modality}: no compatible model available" if self.language == "en" else f"{tier}/{modality} 没有兼容的模型可选")
                return
            routing[route_key][tier][modality] = alias
            definition = routing["models"].setdefault(alias, {"modalities": ["text"]})
            modalities = list(definition.get("modalities", ["text"]))
            if modality not in modalities:
                modalities.append(modality)
            definition["modalities"] = modalities
        settings = {
            **self.settings,
            "auto_start": self.auto_start.isChecked(),
            "always_on_top": self.on_top.isChecked(),
            "opacity": self.opacity.value() / 100,
        }
        self.saving = True
        self.save_button.setEnabled(False)
        self.save_button.setText(self.tr("正在校验并保存…"))
        self.mode_combo.setEnabled(False)
        self.language_combo.setEnabled(False)
        self.message.setText(self.tr("正在验证模型能力并将新选择加入子代理池"))
        self._save_thread = threading.Thread(target=self._save_worker, args=(routing, settings), daemon=True)
        self._save_thread.start()

    def _save_worker(self, routing: dict[str, Any], settings: dict[str, Any]) -> None:
        try:
            backups = save_routing(routing, self.catalog)
            save_settings(settings)
        except Exception as error:
            self.save_failed.emit(str(error))
            return
        self.save_succeeded.emit({"routing": routing, "settings": settings, "backups": backups})

    def _save_succeeded(self, result: dict[str, Any]) -> None:
        self.routing = result["routing"]
        self.settings = result["settings"]
        self.catalog = model_catalog()
        self._update_identity()
        self.preferences_changed.emit(self.settings)
        self._finish_save()
        backups = result["backups"]
        if self.language == "en":
            suffix = f"; config backup: {backups['config'].name}" if backups.get("config") else ""
            self.message.setText(f"Settings saved; routing applies to the next dispatch{suffix}")
        else:
            suffix = f"；配置备份 {backups['config'].name}" if backups.get("config") else ""
            self.message.setText(f"设置已保存，下一次分派生效{suffix}")

    def _save_failed(self, message: str) -> None:
        self._finish_save()
        self.message.setText(f"Save failed: {message}" if self.language == "en" else f"保存失败：{message}")

    def _finish_save(self) -> None:
        self.saving = False
        self.save_button.setEnabled(True)
        self.save_button.setText(self.tr("保存设置"))
        self.mode_combo.setEnabled(True)
        self.language_combo.setEnabled(True)

    def can_close(self) -> bool:
        return not self.saving


class EngineeringWindow(QWidget):
    language_changed = Signal(str)

    def __init__(self, bridge: Bridge) -> None:
        super().__init__()
        self.bridge = bridge
        self.settings = load_settings()
        self.snapshot: dict[str, Any] = {}
        self._drag_position = None
        self._task_cards: dict[str, TaskCard] = {}
        self._task_signature: tuple | None = None
        self.setObjectName("window")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Kimi 多模型工程状态")
        self.resize(self.settings["width"], self.settings["height"])
        self.setMinimumSize(400, 480)
        self.setMaximumSize(720, 900)
        self.setWindowOpacity(self.settings["opacity"])
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.settings["always_on_top"])
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        self.root = QFrame()
        self.root.setObjectName("root")
        root_layout.addWidget(self.root)
        shadow = QGraphicsDropShadowEffect(self.root)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.root.setGraphicsEffect(shadow)
        layout = QVBoxLayout(self.root)
        layout.setContentsMargins(16, 13, 16, 14)
        layout.setSpacing(11)
        self._build_header(layout)
        self.stack = QStackedWidget()
        self.status_page = QWidget()
        self._build_status_page(self.status_page)
        self.stack.addWidget(self.status_page)
        layout.addWidget(self.stack, 1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        bridge.event_received.connect(self._tick)
        bridge.command_received.connect(self.handle_command)
        retranslate_tree(self, self.settings["language"])
        self.setWindowTitle(translate(self.windowTitle(), self.settings["language"]))

    def _build_header(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        self.orb = StatusOrb()
        row.addWidget(self.orb)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        eyebrow = QLabel("MULTIMODEL // OPS")
        eyebrow.setObjectName("eyebrow")
        titles.addWidget(eyebrow)
        self.project = QLabel("尚未连接会话")
        self.project.setObjectName("mono")
        titles.addWidget(self.project)
        row.addLayout(titles, 1)
        hide = QPushButton("隐藏")
        hide.setObjectName("ghost")
        hide.setToolTip("隐藏到系统托盘；可从托盘 M 图标重新唤醒")
        hide.clicked.connect(self.hide_window)
        row.addWidget(hide)
        self.settings_button = QPushButton("设置")
        self.settings_button.setObjectName("ghost")
        self.settings_button.clicked.connect(self.handle_settings_navigation)
        row.addWidget(self.settings_button)
        layout.addLayout(row)
        rule = QFrame()
        rule.setObjectName("topRule")
        layout.addWidget(rule)

    def _build_status_page(self, page: QWidget) -> None:
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(11)
        self.phase = QLabel("空闲")
        self.phase.setObjectName("phase")
        layout.addWidget(self.phase)
        self.detail = QLabel("等待 Kimi Code 工程事件")
        self.detail.setObjectName("detail")
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        self.main_model = QLabel("MAIN  ·  等待 SessionStart")
        self.main_model.setObjectName("mono")
        self.main_model.setWordWrap(True)
        layout.addWidget(self.main_model)
        metrics = QHBoxLayout()
        metrics.setSpacing(7)
        self.active_metric = self._metric(metrics, "活跃子代理")
        self.pending_metric = self._metric(metrics, "待验收")
        self.elapsed_metric = self._metric(metrics, "本轮耗时")
        layout.addLayout(metrics)
        section = QLabel("SUBAGENTS / 实时任务")
        section.setObjectName("section")
        layout.addWidget(section)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.tasks_content = QWidget()
        self.tasks_layout = QVBoxLayout(self.tasks_content)
        self.tasks_layout.setContentsMargins(0, 0, 5, 0)
        self.tasks_layout.setSpacing(7)
        self.tasks_layout.addStretch(1)
        scroll.setWidget(self.tasks_content)
        layout.addWidget(scroll, 1)
        footer = QLabel("LOCAL ONLY  ·  数据来自 Kimi Hooks\n完成状态以主代理实际验收为准")
        footer.setObjectName("muted")
        footer.setStyleSheet("font-size: 10px;")
        layout.addWidget(footer)

    @staticmethod
    def _metric(layout: QHBoxLayout, label: str) -> QLabel:
        frame = QFrame()
        frame.setObjectName("metric")
        box = QVBoxLayout(frame)
        box.setContentsMargins(9, 8, 9, 8)
        box.setSpacing(1)
        value = QLabel("00")
        value.setObjectName("metricValue")
        box.addWidget(value)
        caption = QLabel(label)
        caption.setObjectName("metricLabel")
        box.addWidget(caption)
        layout.addWidget(frame, 1)
        return value

    def update_state(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot
        self._render()

    def _tick(self) -> None:
        self.orb.advance()
        if self.snapshot and self.stack.currentWidget() == self.status_page:
            if self.snapshot.get("phase") in {"planning", "working", "waiting"}:
                self.snapshot["turn_elapsed"] = self.snapshot.get("turn_elapsed", 0) + 1
            for task in self.snapshot.get("tasks", []):
                if task.get("status") == "working":
                    task["elapsed"] = task.get("elapsed", 0) + 1
            self._render()

    def _render(self) -> None:
        state = self.snapshot
        language = self.settings["language"]
        phase = state.get("phase", "idle")
        self.orb.set_phase(phase)
        phase_text = PHASES.get(phase, (phase, ""))
        self.phase.setText(translate(phase_text[0], language))
        detail = state.get("detail") or phase_text[1]
        self.detail.setText(translate(detail, language))
        self.project.setText(elide(state.get("project") or translate("当前项目", language), self.project.font(), 210))
        self.project.setToolTip(state.get("project") or state.get("title") or "")
        fallback_model = "Unmarked" if language == "en" else "未标记"
        self.main_model.setText(f"MAIN  ·  {state.get('main_model') or fallback_model}")
        self.active_metric.setText(f"{state.get('active_count', 0):02d}")
        self.pending_metric.setText(f"{state.get('pending_count', 0):02d}")
        self.elapsed_metric.setText(format_duration(state.get("turn_elapsed", 0), compact=True))
        tasks = state.get("tasks", [])
        signature = tuple((task["task_id"], task["status"]) for task in tasks)
        if signature != self._task_signature:
            self._rebuild_tasks(tasks)
            self._task_signature = signature
        for task in tasks:
            card = self._task_cards.get(task["task_id"])
            if card:
                card.update_task(task, language)

    def _rebuild_tasks(self, tasks: list[dict[str, Any]]) -> None:
        language = self.settings["language"]
        while self.tasks_layout.count():
            item = self.tasks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._task_cards = {}
        if not tasks:
            self.tasks_layout.addStretch(1)
            empty = QLabel(translate("暂无活跃子代理任务", language))
            empty.setObjectName("muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tasks_layout.addWidget(empty)
        else:
            for task in tasks:
                card = TaskCard(task, language)
                self._task_cards[task["task_id"]] = card
                self.tasks_layout.addWidget(card)
            if all(task.get("status") != "working" for task in tasks):
                inactive = QLabel(translate("当前无活跃子代理", language))
                inactive.setObjectName("muted")
                inactive.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tasks_layout.addWidget(inactive)
        self.tasks_layout.addStretch(1)

    def handle_settings_navigation(self) -> None:
        if self.stack.currentWidget() == self.status_page:
            self.show_settings()
        else:
            self.show_status()

    def _update_settings_navigation(self) -> None:
        in_settings = self.stack.currentWidget() != self.status_page
        self.settings_button.setText(translate("返回状态" if in_settings else "设置", self.settings["language"]))
        self.settings_button.setObjectName("primary" if in_settings else "ghost")
        self.settings_button.style().unpolish(self.settings_button)
        self.settings_button.style().polish(self.settings_button)

    def show_settings(self) -> None:
        current = self.stack.currentWidget()
        if hasattr(current, "can_close") and not current.can_close():
            return
        try:
            page = SettingsPage(self)
        except (OSError, ValueError) as error:
            prefix = "Settings failed to load: " if self.settings["language"] == "en" else "设置页加载失败："
            self.detail.setText(f"{prefix}{error}")
            return
        page.preferences_changed.connect(self.apply_settings)
        page.language_changed.connect(self.change_language)
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        self._update_settings_navigation()
        if current != self.status_page and current:
            self.stack.removeWidget(current)
            current.deleteLater()

    def show_status(self) -> None:
        current = self.stack.currentWidget()
        if hasattr(current, "can_close") and not current.can_close():
            return
        self.stack.setCurrentWidget(self.status_page)
        self._update_settings_navigation()
        if current != self.status_page and current:
            self.stack.removeWidget(current)
            current.deleteLater()

    def change_language(self, language: str) -> None:
        if language not in {"zh-CN", "en"}:
            return
        current = self.stack.currentWidget()
        if isinstance(current, SettingsPage) and current.saving:
            return
        previous = self.settings["language"]
        if language == previous:
            return
        self.settings["language"] = language
        if isinstance(current, SettingsPage):
            current.settings["language"] = language
        try:
            save_settings(self.settings)
        except OSError as error:
            self.settings["language"] = previous
            if isinstance(current, SettingsPage):
                current.settings["language"] = previous
                current.language_combo.blockSignals(True)
                current.language_combo.setCurrentIndex(0 if previous == "zh-CN" else 1)
                current.language_combo.blockSignals(False)
                prefix = "Save failed: " if previous == "en" else "保存失败："
                current.message.setText(f"{prefix}{error}")
            return
        retranslate_tree(self, language)
        self.setWindowTitle(translate("Kimi 多模型工程状态", language))
        if isinstance(current, SettingsPage):
            current.retranslate_dynamic()
        self._render()
        self.language_changed.emit(language)

    def apply_settings(self, settings: dict[str, Any]) -> None:
        was_visible = self.isVisible()
        self.settings = settings
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, settings["always_on_top"])
        self.setWindowOpacity(settings["opacity"])
        retranslate_tree(self, settings["language"])
        self._render()
        if was_visible:
            self.show()

    def handle_command(self, action: str) -> None:
        if action == "show":
            self.show_window()
        elif action == "hide":
            self.hide_window()
        elif action == "settings":
            self.show_window()
            self.show_settings()

    def show_window(self) -> None:
        self.show()
        self.setWindowState(Qt.WindowState.WindowNoState)
        self.raise_()
        self.activateWindow()

    def hide_window(self) -> None:
        self.save_position()
        self.hide()

    def save_position(self) -> None:
        if self.settings.get("position") != [self.x(), self.y()]:
            self.settings["position"] = [self.x(), self.y()]
            save_settings(self.settings)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 68:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_position = None
        super().mouseReleaseEvent(event)

    def hideEvent(self, event) -> None:
        self.save_position()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide_window()


def format_duration(seconds: int, compact: bool = False) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def elide(text: str, font, width: int) -> str:
    return QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, width)
