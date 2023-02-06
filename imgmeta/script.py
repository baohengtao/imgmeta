import itertools
from collections import defaultdict
from pathlib import Path
from typing import List

from exiftool import ExifTool
from typer import Option, Typer
from imgmeta import console, get_progress, track
from imgmeta.helper import diff_meta2, get_img_path, show_diff
from imgmeta.meta import ImageMetaUpdate, rename_single_img

app = Typer()


@app.command(help='Write meta to imgs')
def write_meta(
        paths: List[Path],
        prompt: bool = False,
        time_fix: bool = False):
    if not isinstance(paths, list):
        paths = [paths]
    imgs = itertools.chain.from_iterable(
        get_img_path(p, sort=False) for p in paths)

    with ExifTool() as et:
        if not prompt:
            imgs = track(list(imgs), description='writing meta...')
        for img in imgs:
            meta = et.get_metadata(img)
            xmp_info = ImageMetaUpdate(meta, prompt, time_fix).process_meta()
            if to_write := diff_meta2(xmp_info, meta):
                et.set_tags(to_write, str(img))
                console.log(img, style='bold')
                show_diff(xmp_info, meta)
                console.log()


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
