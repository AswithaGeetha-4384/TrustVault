import os
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateFileSystemStorage(FileSystemStorage):
    def __init__(self, location=None, base_url=None, file_permissions_mode=None, directory_permissions_mode=None):
        if location is None:
            location = settings.PRIVATE_STORAGE_ROOT
        if base_url is None:
            base_url = ''
        super().__init__(
            location=location,
            base_url=base_url,
            file_permissions_mode=file_permissions_mode,
            directory_permissions_mode=directory_permissions_mode,
        )

    def url(self, name):
        return ''


def safe_private_path(filename: str) -> str:
    safe_name = Path(filename).name
    if safe_name in {'', '.', '..'}:
        raise ValueError('Invalid uploaded filename.')
    if safe_name.startswith('.'):
        raise ValueError('Hidden filenames are not allowed.')
    return safe_name
