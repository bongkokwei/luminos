"""
luminos_stage_gui.py  (v3)
--------------------------
PyQt5 GUI front-end for LuminosStage.

Layout
------
  ┌─ Connection bar ─────────────────────────────────────────────────┐
  │  Port ▾  ↺   Axis order: [JSON]   [Connect] [Disconnect]        │
  └──────────────────────────────────────────────────────────────────┘
  [⌂ Home All]  [⌂ Home Linear]  [⏹ Stop All]

  ┌─ Linear axes (µm) ──────────────────────────────────────────────┐
  │  X(µm)            Y(µm)            Z(µm)                        │
  └─────────────────────────────────────────────────────────────────┘
  ┌─ Rotational axes (°) ───────────────────────────────────────────┐
  │  ROLL(°)           PITCH(°)         YAW(°)                      │
  └─────────────────────────────────────────────────────────────────┘

  ┌─ Linear jog presets ────────────────────────────────────────────┐
  │  [1 nm] [10 nm] [100 nm] [1 µm] [10 µm] [100 µm] [1 mm]        │
  └─────────────────────────────────────────────────────────────────┘
  ┌─ Rotational jog presets ────────────────────────────────────────┐
  │  [0.001°] [0.01°] [0.1°] [1°]                                   │
  └─────────────────────────────────────────────────────────────────┘

The preset buttons write into whichever QDoubleSpinBox (jog or abs field)
last received keyboard focus.  A linear preset only targets linear-axis
spin boxes; a rotational preset only targets rotational-axis spin boxes.
"""

import sys
import json
import traceback

import serial.tools.list_ports

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QDoubleSpinBox,
    QStatusBar,
    QComboBox,
    QTabWidget,
    QMessageBox,
    QSizePolicy,
)
from PyQt5.QtGui import QFont

from .luminos_stage import LuminosStage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def list_com_ports() -> list[str]:
    return sorted(p.device for p in serial.tools.list_ports.comports())


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------


class StageWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.finished.emit(self._fn())
        except Exception:
            self.error.emit(traceback.format_exc())


# ---------------------------------------------------------------------------
# Focus tracker — app-level singleton
# ---------------------------------------------------------------------------


class FocusTracker:
    """
    Tracks the most recently focused QDoubleSpinBox.

    Register every spin box with  FocusTracker.instance().register(spinbox, is_linear).
    Call  FocusTracker.instance().set_value(v)  from a preset button to write
    into the last focused spin box of the matching axis type.
    """

    _inst = None

    @classmethod
    def instance(cls):
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    def __init__(self):
        self._last_linear: QDoubleSpinBox | None = None
        self._last_rotational: QDoubleSpinBox | None = None

    def register(self, spinbox: QDoubleSpinBox, is_linear: bool):
        """Connect focus-in event of spinbox to the tracker."""
        # We monkey-patch focusInEvent so we don't need eventFilter boilerplate.
        original = spinbox.focusInEvent

        def _focus_in(event, sb=spinbox, lin=is_linear, orig=original):
            orig(event)
            if lin:
                FocusTracker.instance()._last_linear = sb
            else:
                FocusTracker.instance()._last_rotational = sb

        spinbox.focusInEvent = _focus_in

    def set_linear_value(self, value_um: float):
        """Write value (in µm) into the last focused linear spin box."""
        sb = self._last_linear
        if sb is not None and sb.isEnabled():
            sb.setValue(value_um)

    def set_rotational_value(self, value_deg: float):
        """Write value (in °) into the last focused rotational spin box."""
        sb = self._last_rotational
        if sb is not None and sb.isEnabled():
            sb.setValue(value_deg)


# ---------------------------------------------------------------------------
# Axis widget
# ---------------------------------------------------------------------------

_LINEAR_AXES = {"x", "y", "z"}
_SPIN_W = 100  # px


