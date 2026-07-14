import sounddevice as sd
from PyQt6.QtMultimedia import QMediaDevices


def _shorten(name):
    for short in ("Headset", "Microphone Array", "Line In", "Microphone"):
        if short in name:
            return short
    return name

def list_input_devices():
    """Returns [(display_name, sounddevice_index), ...] for available mic devices."""
    seen = set()
    result = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            name = d["name"]
            if name not in seen:
                seen.add(name)
                display = _shorten(name)
                result.append((display, i))
    return result


def best_input_device():
    """Auto-detect the best physical mic. Returns sounddevice index or None."""
    candidates = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            lower = d["name"].lower()
            # Prioritise real mics over virtual mappers
            if any(k in lower for k in ("microphone", "headset", "mic")):
                if "mapper" not in lower and "stereo mix" not in lower:
                    candidates.append(i)
    if candidates:
        return candidates[0]
    # Fallback: any non-mapper input device
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and "mapper" not in d["name"].lower():
            return i
    return None


def resolve_input_device(name: str):
    """Returns a sounddevice device index for the given name, or best auto-detected device."""
    if not name:
        return best_input_device()
    for dname, idx in list_input_devices():
        if dname == name:
            return idx
    # Configured name not found — try matching the raw device name
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and d["name"] == name:
            return i
    # Still nothing — auto-detect a real mic
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
