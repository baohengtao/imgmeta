from collections import defaultdict
from pathlib import Path
from typing import Iterator

from exiftool import ExifToolHelper
from geopy.distance import geodesic

from imgmeta import console


def get_img_path(path: Path, sort=False, skip_dir=None) -> Iterator[Path]:
    media_ext = ('.jpg', '.mov', '.png', '.jpeg', '.mp4', '.gif')
    files = []
    paths = [path] if path.is_file() else path.iterdir()
    for p in paths:
        if any(part.startswith('.') for part in p.parts):
            continue
        elif p.is_file():
            if not p.suffix.lower().endswith(media_ext):
                continue
            files.append(p)
        elif p.is_dir():
            if skip_dir and skip_dir in p.stem:
                continue
            yield from get_img_path(p, sort)
    if sort:
        yield from _sort_img(files)
    else:
        yield from files


def _sort_img(imgs: list[Path]) -> Iterator[Path]:
    with ExifToolHelper() as et:
        tags = et.get_tags(imgs, 'XMP:ImageUniqueID') if imgs else []
    imgs_dict = defaultdict(list)
    for tag in tags:
        imgs_dict[tag.get('XMP:ImageUniqueID')].append(tag['SourceFile'])
    for value in sorted(imgs_dict.values(), key=lambda x: -len(x)):
        for img in sorted(value):
            yield Path(img)


def diff_meta(modified: dict, original: dict):
    assert set(modified).issuperset(original)
    to_write = {}
    for k, v in modified.items():
        if k in original and str(v) == str(original[k]):
            continue
        assert k in original or v
        to_write[k] = v
    return to_write


def show_diff(modified: dict, original: dict):
    assert set(modified).issuperset(original)
    for k, v in modified.items():
        if k in original and str(v) == str(original[k]):
            continue
        assert k in original or v
        if v != '':
            console.log(f'+{k}: {v}', style='green')
        if k in original:
            console.log(f'-{k}: {original[k]}', style='red')
        if k == 'XMP:Geography' and k in original:
            dist = geodesic(original[k], v).meters
            location = modified["XMP:Location"]
            console.log(
                f'Location {location} moved with {dist}m', style='warning')
