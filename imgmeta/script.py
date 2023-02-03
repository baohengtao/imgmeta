import itertools
from collections import defaultdict
from pathlib import Path
from typing import List

from exiftool import ExifTool
from typer import Option, Typer

from imgmeta import console, get_progress
from imgmeta.helper import diff_meta, get_img_path
from imgmeta.meta import ImageMetaUpdate, rename_single_img

app = Typer()


@app.command(help='Write meta to imgs')
def write_meta(paths: List[Path]):
    if not isinstance(paths, list):
        paths = [paths]
    imgs = itertools.chain.from_iterable(
        get_img_path(p, sort=False) for p in paths)
    
    with (get_progress() as progress, ExifTool() as et):
        for img in progress.track(list(imgs), description='writing meta...'):
            meta = et.get_metadata(img)
            xmp_info = ImageMetaUpdate(meta).meta
            if to_write := diff_meta(xmp_info, meta):
                console.log(f'{img}=>write xmp_info:{to_write}\n')
                et.set_tags(to_write, str(img))


@app.command(help='Rename imgs and videos')
def rename(paths: List[Path],
           new_dir: bool = Option(
               False, '--new-dir', '-d', help='whether make new dir'),
           root: Path = Option(None)):
    if not isinstance(paths, list):
        paths = [paths]
    imgs = itertools.chain.from_iterable(
        get_img_path(p, sort=True) for p in paths)
    with (get_progress() as progress, ExifTool() as et):
        for img in progress.track(list(imgs), description='renaming imgs...'):
            rename_single_img(img, et, new_dir, root)


@app.command()
def tidy_liked(path: Path):
    imgs = list(get_img_path(path, sort=False))
    with ExifTool() as et:
        uids = et.get_tag_batch('XMP:ImageSupplierID', imgs)

    uid2imgs = defaultdict(set)

    for uid, img in zip(uids, imgs):
        uid2imgs[uid].add(img)

    for uid, imgs in uid2imgs.items():
        dst_path = path / str(len(imgs))
        dst_path.mkdir(exist_ok=True, parents=True)

        for img in imgs:
            img = Path(img)
            img_new = dst_path / img.name
            if img == img_new:
                break
            assert not img_new.exists()
            img.rename(img_new)
