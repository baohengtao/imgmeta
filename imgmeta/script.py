import itertools
import os
import shutil
from pathlib import Path
from typing import List

from exiftool import ExifTool, ExifToolHelper
from exiftool.exceptions import ExifToolExecuteError
from photosinfo.model import Girl
from playhouse.shortcuts import model_to_dict
from typer import Option, Typer
from typing_extensions import Annotated

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
        get_img_path(p) for p in paths)

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
                f'moving {img} to {new_img}...', style='bold')


@app.command(help='Rename imgs and videos')
def rename(paths: List[Path],
           new_dir: Annotated[bool, Option(
               '--new-dir/--no-new-dir', '-d/-D')] = False,
           root: Path = None,
           sep_mp4: Annotated[bool, Option('--sep-mp4', '-s')] = False,
           sep_mov: Annotated[bool, Option('--sep-mov', '-m')] = False,
           sep_new: Annotated[bool, Option('--sep-new', '-n')] = False
           ):
    assert not (sep_new and root)
    if not isinstance(paths, list):
        paths = [paths]
    imgs = itertools.chain.from_iterable(
        get_img_path(p) for p in paths)
    new_ids = {}
    for girl in Girl:
        girl_dict = model_to_dict(girl)
        for col in ['sina', 'red', 'inst']:
            if uid := girl_dict[f'{col}_id']:
                assert uid not in new_ids
                new_ids[uid] = girl_dict[f'{col}_num']
    old_ids = {uid for uid, num in new_ids.items() if num > 0}

    with (get_progress() as progress, ExifToolHelper() as et):
        for img in progress.track(list(imgs), description='renaming imgs...'):
            if img.suffix == '.mov' and sep_mov:
                continue
            meta = et.get_metadata(img)[0]
            if (uid := meta.get('XMP:ImageSupplierID')) is None:
                subfolder = 'None'
            elif uid in old_ids:
                subfolder = 'User'
            else:
                subfolder = 'New'
            if sep_new:
                root = subfolder
                sep_mp4 = (subfolder == 'User')

            rename_single_img(img, meta, new_dir, root, sep_mp4, sep_mov)


@app.command(help='Clean files')
def clean_file(path: Path):
    media_ext = ('.jpg', '.mov', '.png', '.jpeg',
                 '.mp4', '.gif', '.heic', '.webp')
    fmt = {f'{ext}_original' for ext in media_ext}
    assert path.is_dir()
    for file in path.iterdir():
        if file.is_dir():
            clean_file(file)
            continue
        if (suf := file.suffix).endswith('_original'):
            assert suf in fmt
        elif file.name != '.DS_Store':
            continue
        console.log(f"removing {file}")
        file.unlink()
    if path == Path('.') or any(path.iterdir()):
        return
    console.log(f"removing {path}")
    os.rmdir(path)
