import os


def describe_image(path: str) -> str:
    if not path or not os.path.exists(path):
        return "Image file not found."
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return "Image support is not available in this build."

    info = []
    try:
        with Image.open(path) as img:
            info.append(f"Image size: {img.width}x{img.height}, mode: {img.mode}.")
            info.append(
                "OCR is currently disabled in this build. "
                "##TESSERACT OCR## was used for earlier testing, but that dependency has been removed while a new OCR backend is prepared."
            )
    except Exception:
        return "Could not open the image file."

    if not info:
        return "Image attached, but no readable details were found."
    return " ".join(info)
