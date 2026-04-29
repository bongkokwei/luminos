"""
Luminos stage control built on top of zaber_motion.binary.

All six axes (x, y, z, roll, pitch, yaw) use the same linear actuator:
    - Step size : 99.21875 nm/step
    - Max steps : 131,072 steps
    - Max travel: 131,072 × 99.21875 nm ≈ 13.0 mm

Axis type (linear vs rotational) is determined by axis name:
    Linear     (µm API) — x, y, z
    Rotational (deg API) — roll, pitch, yaw
        Roll/pitch/yaw are linear actuators mechanically coupled to produce
        rotation. The degree values are a soft abstraction; the underlying
        motion is always in native steps. The arc_sec_per_step factor is an
        empirical calibration and does not need to be physically accurate for
        photonic chip coupling alignment.

Default device chain order (0-indexed, closest to PC = index 0):
    z     -> 0
    x     -> 1
    y     -> 2
    roll  -> 3
    pitch -> 4
    yaw   -> 5

The axis order is fully configurable via ``axis_order``, and any subset of
axes may be used. For example, a 5-axis stage with no Z:

    axis_order={'x': 0, 'y': 1, 'roll': 2, 'pitch': 3, 'yaw': 4}

Linear axes: positions exposed in micrometres.
Rotational axes: positions exposed in degrees (soft abstraction over µm).
"""

from zaber_motion import Library, Units
from zaber_motion.binary import BinarySettings, Connection


# ---------------------------------------------------------------------------
# Physical constants — all axes share the same linear actuator
# ---------------------------------------------------------------------------

_NM_PER_STEP = 99.21875  # nm per native step (all axes)
_MAX_STEPS = 131_072  # maximum native steps (all axes)
_MAX_NM = _MAX_STEPS * _NM_PER_STEP  # ~13.0 mm in nm

# Empirical rotational calibration (linear steps -> effective angle).
# These do not need to be physically accurate for alignment purposes.
_AS_PER_STEP_ROLL = 0.1  # arc-sec per step for roll
_AS_PER_STEP_PY = 0.2  # arc-sec per step for pitch and yaw
_MAX_AS_ROLL = _MAX_STEPS * _AS_PER_STEP_ROLL  # 13,107.2 arc-sec (~3.64 deg)
_MAX_AS_PY = _MAX_STEPS * _AS_PER_STEP_PY  # 26,214.4 arc-sec (~7.28 deg)

# Default motion parameters (empirically chosen, from original implementation)
# All axes share the same actuator so a single speed applies.
_DEFAULT_SPEED = 600
_DEFAULT_ACCEL = 22
_DEFAULT_MICROSTEPS = 128

# Axis classification by name — determines which wrapper class is used
_LINEAR_AXES = {"x", "y", "z"}
_ROTATIONAL_AXES = {"roll", "pitch", "yaw"}
_ALL_AXIS_NAMES = _LINEAR_AXES | _ROTATIONAL_AXES

# Default daisy-chain order (0-indexed, closest to PC = 0)
_DEFAULT_AXIS_ORDER = {"z": 0, "x": 1, "y": 2, "roll": 3, "pitch": 4, "yaw": 5}


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------


def open_connection(port: str) -> Connection:
    """Open a binary serial connection and return it.

    Prefer using LuminosStage as a context manager instead:

        with LuminosStage("COM8") as stage:
            stage.home_all()
            stage.x.move_absolute_um(100.0)
    """
    Library.enable_device_db_store()
    return Connection.open_serial_port(port)


# ---------------------------------------------------------------------------
# Individual axis wrappers
# ---------------------------------------------------------------------------


class _LinearAxis:
    """Wraps a zaber_motion binary Device for a linear translation axis."""

    def __init__(
        self, device, nm_per_step: float, max_nm: float, reverse: bool = False
    ):
        self._dev = device
        self._nm_per_step = nm_per_step
        self._max_nm = max_nm
        self._reverse = reverse

    def _apply_reverse_nm(self, nm: float) -> float:
        return self._max_nm - nm if self._reverse else nm

    def home(self):
        self._dev.home()

    def move_absolute_nm(self, nm: float):
        nm = float(nm)
        assert 0 <= nm <= self._max_nm, f"Position {nm:.0f} nm out of range."
        self._dev.move_absolute(
            self._apply_reverse_nm(nm) / 1e6, Units.LENGTH_MILLIMETRES
        )

    def move_absolute_um(self, um: float):
        self.move_absolute_nm(um * 1e3)

    def move_absolute_mm(self, mm: float):
        self.move_absolute_nm(mm * 1e6)

    def move_relative_nm(self, delta_nm: float):
        delta = -delta_nm if self._reverse else delta_nm
        self._dev.move_relative(delta / 1e6, Units.LENGTH_MILLIMETRES)

    def move_relative_um(self, delta_um: float):
        self.move_relative_nm(delta_um * 1e3)

    def move_relative_mm(self, delta_mm: float):
        self.move_relative_nm(delta_mm * 1e6)

    def get_position_nm(self) -> float:
        hw_nm = self._dev.get_position(Units.LENGTH_MILLIMETRES) * 1e6
        return self._apply_reverse_nm(hw_nm)

    def get_position_um(self) -> float:
        return self.get_position_nm() / 1e3

    def get_position_mm(self) -> float:
        return self.get_position_nm() / 1e6

    def stop(self):
        self._dev.stop()

    def is_busy(self) -> bool:
        return self._dev.is_busy()

    def set_speed(self, speed: int) -> int:
        return self._dev.settings.set(BinarySettings.TARGET_SPEED, speed)

    def set_acceleration(self, accel: int) -> int:
        return self._dev.settings.set(BinarySettings.ACCELERATION, accel)

    def set_microstep_resolution(self, microsteps: int) -> int:
        assert microsteps in (1, 2, 4, 8, 16, 32, 64, 128)
        return self._dev.settings.set(BinarySettings.MICROSTEP_RESOLUTION, microsteps)


