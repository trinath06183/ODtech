import io
from PIL import Image
from django.core.files.base import ContentFile

def compress_image_to_target(file):
    """
    Compresses an uploaded image file so that its final size is at most 3 MB.
    Uses high quality settings and only reduces quality/dimensions when necessary.
    Preserves non-image files (PDF, ZIP, etc.) untouched.
    """
    try:
        file.seek(0)
        img = Image.open(file)
    except Exception:
        # Not an image (e.g., PDF, ZIP, TXT), return original file untouched
        return file

    # Normalize image to RGB mode
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'RGBA':
            background.paste(img, mask=img.split()[3])
        else:
            background.paste(img.convert('RGBA'), mask=img.convert('RGBA').split()[3])
        img = background
    else:
        img = img.convert('RGB')

    max_bytes = 3 * 1024 * 1024  # 3 MB

    # Try saving at high quality (85) first
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85, optimize=True)
    initial_size = buf.tell()

    # If the image is already within 3 MB at quality 85, keep it as is
    if initial_size <= max_bytes:
        buf.seek(0)
        new_name = '.'.join(file.name.split('.')[:-1]) + '.jpg' if '.' in file.name else file.name + '.jpg'
        return ContentFile(buf.read(), name=new_name)

    # Step 1: Try reducing quality (from 80 down to 40) without resizing
    best_buf = None
    for quality in range(80, 35, -5):
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality, optimize=True)
        size = buf.tell()
        if size <= max_bytes:
            best_buf = buf
            break

    if best_buf:
        best_buf.seek(0)
        new_name = '.'.join(file.name.split('.')[:-1]) + '.jpg' if '.' in file.name else file.name + '.jpg'
        return ContentFile(best_buf.read(), name=new_name)

    # Step 2: Quality reduction alone wasn't enough, resize dimensions iteratively
    width, height = img.size
    scale = 0.9
    while scale > 0.2:
        new_w = max(100, int(width * scale))
        new_h = max(100, int(height * scale))
        resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        resized_img.save(buf, format='JPEG', quality=70, optimize=True)
        size = buf.tell()

        if size <= max_bytes:
            buf.seek(0)
            new_name = '.'.join(file.name.split('.')[:-1]) + '.jpg' if '.' in file.name else file.name + '.jpg'
            return ContentFile(buf.read(), name=new_name)

        scale -= 0.1

    # Step 3: Last resort — aggressively resize and compress
    new_w = max(100, int(width * 0.2))
    new_h = max(100, int(height * 0.2))
    resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    resized_img.save(buf, format='JPEG', quality=50, optimize=True)
    buf.seek(0)
    new_name = '.'.join(file.name.split('.')[:-1]) + '.jpg' if '.' in file.name else file.name + '.jpg'
    return ContentFile(buf.read(), name=new_name)

