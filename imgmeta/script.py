import itertools
from pathlib import Path
from typing import List

import exiftool
from typer import Typer, Option

from imgmeta import console, get_progress
from imgmeta.helper import get_img_path, diff_meta
from imgmeta.meta import ImageMetaUpdate, rename_single_img

app = Typer()


def update_single_img(img_path, to_write, et):
    if not to_write:
        return
    console.log(f'{img_path}=>write xmp_info:{to_write}\n')
    et.set_tags(to_write, str(img_path))


def write_meta_item(img, et):
    try:
        meta = et.get_metadata(img)
    except ValueError as e:
        console.log(f'value error => {img}', style='error')
        raise e
    xmp_info = ImageMetaUpdate(meta).meta
    to_write = diff_meta(xmp_info, meta)
    update_single_img(img, to_write, et=et)


@app.command(help='Write meta to imgs')
def write_meta(paths: List[Path]):
    if not isinstance(paths, list):
        paths = [paths]
    imgs = itertools.chain.from_iterable(
        get_img_path(p, sort=False) for p in paths)
    imgs = list(imgs)
    with get_progress() as progress:
        with exiftool.ExifTool() as et:
            for img in progress.track(imgs, description='writing meta...'):
                try:
                    write_meta_item(img, et)
                except ValueError as e:
                    raise e


@app.command(help='Rename imgs and videos')
def rename(paths: List[Path],
           new_dir: bool = Option(
               False, '--new-dir', '-d', help='whether make new dir'),
           root: Path = Option(None)):

    if not isinstance(paths, list):
        paths = [paths]
    imgs_sort = itertools.chain.from_iterable(
        get_img_path(p, sort=True) for p in paths)
    imgs = itertools.chain.from_iterable(
        get_img_path(p, sort=False) for p in paths)
    with get_progress() as progress:
        with exiftool.ExifTool() as et:
            for img in progress.track(
                    imgs_sort,
                    description='renaming imgs...',
                    total=len(list(imgs))):
                rename_single_img(img, et, new_dir, root)
