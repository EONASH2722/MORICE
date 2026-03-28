import os
import shutil
import subprocess
import tempfile
from PIL import ImageStat, ImageFilter


def describe_image(path: str) -> str:
    if not path or not os.path.exists(path):
        return "Image file not found."
    try:
        from PIL import Image, ImageOps
    except Exception:  # noqa: BLE001
        return "Image support is not available in this build."

    def resolve_tesseract() -> str:
        tess_path = os.getenv("MORICE_TESSERACT_PATH", "").strip()
        if tess_path and os.path.exists(tess_path):
            return tess_path
        local = os.path.join(os.path.dirname(__file__), "assets", "tesseract", "tesseract.exe")
        if os.path.exists(local):
            return local
        which = shutil.which("tesseract")
        return which or ""

    def run_tesseract(image_path: str, tess_path: str, configs: list[list[str]]) -> str:
        tess_root = os.path.dirname(tess_path)
        if os.path.isdir(os.path.join(tess_root, "tessdata")):
            os.environ.setdefault("TESSDATA_PREFIX", tess_root)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_base = os.path.join(tmpdir, "out")
            try:
                for config in configs:
                    subprocess.run(
                        [tess_path, image_path, out_base, *config],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                    txt_path = out_base + ".txt"
                    if os.path.exists(txt_path):
                        with open(txt_path, "r", encoding="utf-8", errors="ignore") as handle:
                            text = handle.read().strip()
                        if text:
                            return text
                        try:
                            os.remove(txt_path)
                        except OSError:
                            pass
            except Exception:
                return ""
            return ""

    info = []
    try:
        with Image.open(path) as img:
            info.append(f"Image size: {img.width}x{img.height}, mode: {img.mode}.")
            tess_path = resolve_tesseract()
            if tess_path:
                configs = [
                    ["--oem", "3", "--psm", "6"],
                    ["--oem", "3", "--psm", "11"],
                ]
                text = run_tesseract(path, tess_path, configs)
                if not text:
                    variants = []
                    try:
                        gray = ImageOps.grayscale(img)
                        gray = ImageOps.autocontrast(gray)
                        variants.append(gray)
                        variants.append(ImageOps.invert(gray))
                        variants.append(gray.filter(ImageFilter.SHARPEN))
                        variants.append(gray.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3)))
                        big = gray.resize((img.width * 2, img.height * 2))
                        variants.append(big)
                        variants.append(ImageOps.autocontrast(big))
                    except Exception:
                        variants = []

                    for variant in variants:
                        pre_path = ""
                        try:
                            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                                variant.save(tmp.name, format="PNG")
                                pre_path = tmp.name
                            text = run_tesseract(pre_path, tess_path, configs)
                            if text:
                                break
                        except Exception:
                            pass
                        finally:
                            try:
                                if pre_path:
                                    os.remove(pre_path)
                            except Exception:
                                pass
                if text:
                    info.append("Detected text: " + " ".join(text.split()))
                else:
                    info.append("No readable text detected.")
            else:
                info.append(
                    "OCR not available. Put tesseract.exe in morice\\assets\\tesseract or set MORICE_TESSERACT_PATH."
                )
    except Exception:
        return "Could not open the image file."

    if not info:
        return "Image attached, but no readable details were found."
    return " ".join(info)
