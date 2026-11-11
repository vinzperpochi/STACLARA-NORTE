"""Resolve existing private uploads across the two supported local storage layouts."""
from pathlib import Path
from flask import current_app


def private_image_path(folder, filename):
    if folder not in {'document_requirements', 'registration_documents', 'profile_photos'}:
        return None
    if not filename or Path(filename).name != filename or '/' in filename or '\\' in filename:
        return None
    extensions={'.jpg', '.jpeg', '.png'}
    if folder=='profile_photos': extensions.add('.webp')
    if Path(filename).suffix.lower() not in extensions:
        return None
    project=Path(current_app.root_path).parent
    configured=Path(current_app.config['STORAGE_ROOT'])
    if not configured.is_absolute(): configured=project/configured
    roots=[configured, project/'instance', project.parent/'instance']
    for root in roots:
        directory=(root/folder).resolve()
        candidate=directory/filename
        if candidate.resolve().parent==directory and candidate.is_file():
            return candidate
    return None
