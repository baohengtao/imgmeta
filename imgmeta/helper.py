from collections import defaultdict
from pathlib import Path
from time import sleep

import keyring
from exiftool import ExifTool
from geopy import geocoders
from loguru import logger


def get_addr(query):
    from imgmeta.database import geo_table as table
    locator = geocoders.GoogleV3(api_key=keyring.get_password("google_map", "api_key"))
    for symbol in ['@', 'http', '#']:
        if symbol in query:
            logger.warning(f'reject for 「{symbol}」 in 「{query}」')
            return
    if addr := geo_table.find_one(query=query):
        return addr
    addr = locator.geocode(query, language='zh')
    addr = dict(
        query=query,
        address=addr.address,
        longitude=addr.longitude,
        latitude=addr.latitude)
    geo_table.insert(addr)
    logger.success(f'\nwrite geo_info: {addr}\n')
    sleep(1.0)
    return addr


def get_img_path(path):
    path = Path(path)
    if path.is_file():
        return [path]
    media_ext = ('.jpg', '.mov', '.png', '.jpeg', '.mp4', '.gif')
    for img in Path(path).rglob('*.*'):
        if not img.is_file() or _is_hidden(path):
            continue
        if not img.suffix.lower().endswith(media_ext):
            continue
        yield str(img)


def _is_hidden(path):
    for part in path.parts:
        if part.startswith('.'):
            return True


def sort_img_path(imgs):
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
