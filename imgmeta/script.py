from itertools import chain

import exiftool
import click

from imgmeta.helper import get_img_path, diff_meta, update_single_img
from imgmeta.meta import ImageMetaUpdate, rename_single_img

@click.command()
def write_meta(paths):
    for img in get_img_path(paths):
        with exiftool.ExifTool() as et:
            meta = et.get_metadata(img)
            xmp_info = ImageMetaUpdate(meta).meta
            to_write = diff_meta(xmp_info, meta)
            update_single_img(img, to_write, et)

def rename(paths, new_dir=False):
    with exiftool.ExifTool() as et:
        for img in get_img_path(paths):
            rename_single_img(img, et, new_dir)
      