class _RotationalAxis:
    """Wraps a zaber_motion binary Device for a rotational axis.

    The underlying motor is a linear actuator mechanically coupled to produce
    rotation. All motion is performed in raw steps (Units.NATIVE) and converted
    to/from arc-seconds using the empirical arc_sec_per_step calibration factor.
    """

    def __init__(
        self, device, arc_sec_per_step: float, max_arc_sec: float, reverse: bool = False
    ):
        self._dev = device
        self._arc_sec_per_step = arc_sec_per_step
        self._max_arc_sec = max_arc_sec
        self._reverse = reverse

    def _as_to_steps(self, arc_sec: float) -> int:
        return int(round(arc_sec / self._arc_sec_per_step))

    def _steps_to_as(self, steps: int) -> float:
        return steps * self._arc_sec_per_step

    def _apply_reverse_as(self, arc_sec: float) -> float:
        return self._max_arc_sec - arc_sec if self._reverse else arc_sec

    def home(self):
        self._dev.home()

    def move_absolute_arc_second(self, arc_sec: float):
        arc_sec = float(arc_sec)
        assert (
            0 <= arc_sec <= self._max_arc_sec
        ), f"Position {arc_sec:.2f} arc-sec out of range."
        steps = self._as_to_steps(self._apply_reverse_as(arc_sec))
        self._dev.move_absolute(steps, Units.NATIVE)

    def move_absolute_degree(self, deg: float):
        self.move_absolute_arc_second(deg * 3600.0)

    def move_relative_arc_second(self, delta_as: float):
        delta = -delta_as if self._reverse else delta_as
        self._dev.move_relative(self._as_to_steps(delta), Units.NATIVE)

    def move_relative_degree(self, delta_deg: float):
        self.move_relative_arc_second(delta_deg * 3600.0)

    def get_position_arc_second(self) -> float:
        steps = self._dev.get_position(Units.NATIVE)
        return self._apply_reverse_as(self._steps_to_as(steps))

    def get_position_degree(self) -> float:
        return self.get_position_arc_second() / 3600.0

    def stop(self):
        self._dev.stop()

    def is_busy(self) -> bool:
        return self._dev.is_busy()

    def set_speed(self, speed: int) -> int:
        return self._dev.settings.set(BinarySettings.TARGET_SPEED, speed)

    def set_acceleration(self, accel: int) -> int:
        return self._dev.settings.set(BinarySettings.ACCELERATION, accel)

    def set_microstep_resolution(self, microsteps: int) -> int:
        assert microsteps in (1, 2, 4, 8, 16, 32, 64, 128)
        return self._dev.settings.set(BinarySettings.MICROSTEP_RESOLUTION, microsteps)


# ---------------------------------------------------------------------------
# Main stage class
# ---------------------------------------------------------------------------


