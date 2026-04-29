# Luminos Stage Python Interface

A Python interface for controlling Luminos motorised 6-axis positioning stages via Zaber motion control. This library provides intuitive programmatic access and a professional GUI for controlling linear (X, Y, Z) and rotational (Roll, Pitch, Yaw) axes.

## Overview

The Luminos stage is a precision motorised positioning platform with up to 6 degrees of freedom. All axes use identical linear actuators with different mechanical interpretations:

- **Linear axes** (X, Y, Z): Direct linear displacement in micrometres
- **Rotational axes** (Roll, Pitch, Yaw): Mechanically coupled rotation, exposed as degrees

This Python package provides:

- **Type-annotated classes** for linear and rotational axes
- **Flexible axis configuration** for any subset of the 6 axes
- **Real-time position monitoring** with PyQt5 GUI
- **Comprehensive logging** throughout for debugging
- **Context manager support** for clean resource management
- **Thread-safe operations** via worker threads

## Features

- TCP/IP control via Zaber motion library
- Support for 3 to 6 axes with customisable ordering
- Separate position APIs for linear (µm) and rotational (°) axes
- Absolute and relative motion commands
- Homing functionality for reference positioning
- Speed and acceleration configuration
- Microstep resolution control
- Real-time position monitoring with scrolling display
- Preset buttons for common jog distances
- Multi-stage support (multiple independent controllers)
- Comprehensive Python logging

## Installation

### Requirements

- Python 3.7+
- zaber-motion ≥ 5.0.0
- (Optional) PyQt5 ≥ 5.15.0 and NumPy ≥ 1.20.0 for GUI

### Install Dependencies

```bash
pip install zaber-motion
```

For GUI support:

```bash
pip install PyQt5 numpy
```

### Import the Classes

```python
from luminos_stage import LuminosStage
```

## Quick Start

### Basic Usage (6-axis stage)

```python
from luminos_stage import LuminosStage
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Open connection (uses default axis order)
with LuminosStage(port='COM8') as stage:
    # Home all axes
    stage.home_all()

    # Move X axis to 100 µm
    stage.x.move_absolute_um(100.0)

    # Move Y axis relative
    stage.y.move_relative_um(50.0)

    # Rotate roll axis to 5°
    stage.roll.move_absolute_degree(5.0)

    # Get current positions
    linear_pos = stage.get_position_um()
    rotational_pos = stage.get_position_deg()
    print(f"Linear: {linear_pos}")
    print(f"Rotational: {rotational_pos}")
```

### Custom Axis Configuration (5-axis stage, no Z)

```python
with LuminosStage(
    port='COM8',
    axis_order={'x': 0, 'y': 1, 'roll': 2, 'pitch': 3, 'yaw': 4}
) as stage:
    print(f"Z axis: {stage.z}")  # None
    print(f"Roll axis: {stage.roll}")  # <_RotationalAxis>
```

### Running the GUI

```bash
python src/luminos/gui.py
```

Alternatively from Python:

```python
from luminos_gui import main
main()
```

## API Reference

### LuminosStage Class

#### Initialisation

```python
LuminosStage(
    port,
    reverse_x=False,
    reverse_y=False,
    reverse_z=False,
    axis_order=None
)
```

**Parameters:**

- `port` (str): Serial port name (e.g. `'COM8'`, `'/dev/ttyUSB0'`)
- `reverse_x, reverse_y, reverse_z` (bool): Reverse direction for linear axes
- `axis_order` (dict, optional): Custom axis ordering

  Default: `{'z': 0, 'x': 1, 'y': 2, 'roll': 3, 'pitch': 4, 'yaw': 5}`

**Example:**

```python
stage = LuminosStage(port='COM8', reverse_y=True)
```

---

### Connection Management

#### `close()`

Close the serial connection.

```python
stage.close()
```

#### Context Manager

Preferred method for automatic connection cleanup:

```python
with LuminosStage(port='COM8') as stage:
    # Use stage
    pass  # Connection automatically closed
```