class AxisWidget(QGroupBox):
    """Compact per-axis panel."""

    command_requested = pyqtSignal(object)

    def __init__(self, name: str, parent=None):
        is_linear = name in _LINEAR_AXES
        unit = "µm" if is_linear else "°"
        max_val = 13_000.0 if is_linear else 10.0
        step_val = 0.001 if is_linear else 0.0001
        dec_places = 3 if is_linear else 4

        super().__init__(f"{name.upper()} ({unit})", parent)
        self._is_linear = is_linear
        self._axis = None

        g = QGridLayout(self)
        g.setContentsMargins(6, 14, 6, 6)
        g.setHorizontalSpacing(4)
        g.setVerticalSpacing(3)
        g.setColumnStretch(1, 1)

        pos_font = QFont("Courier New", 10, QFont.Bold)

        # Row 0 — position + Home
        self._pos_label = QLabel("—")
        self._pos_label.setFont(pos_font)
        self._pos_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._pos_label.setMinimumWidth(_SPIN_W)
        self._home_btn = QPushButton("Home")
        self._home_btn.setFixedWidth(46)
        self._home_btn.clicked.connect(self._home)
        g.addWidget(QLabel("Pos:"), 0, 0)
        g.addWidget(self._pos_label, 0, 1)
        g.addWidget(QLabel(unit), 0, 2)
        g.addWidget(self._home_btn, 0, 3)

        # Row 1 — absolute move
        self._abs_spin = QDoubleSpinBox()
        self._abs_spin.setDecimals(dec_places)
        self._abs_spin.setRange(0.0, max_val)
        self._abs_spin.setSingleStep(step_val)
        self._abs_spin.setMinimumWidth(_SPIN_W)
        self._abs_btn = QPushButton("Go")
        self._abs_btn.setFixedWidth(46)
        self._abs_btn.clicked.connect(self._move_abs)
        g.addWidget(QLabel("Abs:"), 1, 0)
        g.addWidget(self._abs_spin, 1, 1)
        g.addWidget(QLabel(unit), 1, 2)
        g.addWidget(self._abs_btn, 1, 3)

        # Row 2 — relative jog
        self._rel_spin = QDoubleSpinBox()
        self._rel_spin.setDecimals(dec_places)
        self._rel_spin.setRange(0.0, max_val)
        self._rel_spin.setValue(1.0 if is_linear else 0.01)
        self._rel_spin.setSingleStep(step_val)
        self._rel_spin.setMinimumWidth(_SPIN_W)
        self._neg_btn = QPushButton("−")
        self._pos_btn = QPushButton("+")
        for b in (self._neg_btn, self._pos_btn):
            b.setFixedWidth(24)
        self._neg_btn.clicked.connect(lambda: self._move_rel(-1))
        self._pos_btn.clicked.connect(lambda: self._move_rel(+1))
        jog_btns = QHBoxLayout()
        jog_btns.setSpacing(2)
        jog_btns.addWidget(self._neg_btn)
        jog_btns.addWidget(self._pos_btn)
        g.addWidget(QLabel("Jog:"), 2, 0)
        g.addWidget(self._rel_spin, 2, 1)
        g.addWidget(QLabel(unit), 2, 2)
        g.addLayout(jog_btns, 2, 3)

        # Register both spin boxes with the focus tracker
        tracker = FocusTracker.instance()
        tracker.register(self._abs_spin, is_linear)
        tracker.register(self._rel_spin, is_linear)

        self._controls = [
            self._home_btn,
            self._abs_btn,
            self._neg_btn,
            self._pos_btn,
            self._abs_spin,
            self._rel_spin,
        ]
        self.set_enabled(False)

    # --- public ---

    def set_axis(self, axis_obj):
        self._axis = axis_obj
        self.set_enabled(axis_obj is not None)
        if axis_obj is None:
            self._pos_label.setText("—")

    def set_enabled(self, state: bool):
        for w in self._controls:
            w.setEnabled(state)

    def update_position(self):
        if self._axis is None:
            return
        try:
            if self._is_linear:
                self._pos_label.setText(f"{self._axis.get_position_um():>10.3f}")
            else:
                self._pos_label.setText(f"{self._axis.get_position_degree():>10.4f}")
        except Exception:
            self._pos_label.setText("ERR")

    # --- internal slots ---

    def _home(self):
        if self._axis:
            self.command_requested.emit(self._axis.home)

    def _move_abs(self):
        if not self._axis:
            return
        v = self._abs_spin.value()
        if self._is_linear:
            self.command_requested.emit(lambda v=v: self._axis.move_absolute_um(v))
        else:
            self.command_requested.emit(lambda v=v: self._axis.move_absolute_degree(v))

    def _move_rel(self, sign: int):
        if not self._axis:
            return
        d = sign * self._rel_spin.value()
        if self._is_linear:
            self.command_requested.emit(lambda d=d: self._axis.move_relative_um(d))
        else:
            self.command_requested.emit(lambda d=d: self._axis.move_relative_degree(d))