class LuminosStage:
    """Controls a Luminos stage (any subset of 6 axes) via zaber_motion.binary.

    Axis type is determined purely by name — independently of what other axes
    are present:
        Linear     — x, y, z
        Rotational — roll, pitch, yaw

    Parameters
    ----------
    port : str
        Serial port string, e.g. "COM8" or "/dev/ttyUSB0".
    reverse_x, reverse_y, reverse_z : bool
        Reverse the respective linear axis direction.
    axis_order : dict, optional
        Maps axis name -> 0-indexed position in the daisy chain
        (closest device to PC = index 0).
        Any subset of {'x', 'y', 'z', 'roll', 'pitch', 'yaw'} is accepted.

        Defaults to:
            {'z': 0, 'x': 1, 'y': 2, 'roll': 3, 'pitch': 4, 'yaw': 5}

        Examples::

            # 5-axis stage, no Z, wired X->Y->Roll->Pitch->Yaw
            axis_order={'x': 0, 'y': 1, 'roll': 2, 'pitch': 3, 'yaw': 4}

            # XYZ only
            axis_order={'x': 0, 'y': 1, 'z': 2}

    Examples
    --------
    Full 6-axis stage (default wiring)::

        with LuminosStage("COM8") as stage:
            stage.home_all()
            stage.x.move_absolute_um(100.0)

    5-axis stage, no Z::

        with LuminosStage("COM8",
                          axis_order={'x': 0, 'y': 1,
                                      'roll': 2, 'pitch': 3, 'yaw': 4}) as stage:
            stage.home_all()
            print(stage.z)     # None
            print(stage.roll)  # <_RotationalAxis>
    """

    def __init__(
        self,
        port: str,
        reverse_x: bool = False,
        reverse_y: bool = False,
        reverse_z: bool = False,
        axis_order: dict = None,
    ):

        idx = axis_order if axis_order is not None else _DEFAULT_AXIS_ORDER

        unknown = set(idx.keys()) - _ALL_AXIS_NAMES
        assert (
            not unknown
        ), f"Unknown axis name(s): {unknown}. Valid names: {_ALL_AXIS_NAMES}"

        self._connection = open_connection(port)
        devices = self._connection.detect_devices()
        assert len(devices) >= len(idx), (
            f"axis_order needs {len(idx)} devices but only "
            f"{len(devices)} detected on {port}."
        )

        d = {name: devices[i] for name, i in idx.items()}

        # Apply motion settings — all axes share the same actuator
        for dev in d.values():
            self._configure_device(
                dev, _DEFAULT_SPEED, _DEFAULT_ACCEL, _DEFAULT_MICROSTEPS
            )

        # Build axis objects.
        # Type is determined by name alone — not by what other axes are present.
        # All axes share the same physical actuator constants.
        reverses = {"x": reverse_x, "y": reverse_y, "z": reverse_z}

        def _make_axis(name):
            if name not in d:
                return None
            dev = d[name]
            if name in _LINEAR_AXES:
                return _LinearAxis(
                    dev, _NM_PER_STEP, _MAX_NM, reverse=reverses.get(name, False)
                )
            else:  # rotational — linear actuator with soft degree abstraction
                if name == "roll":
                    return _RotationalAxis(dev, _AS_PER_STEP_ROLL, _MAX_AS_ROLL)
                else:
                    return _RotationalAxis(dev, _AS_PER_STEP_PY, _MAX_AS_PY)

        self.x = _make_axis("x")
        self.y = _make_axis("y")
        self.z = _make_axis("z")
        self.roll = _make_axis("roll")
        self.pitch = _make_axis("pitch")
        self.yaw = _make_axis("yaw")

        self._all_axes = [
            a
            for a in [self.x, self.y, self.z, self.roll, self.pitch, self.yaw]
            if a is not None
        ]

    @staticmethod
    def _configure_device(device, speed: int, accel: int, microsteps: int):
        """Apply motion settings to a raw zaber_motion Device."""
        try:
            device.settings.set(BinarySettings.TARGET_SPEED, speed)
            device.settings.set(BinarySettings.ACCELERATION, accel)
            device.settings.set(BinarySettings.MICROSTEP_RESOLUTION, microsteps)
        except Exception as e:
            print(
                f"Warning: could not configure device " f"{device.device_address}: {e}"
            )

    def home_all(self):
        """Home all present axes sequentially."""
        for axis in self._all_axes:
            axis.home()

    def home_linear(self):
        """Home only the linear axes (x, y, z) that are present."""
        for axis in [self.x, self.y, self.z]:
            if axis is not None:
                axis.home()

    def get_position_um(self) -> dict:
        """Return positions of all present linear axes in micrometres."""
        return {
            name: getattr(self, name).get_position_um()
            for name in ("x", "y", "z")
            if getattr(self, name) is not None
        }

    def get_position_deg(self) -> dict:
        """Return positions of all present rotational axes in degrees."""
        return {
            name: getattr(self, name).get_position_degree()
            for name in ("roll", "pitch", "yaw")
            if getattr(self, name) is not None
        }

    def stop_all(self):
        """Stop all present axes immediately."""
        for axis in self._all_axes:
            axis.stop()

    def close(self):
        """Close the serial connection."""
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


# ---------------------------------------------------------------------------
# Quick usage example
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    # 5-axis stage — no Z, wired X->Y->Roll->Pitch->Yaw
    with LuminosStage(
        "COM9", axis_order={"x": 0, "y": 1, "roll": 2, "pitch": 3, "yaw": 4}
    ) as stage:
        # stage.home_all()
        print("z axis:", stage.z)  # None
        print("Linear (um):", stage.get_position_um())  # x, y only
        print("Rotational (deg):", stage.get_position_deg())  # roll, pitch, yaw

        # stage.y.move_absolute_um(100)
        stage.roll.move_absolute_degree(1.5)
        print("New linear (um):", stage.get_position_um())
        print("New rotational (deg):", stage.get_position_deg())
