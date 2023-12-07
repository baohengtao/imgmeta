import itertools
import shutil
from collections import defaultdict
from pathlib import Path
from typing import List

from exiftool import ExifTool, ExifToolHelper
from exiftool.exceptions import ExifToolExecuteError
from typer import Option, Typer

from imgmeta import console, get_progress
from imgmeta.helper import diff_meta, get_img_path, show_diff
from imgmeta.meta import ImageMetaUpdate, rename_single_img

app = Typer()


@app.command(help='Write meta to imgs')
def write_meta(
        paths: List[Path],
        prompt: bool = False,
        time_fix: bool = False,
        move_with_exception: bool = False,
        max_write: int = None):
    if not isinstance(paths, list):
        paths = [paths]
    imgs = itertools.chain.from_iterable(
        get_img_path(p, sort=False) for p in paths)

    with (ExifToolHelper() as et,
          ExifTool(common_args=['-G1', '-n']) as etl,
          get_progress(disable=prompt) as progress):

        count = 0

        for img in progress.track(list(imgs), description='writing meta...'):
            try:
                meta = et.get_metadata(img)[0]
                meta |= etl.execute_json(str(img), '-Keys:GPSCoordinates')[0]
                xmp_info = ImageMetaUpdate(
                    meta, prompt, time_fix).process_meta()
                if to_write := diff_meta(xmp_info, meta):
                    for k, v in to_write.copy().items():
                        if isinstance(v, str):
                            to_write[k] = v.replace('\n', '&#x0a;')

                    et.set_tags(img, to_write, params=[
                                '-ignoreMinorErrors', '-escapeHTML'])
                    console.log(img, style='bold')
                    show_diff(xmp_info, meta)
                    console.log()
                    if max_write and (count := count + 1) >= max_write:
                        break
            except ExifToolExecuteError as e:
                console.log(e.stdout, e.stderr, e.cmd, style='error')
                if not move_with_exception:
                    raise
                Path('./problem').mkdir(exist_ok=True)
                new_img = Path('./problem')/img.name
                if new_img != img:
                    assert not new_img.exists()
                    img.rename(new_img)
                console.log(f'{e}: {img}', style='error')
                console.log(f'{img} moved to {new_img}', style='error')


@app.command()
def write_ins():
    from insmeta.model import Artist as InsArtist
    stogram = Path.home()/'Pictures/4K Stogram'
    if not (p := Path('/Volumes/Art')).exists():
        p = Path.home()/'Pictures'
    dst_path = p/'Instagram'
    imgs = list(get_img_path(stogram))
    with (ExifToolHelper() as et, get_progress() as progress):
        for img in progress.track(imgs):
            meta = et.get_metadata(img)[0]
            patch = {
                "XMP:ImageSupplierName": "Instagram",
                "EXIF:UserComment": "",
                "EXIF:ImageDescription": "",
                "EXIF:Artist": "",
            }
            patch = {k: v for k, v in patch.items() if v or k in meta}
            xmp_info = ImageMetaUpdate(meta | patch).process_meta()
            xmp_info |= patch
            if to_write := diff_meta(xmp_info, meta):
                et.set_tags(img, to_write)
                console.log(img, style='bold')
                show_diff(xmp_info, meta)

            if (uid := xmp_info.get('XMP:ImageSupplierID')) is None:
                img_path = dst_path / 'None'
            elif InsArtist.get(user_id=uid).photos_num == 0:
                img_path = dst_path / 'New'
            else:
                img_path = dst_path / 'User'

            img_path.mkdir(exist_ok=True, parents=True)
            new_img = img_path / img.name
            assert not (new_img).exists()
            shutil.move(img, new_img)
            console.log(
                f'moved {img} to {new_img}', style='bold')


@app.command(help='Rename imgs and videos')
def rename(paths: List[Path],
           new_dir: bool = Option(
               False, '--new-dir', '-d', help='whether make new dir'),
           root: Path = Option(None),
           sep_mp4: bool = Option(False, '--sep-mp4', '-s'),
           sep_mov: bool = Option(False, '--sep-mov', '-m')
           ):
    if not isinstance(paths, list):
        paths = [paths]
    imgs = itertools.chain.from_iterable(
        get_img_path(p, sort=True) for p in paths)
    with (get_progress() as progress, ExifToolHelper() as et):
        for img in progress.track(list(imgs), description='renaming imgs...'):
            if img.suffix == '.mov' and sep_mov:
                continue
            meta = et.get_metadata(img)[0]
            rename_single_img(img, meta, new_dir, root, sep_mp4, sep_mov)


@app.command(help='Rename imgs and videos for Ins Photo')
def rename_ins(paths: List[Path],
               new_dir: bool = Option(
               False, '--new-dir', '-d', help='whether make new dir')):
    from insmeta.model import Artist as InsArtist
    if not isinstance(paths, list):
        paths = [paths]
    imgs = itertools.chain.from_iterable(
        get_img_path(p, sort=True) for p in paths)
    with (get_progress() as progress, ExifToolHelper() as et):
        for img in progress.track(list(imgs), description='renaming imgs...'):
            meta = et.get_metadata(img)[0]
            if (uid := meta.get('XMP:ImageSupplierID')) is None:
                subfolder = 'None'
            elif InsArtist.get(user_id=uid).photos_num == 0:
                subfolder = 'New'
                sep_mp4 = False
            else:
                subfolder = 'User'
                sep_mp4 = True
            rename_single_img(img, meta, new_dir,
                              root=subfolder, sep_mp4=sep_mp4)