# ---------------------------------------------------------------------------
# Jog preset bar
# ---------------------------------------------------------------------------


def _make_preset_bar(is_linear: bool) -> QGroupBox:
    """
    Returns a QGroupBox containing preset buttons.

    Linear presets  : 1 nm, 10 nm, 100 nm, 1 µm, 10 µm, 100 µm, 1 mm
                      (all converted to µm before writing)
    Rotational presets: 0.001°, 0.01°, 0.1°, 1°
    """
    if is_linear:
        title = "Linear jog presets  →  click to fill focused jog / abs field"
        presets = [
            ("1 nm", 1e-3),
            ("10 nm", 1e-2),
            ("100 nm", 0.1),
            ("1 µm", 1.0),
            ("10 µm", 10.0),
            ("100 µm", 100.0),
            ("1 mm", 1_000.0),
        ]
    else:
        title = "Rotational jog presets  →  click to fill focused jog / abs field"
        presets = [
            ("0.001°", 0.001),
            ("0.01°", 0.01),
            ("0.1°", 0.1),
            ("1°", 1.0),
        ]

    box = QGroupBox(title)
    lay = QHBoxLayout(box)
    lay.setSpacing(4)
    lay.setContentsMargins(8, 10, 8, 6)

    tracker = FocusTracker.instance()

    for label, value in presets:
        btn = QPushButton(label)
        btn.setFixedHeight(26)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if is_linear:
            btn.clicked.connect(
                lambda checked=False, v=value: tracker.set_linear_value(v)
            )
        else:
            btn.clicked.connect(
                lambda checked=False, v=value: tracker.set_rotational_value(v)
            )
        lay.addWidget(btn)

    lay.addStretch()
    return box


# ---------------------------------------------------------------------------
# Stage panel  (one per tab)
# ---------------------------------------------------------------------------

_DEFAULT_ORDER_JSON = '{"x":0,"y":1,"roll":2,"yaw":3,"pitch":4}'


