import time
from collections import defaultdict
from threading import Lock
from time import sleep

import dataset
import geopy
import keyring
from exiftool import ExifTool
from geopy import geocoders

from imgmeta import console

geo_table = dataset.Database('postgresql://localhost/imgmeta')['geolocation']


def get_addr(query):
    locator = geocoders.GoogleV3(api_key=keyring.get_password("google_map", "api_key"))
    for symbol in ['@', 'http', '#']:
        if symbol in query:
            console.log(f'reject for 「{symbol}」 in 「{query}」', style='warning')
            return
    if addr := geo_table.find_one(query=query):
        return addr
    try:
        with Lock():
            addr = locator.geocode(query, language='zh')
            time.sleep(0.1)
    except geopy.exc.GeocoderUnavailable as e:
        return

    if not addr:
        return

    addr = dict(
        query=query,
        address=addr.address,
        longitude=addr.longitude,
        latitude=addr.latitude)
    geo_table.insert(addr)
    console.log(f'\nwrite geo_info: {addr}\n')
    sleep(1.0)
    return addr


def get_img_path(path, sort=False):
    media_ext = ('.jpg', '.mov', '.png', '.jpeg', '.mp4', '.gif')
    files = []
    for p in path.iterdir():
        if any(part.startswith('.') for part in p.parts):
            continue
        elif p.is_dir():
            yield from get_img_path(p, sort)
        elif p.is_file():
            if not p.suffix.lower().endswith(media_ext):
                continue
            files.append(str(p))
    if sort:
        yield from _sort_img(files)
    else:
        yield from files


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
    console.log(f'{img_path}=>write xmp_info:{to_write}\n')
    et.set_tags(to_write, str(img_path))
