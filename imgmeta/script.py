from pathlib import Path


import exiftool
from imgmeta import logger
from tqdm import tqdm

from imgmeta.helper import get_img_path, diff_meta, update_single_img
from imgmeta.meta import ImageMetaUpdate, rename_single_img

from typer import Typer, Option, Argument
from typing import List
app = Typer()

@app.command()
def write_meta(paths: List[Path]):
    for img in tqdm(list(get_img_path(paths))):
        with exiftool.ExifTool() as et:
            try:
                meta = et.get_metadata(img)
            except ValueError as e:
                logger.error(f'{img}:{e}')
            xmp_info = ImageMetaUpdate(meta).meta
            to_write = diff_meta(xmp_info, meta)
            update_single_img(img, to_write, et)


@app.command()
def rename(paths:List[Path], 
           new_dir:bool=Option(False, '--new-dir', '-d', help='whether make new dir')):
    print(paths)
    with exiftool.ExifTool() as et:
        for img in get_img_path(paths, sort=True):
            logger.info(img)
            rename_single_img(img, et, new_dir)