class StagePanel(QWidget):
    """Self-contained panel for one LuminosStage instance."""

    status_message = pyqtSignal(str)

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._stage: LuminosStage | None = None
        self._workers: list[StageWorker] = []
        self._label = label

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        # ── Connection bar ────────────────────────────────────────────────
        conn_box = QGroupBox("Connection")
        conn_lay = QHBoxLayout(conn_box)
        conn_lay.setSpacing(5)

        conn_lay.addWidget(QLabel("Port:"))
        self._port_combo = QComboBox()
        self._port_combo.setFixedWidth(90)
        self._port_combo.setEditable(True)
        conn_lay.addWidget(self._port_combo)

        self._refresh_btn = QPushButton("↺")
        self._refresh_btn.setFixedWidth(26)
        self._refresh_btn.setToolTip("Refresh COM ports")
        self._refresh_btn.clicked.connect(self._refresh_ports)
        conn_lay.addWidget(self._refresh_btn)

        conn_lay.addWidget(QLabel("Axis order:"))
        self._order_edit = QLineEdit(_DEFAULT_ORDER_JSON)
        self._order_edit.setFixedWidth(255)
        conn_lay.addWidget(self._order_edit)

        self._conn_btn = QPushButton("Connect")
        self._disconn_btn = QPushButton("Disconnect")
        self._disconn_btn.setEnabled(False)
        self._conn_btn.clicked.connect(self._on_connect)
        self._disconn_btn.clicked.connect(self._on_disconnect)
        conn_lay.addWidget(self._conn_btn)
        conn_lay.addWidget(self._disconn_btn)
        conn_lay.addStretch()
        root.addWidget(conn_box)

        # ── Action buttons ────────────────────────────────────────────────
        act_lay = QHBoxLayout()
        self._home_all_btn = QPushButton("⌂  Home All")
        self._home_lin_btn = QPushButton("⌂  Home Linear")
        self._stop_all_btn = QPushButton("⏹  Stop All")
        self._stop_all_btn.setStyleSheet(
            "background-color:#c0392b; color:white; font-weight:bold;"
        )
        for b in (self._home_all_btn, self._home_lin_btn, self._stop_all_btn):
            b.setFixedHeight(28)
            b.setEnabled(False)
            act_lay.addWidget(b)
        act_lay.addStretch()
        self._home_all_btn.clicked.connect(self._home_all)
        self._home_lin_btn.clicked.connect(self._home_linear)
        self._stop_all_btn.clicked.connect(self._stop_all)
        root.addLayout(act_lay)

        # ── Linear axes (stacked on top) ──────────────────────────────────
        lin_group = QGroupBox("Linear axes")
        lin_lay = QHBoxLayout(lin_group)
        lin_lay.setSpacing(4)

        self._axis_widgets: dict[str, AxisWidget] = {}

        for name in ("x", "y", "z"):
            aw = AxisWidget(name)
            aw.command_requested.connect(self._run_command)
            self._axis_widgets[name] = aw
            lin_lay.addWidget(aw)

        root.addWidget(lin_group)

        # ── Rotational axes (below) ───────────────────────────────────────
        rot_group = QGroupBox("Rotational axes")
        rot_lay = QHBoxLayout(rot_group)
        rot_lay.setSpacing(4)

        for name in ("roll", "pitch", "yaw"):
            aw = AxisWidget(name)
            aw.command_requested.connect(self._run_command)
            self._axis_widgets[name] = aw
            rot_lay.addWidget(aw)

        root.addWidget(rot_group)

        # ── Jog preset bars ───────────────────────────────────────────────
        root.addWidget(_make_preset_bar(is_linear=True))
        root.addWidget(_make_preset_bar(is_linear=False))

        # ── Polling timer ─────────────────────────────────────────────────
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._poll_positions)

        self._refresh_ports()

    # ── Port helpers ──────────────────────────────────────────────────────

    def _refresh_ports(self):
        current = self._port_combo.currentText()
        self._port_combo.clear()
        ports = list_com_ports()
        self._port_combo.addItems(ports if ports else ["(none)"])
        idx = self._port_combo.findText(current)
        if idx >= 0:
            self._port_combo.setCurrentIndex(idx)

    # ── Connection ────────────────────────────────────────────────────────

    def _on_connect(self):
        port = self._port_combo.currentText().strip()
        try:
            order = json.loads(self._order_edit.text())
        except json.JSONDecodeError as exc:
            QMessageBox.critical(self, "Bad JSON", str(exc))
            return
        self.status_message.emit(f"[{self._label}] Connecting to {port} …")

        def _connect():
            return LuminosStage(port, axis_order=order)

        w = StageWorker(_connect)
        w.finished.connect(self._on_stage_connected)
        w.error.connect(self._on_worker_error)
        self._keep(w)
        w.start()

    def _on_stage_connected(self, stage: LuminosStage):
        self._stage = stage
        self._set_connected_ui(True)
        for name, aw in self._axis_widgets.items():
            aw.set_axis(getattr(stage, name))
        self._poll_timer.start()
        self.status_message.emit(f"[{self._label}] Connected.")

    def _on_disconnect(self):
        self._poll_timer.stop()
        if self._stage is not None:
            try:
                self._stage.close()
            except Exception:
                pass
            self._stage = None
        self._set_connected_ui(False)
        for aw in self._axis_widgets.values():
            aw.set_axis(None)
        self.status_message.emit(f"[{self._label}] Disconnected.")

    def _set_connected_ui(self, state: bool):
        self._conn_btn.setEnabled(not state)
        self._disconn_btn.setEnabled(state)
        self._port_combo.setEnabled(not state)
        self._refresh_btn.setEnabled(not state)
        self._order_edit.setEnabled(not state)
        for b in (self._home_all_btn, self._home_lin_btn, self._stop_all_btn):
            b.setEnabled(state)

    # ── Commands ──────────────────────────────────────────────────────────

    def _run_command(self, fn):
        w = StageWorker(fn)
        w.finished.connect(lambda _: self.status_message.emit(f"[{self._label}] OK."))
        w.error.connect(self._on_worker_error)
        self._keep(w)
        w.start()

    def _home_all(self):
        if self._stage:
            self.status_message.emit(f"[{self._label}] Homing all …")
            self._run_command(self._stage.home_all)

    def _home_linear(self):
        if self._stage:
            self.status_message.emit(f"[{self._label}] Homing linear …")
            self._run_command(self._stage.home_linear)

    def _stop_all(self):
        if self._stage is None:
            return
        try:
            self._stage.stop_all()
            self.status_message.emit(f"[{self._label}] Stopped.")
        except Exception as exc:
            self.status_message.emit(f"[{self._label}] Stop error: {exc}")

    # ── Polling ───────────────────────────────────────────────────────────

    def _poll_positions(self):
        for aw in self._axis_widgets.values():
            aw.update_position()

    # ── Worker bookkeeping ────────────────────────────────────────────────

    def _keep(self, w: StageWorker):
        self._workers.append(w)
        w.finished.connect(lambda _: self._purge())
        w.error.connect(lambda _: self._purge())

    def _purge(self):
        self._workers = [w for w in self._workers if w.isRunning()]

    def _on_worker_error(self, tb: str):
        last = tb.strip().splitlines()[-1]
        self.status_message.emit(f"[{self._label}] Error: {last}")
        print(f"=== [{self._label}] worker error ===\n{tb}")

    def close_stage(self):
        self._on_disconnect()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Luminos Stage Controller")
        self.resize(1050, 620)
        self.setMaximumHeight(200)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready.")

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(4)

        # ── Tab controls ──────────────────────────────────────────────────
        tab_ctrl = QHBoxLayout()
        self._add_btn = QPushButton("＋  Add Stage")
        self._add_btn.setFixedHeight(26)
        self._add_btn.clicked.connect(self._add_stage)
        self._rem_btn = QPushButton("−  Remove Stage")
        self._rem_btn.setFixedHeight(26)
        self._rem_btn.setEnabled(False)
        self._rem_btn.clicked.connect(self._remove_current_stage)
        tab_ctrl.addWidget(self._add_btn)
        tab_ctrl.addWidget(self._rem_btn)
        tab_ctrl.addStretch()
        root.addLayout(tab_ctrl)

        # ── Tabs ──────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        root.addWidget(self._tabs)

        self._stage_count = 0
        self._add_stage()

    def _add_stage(self):
        self._stage_count += 1
        label = f"Stage {self._stage_count}"
        panel = StagePanel(label)
        panel.status_message.connect(self._status.showMessage)
        self._tabs.addTab(panel, label)
        self._tabs.setCurrentWidget(panel)
        self._rem_btn.setEnabled(self._tabs.count() > 1)

    def _remove_current_stage(self):
        if self._tabs.count() <= 1:
            return
        idx = self._tabs.currentIndex()
        panel = self._tabs.widget(idx)
        panel.close_stage()
        self._tabs.removeTab(idx)
        self._rem_btn.setEnabled(self._tabs.count() > 1)

    def closeEvent(self, event):
        for i in range(self._tabs.count()):
            self._tabs.widget(i).close_stage()
        event.accept()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
