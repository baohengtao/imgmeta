from collections import defaultdict
from pathlib import Path
from time import sleep

import dataset
import keyring
from exiftool import ExifTool
from geopy import geocoders
import geopy
from imgmeta import logger
import time

geo_table = dataset.Database('postgresql://localhost/imgmeta')['geolocation']


def get_addr(query):
    locator = geocoders.GoogleV3(api_key=keyring.get_password("google_map", "api_key"))
    for symbol in ['@', 'http', '#']:
        if symbol in query:
            logger.warning(f'reject for 「{symbol}」 in 「{query}」')
            return
    if addr := geo_table.find_one(query=query):
        return addr
    while True:
        try:
            addr = locator.geocode(query, language='zh')
            break
        except geopy.exc.GeocoderUnavailable as e:
            logger.info('sleeping 1 miniute')
            time.sleep(60)
            continue
            
    addr = dict(
        query=query,
        address=addr.address,
        longitude=addr.longitude,
        latitude=addr.latitude)
    geo_table.insert(addr)
    logger.success(f'\nwrite geo_info: {addr}\n')
    sleep(1.0)
    return addr


def get_img_path(paths: list[Path], sort=False):
    for path in paths:
        imgs = _filter_img(path)
        if sort:
            yield from _sort_img(imgs)
        else:
            yield from imgs


def _filter_img(path: Path):
    path = Path(path)
    media_ext = ('.jpg', '.mov', '.png', '.jpeg', '.mp4', '.gif')
    imgs = [path] if path.is_file() or path.rglob('*')
    for img in imgs:
        if any(part.startswith('.') for part in path.parts):
            continue
        if not img.is_file():
            continue
        if not img.suffix.lower().endswith(media_ext):
            continue
        yield str(img)


def _sort_img(imgs):
    imgs_dict = defaultdict(list)
    with ExifTool() as et:
        for img in imgs:
            img_id = et.get_tag('XMP:ImageUniqueID', img)
            imgs_dict[img_id].append(img)
    for key, value in sorted(imgs_dict.items(), key=lambda x: -len(x[1])):
        for img in sorted(value):
            yield img


def diff_meta(meta, original):
    if not meta:
        return
    to_write = dict()
    for k, v in meta.items():
        for white_list in ['ICC_Profile', 'MarkerNotes', 'Composite']:
            if k.startswith(white_list):
                k = None
                break
        if not k:
            continue

        v_meta = str(v).strip()
        v_ori = str(original.get(k, '')).strip()
        if v_meta == v_ori:
            if k in original and v_meta == '':
                to_write[k] = v
        else:
            to_write[k] = v
    return to_write


def update_single_img(img_path, to_write, et):
    if not to_write:
        # logger.debug(f'{img_path}=>Nothing to write')
        return
    logger.info(f'{img_path}=>write xmp_info:{to_write}\n')
    et.set_tags(to_write, str(img_path))
