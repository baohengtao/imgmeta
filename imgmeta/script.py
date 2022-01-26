from pathlib import Path
from typing import List

from typer import Typer, Option

from imgmeta import console
from imgmeta.helper import get_img_path, diff_meta, update_single_img
from imgmeta.meta import ImageMetaUpdate, rename_single_img
from concurrent.futures import ThreadPoolExecutor
from exiftool import ExifTool
import itertools
from rich.progress import track
app = Typer()


def write_meta_item(img):
    with ExifTool() as et:
        try:
            meta = et.get_metadata(img)
        except ValueError:
            console.log(f'value error => {img}', style='error')
            return
        xmp_info = ImageMetaUpdate(meta).meta
        to_write = diff_meta(xmp_info, meta)
        update_single_img(img, to_write, et=et)


@app.command(help='Write meta to imgs')
def write_meta(paths: List[Path]):
    imgs = itertools.chain.from_iterable(get_img_path(p, sort=False) for p in paths)

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = []
        for img in track(list(imgs)):
            futures.append(pool.submit(write_meta_item, img))
        for future in futures:
            future.result()


@app.command(help='Rename imgs and videos')
def rename(paths: List[Path],
           new_dir: bool = Option(False, '--new-dir', '-d', help='whether make new dir')):

    imgs = itertools.chain.from_iterable(get_img_path(p, sort=True) for p in paths)
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = []
        for img in track(list(imgs)):
            args = (img, new_dir)
            futures.append(pool.submit(rename_single_img, *args))

        for future in futures:
            future.result()


