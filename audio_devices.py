import sounddevice as sd
from PyQt6.QtMultimedia import QMediaDevices

_JUNK = {"microsoft sound mapper", "primary sound capture driver", "stereo mix"}


def _shorten(name):
    for short in ("Headset", "Microphone Array", "Line In", "Microphone"):
        if short in name:
            return short
    return name


def _is_junk(name):
    lower = name.lower().strip()
    if not lower or "input ()" in lower:
        return True
    return any(junk in lower for junk in _JUNK)


def list_input_devices():
    """Returns [(display_name, sounddevice_index), ...] for real mic devices.
    Filters out virtual drivers, duplicates, and junk entries."""
    seen_display = set()
    result = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] <= 0:
            continue
        if _is_junk(d["name"]):
            continue
        display = _shorten(d["name"])
        if display in seen_display:
            continue
        seen_display.add(display)
        result.append((display, i))
    return result


def best_input_device():
    """Fast heuristic: first device that looks like a real mic. No probing."""
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] <= 0 or _is_junk(d["name"]):
            continue
        lower = d["name"].lower()
        if any(k in lower for k in ("microphone", "headset", "mic")):
            if "stereo mix" not in lower:
                return i
    # Fallback: first non-junk input device
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and not _is_junk(d["name"]):
            return i
    return None


def resolve_input_device(name: str):
    """Returns a sounddevice device index for the given name, or auto-detected device."""
    if not name:
        return best_input_device()
    # Try exact shortened name match (what the settings dropdown saves)
    for dname, idx in list_input_devices():
        if dname == name:
            return idx
    # Try matching the raw device name
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and d["name"] == name:
            return i
    # Not found — auto-detect
    return best_input_device()


def list_output_devices():
    """Returns [(description, QAudioDevice), ...] for available speaker devices."""
    return [(d.description(), d) for d in QMediaDevices.audioOutputs()]


def resolve_output_device(name: str):
    """Returns a QAudioDevice for the given description, or None (system default)."""
    if not name:
        return None
    for desc, dev in list_output_devices():
        if desc == name:
            return dev
    return None


def apply_output_device(audio_output, config):
    """Points a QAudioOutput at the configured speaker, if one is set."""
    device = resolve_output_device(config.get("speaker_device"))
    if device is not None:
        audio_output.setDevice(device)