---

### Global Stage Operations

#### `home_all()`

Home all axes sequentially to reference position.

```python
stage.home_all()
```

#### `home_linear()`

Home only linear axes (X, Y, Z) that are present.

```python
stage.home_linear()
```

#### `stop_all()`

Emergency stop all axes immediately.

```python
stage.stop_all()
```

#### `get_position_um() -> Dict[str, float]`

Get positions of all linear axes in micrometres.

**Returns:** Dictionary with axis names as keys

**Example:**

```python
pos = stage.get_position_um()
print(f"X: {pos['x']:.3f} µm")
print(f"Y: {pos['y']:.3f} µm")
```

#### `get_position_deg() -> Dict[str, float]`

Get positions of all rotational axes in degrees.

**Example:**

```python
pos = stage.get_position_deg()
print(f"Roll: {pos['roll']:.4f}°")
```

---

### Linear Axis Operations

Each linear axis (X, Y, Z) provides these methods:

#### Movement Commands

```python
stage.x.move_absolute_um(100.0)      # Move to 100 µm
stage.x.move_absolute_mm(1.5)        # Move to 1.5 mm
stage.x.move_relative_um(50.0)       # Move 50 µm forward
stage.x.move_relative_um(-10.0)      # Move 10 µm backward
```

#### Position Queries

```python
pos_um = stage.x.get_position_um()   # Position in micrometres
pos_mm = stage.x.get_position_mm()   # Position in millimetres
```

#### Axis Control

```python
stage.x.home()                        # Home to reference
stage.x.stop()                        # Emergency stop
busy = stage.x.is_busy()             # Check if moving
```

#### Motion Configuration

```python
stage.x.set_speed(800)               # Set velocity
stage.x.set_acceleration(30)         # Set acceleration
stage.x.set_microstep_resolution(64) # 1, 2, 4, 8, 16, 32, 64, 128
```

---

### Rotational Axis Operations

Each rotational axis (Roll, Pitch, Yaw) provides:

#### Movement Commands

```python
stage.roll.move_absolute_degree(5.0)      # Move to 5°
stage.roll.move_relative_degree(1.0)      # Rotate 1° forward
stage.roll.move_relative_degree(-0.5)     # Rotate 0.5° backward
```

#### Position Queries

```python
pos_deg = stage.roll.get_position_degree()  # Position in degrees
```

#### Axis Control

```python
stage.roll.home()                    # Home to reference
stage.roll.stop()                    # Emergency stop
busy = stage.roll.is_busy()         # Check if moving
```

#### Motion Configuration

```python
stage.roll.set_speed(600)            # Set velocity
stage.roll.set_acceleration(22)      # Set acceleration
```

---

## Physical Specifications

### Hardware Constants

All axes use the same linear actuator:

| Parameter | Value |
|-----------|-------|
| Step size | 99.21875 nm/step |
| Max steps | 131,072 steps |
| Max travel | ~13.0 mm |

### Default Motion Parameters

| Parameter | Value |
|-----------|-------|
| Speed | 600 |
| Acceleration | 22 |
| Microsteps | 128 |

### Rotational Calibration

| Axis | Arc-sec/step | Max range |
|------|--------------|-----------|
| Roll | 0.1 | ~3.64° |
| Pitch/Yaw | 0.2 | ~7.28° |

---

## Complete Example

```python
from luminos_stage import LuminosStage
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def alignment_sequence(port='COM8'):
    """
    Perform automated alignment sequence on 6-axis stage.
    """
    with LuminosStage(port=port) as stage:
        logger.info("Starting alignment sequence")

        # Home all axes
        logger.info("Homing all axes...")
        stage.home_all()

        # Move to alignment position
        logger.info("Moving to alignment position...")
        stage.x.move_absolute_um(500.0)
        stage.y.move_absolute_um(500.0)
        stage.z.move_absolute_um(250.0)

        # Fine adjustments
        logger.info("Fine tuning position...")
        stage.roll.move_absolute_degree(0.5)
        stage.pitch.move_absolute_degree(1.0)

        # Report final positions
        linear_pos = stage.get_position_um()
        rotational_pos = stage.get_position_deg()

        logger.info(f"Final linear positions (µm): {linear_pos}")
        logger.info(f"Final rotational positions (°): {rotational_pos}")

        logger.info("Alignment complete")

if __name__ == '__main__':
    alignment_sequence()
```

