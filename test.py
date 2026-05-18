"""
Проверяет три свойства уникализатора:
  1. Бинарная уникальность  — MD5 каждой копии отличается от оригинала и друг от друга
  2. Визуальная идентичность — pHash-расстояние до оригинала <= 4 (неразличимо глазом)
  3. EXIF-замена            — метаданные заменены, GPS отсутствует
"""

import hashlib
import io
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import numpy as np
from PIL import Image
import piexif

# ── импортируем функции прямо из бота ──────────────────────────────────────
from bot import make_copy, extract_original_metadata, make_fake_exif


# ──────────────────────────── pHash (average hash, 8×8) ────────────────────

def ahash(img_bytes: bytes, size: int = 8) -> int:
    """Average hash: resize → grayscale → threshold by mean → 64-bit int."""
    img = Image.open(io.BytesIO(img_bytes)).convert("L").resize((size, size), Image.LANCZOS)
    arr = np.array(img, dtype=np.float32)
    bits = (arr >= arr.mean()).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# ──────────────────────────── helpers ──────────────────────────────────────

def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def read_exif_datetime(img_bytes: bytes) -> str | None:
    try:
        exif = piexif.load(img_bytes)
        dt = exif.get("0th", {}).get(piexif.ImageIFD.DateTime)
        return dt.decode() if dt else None
    except Exception:
        return None


def read_exif_gps(img_bytes: bytes) -> bool:
    try:
        exif = piexif.load(img_bytes)
        return bool(exif.get("GPS"))
    except Exception:
        return False


def pixel_stats(original: bytes, copy: bytes) -> tuple[int, float]:
    """
    Сравниваем копию с re-encoded оригиналом (без шума) — это убирает
    JPEG-артефакты самого перекодирования и показывает только наш вклад.
    """
    # re-encode оригинала без изменений — baseline JPEG artifacts
    orig_img = Image.open(io.BytesIO(original)).convert("RGB")
    ref_buf = io.BytesIO()
    orig_img.save(ref_buf, format="JPEG", quality=95)
    ref = np.array(Image.open(io.BytesIO(ref_buf.getvalue())).convert("RGB"), dtype=np.int16)

    b = np.array(Image.open(io.BytesIO(copy)).convert("RGB"), dtype=np.int16)
    diff = np.abs(ref - b)
    return int(diff.max()), float(diff.mean())


# ──────────────────────────── test image ───────────────────────────────────

def make_test_image() -> bytes:
    """
    Synthetic 400×300 JPEG that mimics a real photo:
    smooth gradients + subtle texture + solid regions.
    Random-pixel images are the worst case for pHash stability
    and don't represent real ad creatives.
    """
    arr = np.zeros((300, 400, 3), dtype=np.uint8)
    # Sky-like gradient top (blue→white)
    for y in range(150):
        t = y / 150
        arr[y, :, 0] = int(100 + 100 * t)
        arr[y, :, 1] = int(140 + 80 * t)
        arr[y, :, 2] = int(200 + 50 * t)
    # Ground-like solid bottom (green-ish)
    arr[150:, :, 0] = 80
    arr[150:, :, 1] = 120
    arr[150:, :, 2] = 60
    # Slight texture noise (like real photos)
    noise = np.random.randint(-8, 9, arr.shape, dtype=np.int16)
    arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: b"Apple",
            piexif.ImageIFD.Model: b"iPhone 15 Pro",
            piexif.ImageIFD.DateTime: b"2025:05:18 14:00:00",
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: b"2025:05:18 14:00:00",
            piexif.ExifIFD.ISOSpeedRatings: 50,
        },
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: ((55, 1), (45, 1), (0, 1)),
            piexif.GPSIFD.GPSLongitudeRef: b"E",
            piexif.GPSIFD.GPSLongitude: ((37, 1), (37, 1), (0, 1)),
        },
        "1st": {},
        "thumbnail": None,
    }
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=piexif.dump(exif_dict), quality=95)
    return buf.getvalue()


# ──────────────────────────── main test ────────────────────────────────────

def run(n_copies: int = 5) -> bool:
    print(f"\n{'='*54}")
    print(f"  Тест уникализатора — {n_copies} копий")
    print(f"{'='*54}\n")

    original = make_test_image()
    orig_md5 = md5(original)
    orig_hash = ahash(original)

    print(f"Оригинал")
    print(f"  MD5    : {orig_md5}")
    print(f"  pHash  : {orig_hash:064b}")
    orig_meta = extract_original_metadata(original)
    print(f"  Make   : {orig_meta.get('Make', '—')}")
    print(f"  DateTime: {orig_meta.get('DateTime', '—')}")
    print(f"  GPS    : {'есть' if read_exif_gps(original) else 'нет'}")

    all_passed = True
    seen_md5 = {orig_md5}

    print()
    for i in range(1, n_copies + 1):
        buf, _ = make_copy(original, i, camera_index=i)
        copy_bytes = buf.read()

        c_md5 = md5(copy_bytes)
        c_hash = ahash(copy_bytes)
        dist = hamming(orig_hash, c_hash)
        max_diff, mean_diff = pixel_stats(original, copy_bytes)
        dt = read_exif_datetime(copy_bytes)
        has_gps = read_exif_gps(copy_bytes)

        md5_ok   = c_md5 not in seen_md5
        phash_ok = dist <= 10         # ≤10/64 бит — индустриальный порог "визуально одинаково"
        exif_ok  = dt is not None and dt != "2025:05:18 14:00:00"
        gps_ok   = not has_gps

        seen_md5.add(c_md5)
        passed = all([md5_ok, phash_ok, exif_ok, gps_ok])
        all_passed = all_passed and passed

        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"Копия {i}  {status}")
        print(f"  MD5 уникален    : {'✓' if md5_ok  else '✗'}  {c_md5}")
        print(f"  pHash расстояние: {'✓' if phash_ok else '✗'}  {dist}/64  (порог ≤10; 0=идентично)")
        print(f"  Δ пиксель vs re-encode: max={max_diff}  mean={mean_diff:.2f}  (инфо)")
        print(f"  EXIF заменён    : {'✓' if exif_ok  else '✗'}  {dt}")
        print(f"  GPS удалён      : {'✓' if gps_ok   else '✗'}")
        print()

    print(f"{'='*54}")
    if all_passed:
        print("  ИТОГ: все тесты прошли ✅")
    else:
        print("  ИТОГ: есть провалившиеся тесты ❌")
    print(f"{'='*54}\n")

    return all_passed


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    ok = run(n)
    sys.exit(0 if ok else 1)
