import time
from collections import defaultdict
from pathlib import Path
from time import sleep

import geopy
import keyring
from exiftool import ExifTool
from geopy import geocoders
from peewee import Model, TextField, FloatField
from playhouse.postgres_ext import PostgresqlExtDatabase

from imgmeta import console

ADDR_NOT_FOUND = []

# geo_table = DataSet('postgresql://localhost/imgmeta')['geolocation']


class BaseModel(Model):
    class Meta:
        database = PostgresqlExtDatabase(
            'imgmeta', host='localhost', autorollback=True)


class Geolocation(BaseModel):
    query = TextField()
    address = TextField()
    longitude = FloatField()
    latitude = FloatField()


def get_addr(query):
    locator = geocoders.GoogleV3(
        api_key=keyring.get_password("google_map", "api_key"))
    for symbol in ['@', 'http', '#']:
        if symbol in query:
            console.log(f'reject for 「{symbol}」 in 「{query}」', style='warning')
            return
    if query in ADDR_NOT_FOUND:
        return
    if addr := Geolocation.get_or_none(query=query):
        return addr
    try:
        addr = locator.geocode(query, language='zh')
    except geopy.exc.GeocoderUnavailable:
        time.sleep(1)
        ADDR_NOT_FOUND.append(query)
    if not addr:
        return
    addr = Geolocation.create(
        query=query,
        address=addr.address,
        longitude=addr.longitude,
        latitude=addr.latitude)
    console.log(f'\nwrite geo_info: {addr.query, addr.address}\n')
    sleep(1.0)
    return addr


def get_img_path(path: Path, sort=False):
    media_ext = ('.jpg', '.mov', '.png', '.jpeg', '.mp4', '.gif')
    files = []
    paths = [path] if path.is_file() else path.iterdir()
    for p in paths:
        if any(part.startswith('.') for part in p.parts):
            continue
        elif p.is_file():
            if not p.suffix.lower().endswith(media_ext):
                continue
            files.append(str(p))
        elif p.is_dir():
            yield from get_img_path(p, sort)
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
                to_write[k] = ''
        else:
            to_write[k] = v
    return to_write
