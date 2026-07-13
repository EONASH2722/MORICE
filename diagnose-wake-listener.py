"""
Comprehensive diagnostic tool for the MORICE wake listener.
Run this to identify issues with voice recognition, audio devices, and Vosk models.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VOICE_MODELS = ROOT / "voice_models"
LOG_PATH = ROOT / "morice_wake_listener.log"


def header(text: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def success(text: str) -> None:
    print(f"✓ {text}")


def error(text: str) -> None:
    print(f"✗ {text}")


def info(text: str) -> None:
    print(f"ℹ {text}")


def check_vosk_installed() -> bool:
    """Check if Vosk library is installed."""
    header("1. CHECKING VOSK LIBRARY")
    try:
        from vosk import KaldiRecognizer, Model, SetLogLevel
        success("Vosk library is installed")
        return True
    except ImportError as e:
        error(f"Vosk not installed: {e}")
        print("\nFIX: Install Vosk with:")
        print("  pip install vosk\n")
        return False


def check_sounddevice_installed() -> bool:
    """Check if sounddevice library is installed."""
    header("2. CHECKING SOUNDDEVICE LIBRARY")
    try:
        import sounddevice as sd
        success("sounddevice library is installed")
        return True
    except ImportError as e:
        error(f"sounddevice not installed: {e}")
        print("\nFIX: Install sounddevice with:")
        print("  pip install sounddevice\n")
        return False


def list_audio_devices() -> bool:
    """List all audio input devices."""
    header("3. LISTING AUDIO DEVICES")
    try:
        import sounddevice as sd
        print(sd.query_devices())
        print("\nNOTE: Find your microphone in the list above.")
        print("If you need to force a specific device, set:")
        print("  set MORICE_AUDIO_DEVICE=<device_index_or_name>\n")
        return True
    except Exception as e:
        error(f"Failed to list audio devices: {e}")
        return False


def find_vosk_model_path() -> Path | None:
    """Find existing Vosk model."""
    header("4. SEARCHING FOR VOSK MODELS")
    VOICE_MODELS.mkdir(exist_ok=True)
    candidates: list[Path] = []
    for base in (VOICE_MODELS, ROOT):
        for folder in base.glob("vosk-model*"):
            if folder.is_dir() and (folder / "conf").exists():
                candidates.append(folder)
    
    if candidates:
        best = sorted(candidates, key=lambda p: (0 if "small" in p.name.lower() else 1, p.name.lower()))[0]
        success(f"Found Vosk model: {best}")
        return best
    
    error("No Vosk model found")
    print("\nFIX: Download a model and extract it to the MORICE root:")
    print("  • Small (40MB): https://alphacephei.com/vosk/models")
    print("  • Large (1.4GB): https://alphacephei.com/vosk/models")
    print("\nAfter downloading, extract so you have:")
    print("  MORICE/vosk-model-en-us-0.22/conf/\n")
    return None


def check_vosk_model_usable(model_path: Path) -> bool:
    """Verify Vosk model is usable."""
    header("5. TESTING VOSK MODEL")
    try:
        from vosk import Model, SetLogLevel
        if SetLogLevel:
            SetLogLevel(-1)
        Model(str(model_path))
        success(f"Vosk model loads successfully: {model_path.name}")
        return True
    except Exception as e:
        error(f"Vosk model failed to load: {e}")
        return False


def check_settings() -> dict:
    """Load and display current settings."""
    header("6. CHECKING WAKE LISTENER SETTINGS")
    try:
        from morice.settings import load_settings, settings_path
        settings = load_settings()
        path = settings_path()
        info(f"Settings file: {path}")
        info(f"Wake phrase: '{settings.get('wake_phrase', 'wake up son')}'")
        print()
        return settings
    except Exception as e:
        error(f"Failed to load settings: {e}")
        return {}


def check_recent_logs() -> None:
    """Display recent wake listener log entries."""
    header("7. RECENT WAKE LISTENER LOGS")
    if not LOG_PATH.exists():
        info("No log file yet (listener hasn't run)")
        return
    
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Show last 30 lines
        recent = lines[-30:] if len(lines) > 30 else lines
        for line in recent:
            print(line.rstrip())
        print()
    except Exception as e:
        error(f"Failed to read log: {e}")


def test_audio_stream() -> bool:
    """Attempt a short audio stream test."""
    header("8. TESTING AUDIO STREAM")
    try:
        import sounddevice as sd
        import numpy as np
        
        print("Recording 3 seconds of audio to test microphone...")
        duration = 3
        samplerate = 16000
        
        recording = sd.rec(int(samplerate * duration), samplerate=samplerate, channels=1, dtype='int16')
        sd.wait()
        
        # Check if we got audio
        peak = np.max(np.abs(recording))
        if peak > 100:
            success(f"Microphone working! Peak level: {peak}")
            return True
        else:
            error(f"Microphone appears silent. Peak level: {peak} (expected > 100)")
            print("\nTRY:")
            print("  • Check microphone is plugged in and enabled")
            print("  • Check Windows audio input level is not muted")
            print("  • Check application audio permissions\n")
            return False
    except Exception as e:
        error(f"Audio stream test failed: {e}")
        return False


def run_self_test() -> bool:
    """Run the built-in wake listener self-test."""
    header("9. RUNNING WAKE LISTENER SELF-TEST")
    try:
        result = subprocess.run(
            [sys.executable, "morice_wake_listener.py", "--self-test"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(ROOT),
        )
        print(result.stdout)
        if result.returncode == 0:
            success("Self-test passed")
            return True
        else:
            error("Self-test failed")
            if result.stderr:
                print(result.stderr)
            return False
    except Exception as e:
        error(f"Could not run self-test: {e}")
        return False


def main() -> int:
    print("""
╔════════════════════════════════════════════════════════════╗
║     MORICE WAKE LISTENER DIAGNOSTIC TOOL                  ║
║                                                            ║
║ This tool will check your setup and identify issues.      ║
╚════════════════════════════════════════════════════════════╝
""")
    
    results = {
        "vosk_installed": check_vosk_installed(),
        "sounddevice_installed": check_sounddevice_installed(),
        "audio_devices": list_audio_devices(),
    }
    
    model_path = find_vosk_model_path()
    results["model_found"] = model_path is not None
    
    if model_path:
        results["model_usable"] = check_vosk_model_usable(model_path)
    
    settings = check_settings()
    check_recent_logs()
    results["audio_working"] = test_audio_stream()
    results["self_test"] = run_self_test()
    
    # Summary
    header("DIAGNOSTIC SUMMARY")
    
    issues = []
    if not results["vosk_installed"]:
        issues.append("Vosk library not installed")
    if not results["sounddevice_installed"]:
        issues.append("sounddevice library not installed")
    if not results.get("model_found"):
        issues.append("No Vosk model found")
    if not results.get("model_usable"):
        issues.append("Vosk model failed to load")
    if not results.get("audio_working"):
        issues.append("Microphone not working or too quiet")
    if not results.get("self_test"):
        issues.append("Wake listener self-test failed")
    
    if not issues:
        success("All checks passed! Wake listener should work.")
        print("\nStart the listener with:")
        print("  python morice_wake_listener.py\n")
        return 0
    
    error(f"Found {len(issues)} issue(s):\n")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
    print()
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nDiagnostic cancelled.")
        sys.exit(1)
    except Exception as e:
        error(f"Diagnostic failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