## GUI Application

The included PyQt5 GUI provides:

- **Multi-stage support**: Control multiple stages in separate tabs
- **Real-time monitoring**: Position display updates every 500 ms
- **Intuitive controls**: Home, absolute move, and relative jog buttons
- **Preset buttons**: Quick access to common jog distances
  - Linear: 1 nm, 10 nm, 100 nm, 1 µm, 10 µm, 100 µm, 1 mm
  - Rotational: 0.001°, 0.01°, 0.1°, 1.0°
- **Flexible configuration**: Custom axis ordering via JSON
- **Focus-aware presets**: Presets fill whichever spinbox last received focus
- **Emergency stop**: Red stop button for all axes

### Running the GUI

```bash
python -m luminos_stage.gui
```

---

## Troubleshooting

### Connection Issues

**Problem:** `RuntimeError: Failed to open serial connection`

**Solutions:**
- Verify correct serial port (use Device Manager on Windows)
- Ensure Zaber devices are powered on
- Check USB cable connections
- Verify no other application is using the port

### Axis Not Moving

**Problem:** No motion after move command

**Solutions:**
- Verify axis is not already at target position
- Check axis is not busy: `stage.x.is_busy()`
- Try homing axis: `stage.x.home()`
- Check speed/acceleration settings
- Verify axis power supply

### Position Not Updating

**Problem:** `get_position_um()` returns stale values

**Solutions:**
- Ensure axis has finished moving: `stage.x.is_busy()`
- Try calling position multiple times
- Check serial communication (logging at DEBUG level)

---

## Logging

Configure Python logging to see detailed information:

```python
import logging

# Show all debug messages
logging.basicConfig(level=logging.DEBUG)

# Or configure just this package
logger = logging.getLogger('luminos_stage')
logger.setLevel(logging.DEBUG)
```

Log levels:
- `DEBUG`: Detailed hardware commands and responses
- `INFO`: Connection status, major operations
- `WARNING`: Unexpected conditions
- `ERROR`: Operation failures

---

## Axis Ordering

The default axis ordering assumes:

```
Port 0 (closest to PC)  →  Z axis
Port 1                   →  X axis
Port 2                   →  Y axis
Port 3                   →  Roll axis
Port 4                   →  Pitch axis
Port 5                   →  Yaw axis
```

Customise with `axis_order` parameter:

```python
# 5-axis: X->Y->Roll->Pitch->Yaw (no Z)
LuminosStage(port='COM8', axis_order={
    'x': 0, 'y': 1, 'roll': 2, 'pitch': 3, 'yaw': 4
})

# 3-axis XYZ only
LuminosStage(port='COM8', axis_order={
    'x': 0, 'y': 1, 'z': 2
})
```

---

## Performance Notes

- Typical position query response: ~50 ms
- Homing duration: Variable, depends on current position
- GUI update rate: 500 ms (user configurable)
- Thread-safe: All hardware operations run in worker threads

---

## License

MIT License. See LICENSE file for details.

## References

- Zaber Motion library: https://github.com/zabertech/zaber-python-api
- PyQt5 documentation: https://www.riverbankcomputing.com/software/pyqt/

## Support

For issues with this Python implementation:
1. Enable logging: `logging.basicConfig(level=logging.DEBUG)`
2. Check serial port configuration
3. Verify Zaber devices are detected: Check Device Manager or `/dev/ttyUSB*`
4. Review error messages in console output

For device-specific issues, consult Zaber documentation or contact support.

---

**Note:** This implementation requires proper mechanical assembly and calibration of the Luminos stage before use.
