"""Private JPEG/PNG storage with MIME, signature, size and decoder checks."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import warnings

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError


def prepare_image(file_storage, folder, crop=None, *, limit=None):
    if not file_storage or not file_storage.filename:
        raise ValueError('Please select a JPEG or PNG image.')
    ext = Path(file_storage.filename).suffix.lower()
    formats = {'.jpg': ('JPEG', 'image/jpeg'), '.jpeg': ('JPEG', 'image/jpeg'), '.png': ('PNG', 'image/png')}
    if folder == 'profile_photos':
        formats['.webp'] = ('WEBP', 'image/webp')
    if ext not in formats or file_storage.mimetype != formats[ext][1]:
        raise ValueError('Only JPEG, PNG or WebP profile photos are allowed.' if folder == 'profile_photos' else 'Only JPEG and PNG images are allowed.')
    if limit is None:
        limit = current_app.config.get('MAX_IMAGE_BYTES', 5 * 1024 * 1024)
    data = file_storage.stream.read(limit + 1)
    if not data or len(data) > limit:
        max_mb = 4 if limit == 4_000_000 else 5
        raise ValueError(f'Image must be nonempty and no larger than {max_mb} MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != formats[ext][0] or image.width * image.height > 20_000_000:
                    raise ValueError('Invalid image format or image dimensions are too large.')
                image.verify()
            # Decode and re-encode: strips metadata and trailing embedded payloads.
            with Image.open(BytesIO(data)) as image:
                image.load()
                image = ImageOps.exif_transpose(image)
                if crop is not None and folder == 'profile_photos':
                    from math import isfinite
                    try:
                        zoom, x, y = (float(crop[key]) for key in ('zoom', 'x', 'y'))
                    except (ValueError, KeyError, TypeError) as exc:
                        raise ValueError('Invalid photo crop settings.') from exc
                    if not all(isfinite(v) for v in (zoom, x, y)) or not (1 <= zoom <= 3 and 0 <= x <= 1 and 0 <= y <= 1):
                        raise ValueError('Invalid photo crop settings.')
                    side = min(image.size) / zoom
                    left = max(0, min(image.width-side, x*image.width-side/2))
                    top = max(0, min(image.height-side, y*image.height-side/2))
                    image = image.crop((round(left), round(top), round(left+side), round(top+side)))
                if folder == 'profile_photos':
                    image.thumbnail((1600, 1600))
                image.info.clear()
                output = BytesIO()
                image.convert('RGB' if formats[ext][0] == 'JPEG' else 'RGBA').save(output, format=formats[ext][0])
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('The file is not a valid JPEG, PNG or WebP image.' if folder == 'profile_photos' else 'The file is not a valid JPEG or PNG image.') from exc
    if folder not in {'profile_photos', 'document_requirements', 'registration_documents', 'incident_evidence'}:
        raise ValueError('Invalid image storage location.')
    filename = uuid4().hex + {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}[formats[ext][0]]
    return filename, output.getvalue()


def save_image(file_storage, folder, crop=None):
    filename, data = prepare_image(file_storage, folder, crop)
    directory = Path(current_app.config['STORAGE_ROOT']) / folder
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_bytes(data)
    return filename


def remove_image(folder, filename):
    if not filename or Path(filename).name != filename:
        return
    if folder not in {'profile_photos', 'document_requirements', 'registration_documents', 'incident_evidence'}:
        raise ValueError('Invalid image storage location.')
    try:
        (Path(current_app.config['STORAGE_ROOT']) / folder / filename).unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning('Unable to remove obsolete image from %s', folder)
