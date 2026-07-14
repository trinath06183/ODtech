import io
from PIL import Image
from django.core.files.base import ContentFile

def compress_image_to_target(file):
    """
    Compresses an uploaded image file so that its final size is in the 15 KB - 20 KB range (max 20 KB).
    Preserves non-image files.
    """
    try:
        # Seek to start just in case it was read elsewhere
        file.seek(0)
        img = Image.open(file)
    except Exception:
        # Not an image (e.g., PDF, ZIP, TXT), return original file untouched
        return file

    # Normalize image to RGB mode
    # Handle alpha channel (RGBA/LA) by placing on a white background
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'RGBA':
            background.paste(img, mask=img.split()[3])
        else:
            background.paste(img.convert('RGBA'), mask=img.convert('RGBA').split()[3])
        img = background
    else:
        img = img.convert('RGB')

    min_bytes = 15 * 1024
    max_bytes = 20 * 1024

    # Try saving at a high quality (85) first
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85)
    initial_size = buf.tell()

    # If the image is already smaller than 20 KB at quality 85, keep it as is
    if initial_size <= max_bytes:
        buf.seek(0)
        new_name = '.'.join(file.name.split('.')[:-1]) + '.jpg' if '.' in file.name else file.name + '.jpg'
        return ContentFile(buf.read(), name=new_name)

    # Otherwise, we need to compress/resize to fit the 15-20 KB budget
    width, height = img.size
    best_img = img
    
    # Check size at lowest acceptable quality (15) to decide if we need to resize dimensions
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=15)
    size_at_q15 = buf.tell()

    if size_at_q15 > max_bytes:
        # Resizing is necessary. Scale down iteratively.
        scale = 0.9
        while scale > 0.05:
            new_w = max(10, int(width * scale))
            new_h = max(10, int(height * scale))
            resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            buf = io.BytesIO()
            resized_img.save(buf, format='JPEG', quality=50)
            size_at_q50 = buf.tell()
            
            if size_at_q50 <= max_bytes:
                best_img = resized_img
                break
            scale -= 0.1

    # Tune quality of best_img using binary search to land between 15 KB and 20 KB
    low_q = 10
    high_q = 95
    final_quality = 70
    final_buf = None

    for _ in range(7):
        mid_q = (low_q + high_q) // 2
        buf = io.BytesIO()
        best_img.save(buf, format='JPEG', quality=mid_q)
        size = buf.tell()

        if min_bytes <= size <= max_bytes:
            final_quality = mid_q
            final_buf = buf
            break
        elif size > max_bytes:
            high_q = mid_q - 1
            final_buf = buf
            final_quality = mid_q
        else:
            low_q = mid_q + 1
            final_buf = buf
            final_quality = mid_q

    if final_buf is None:
        final_buf = io.BytesIO()
        best_img.save(final_buf, format='JPEG', quality=final_quality)

    # Absolute safety cap: if still somehow above max_bytes, force quality 10
    if final_buf.tell() > max_bytes:
        final_buf = io.BytesIO()
        best_img.save(final_buf, format='JPEG', quality=10)

    final_buf.seek(0)
    new_name = '.'.join(file.name.split('.')[:-1]) + '.jpg' if '.' in file.name else file.name + '.jpg'
    return ContentFile(final_buf.read(), name=new_name)
