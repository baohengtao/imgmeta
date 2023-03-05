import time
from collections import defaultdict
from pathlib import Path
from time import sleep
from typing import Iterator, Self

import geopy
import keyring
from exiftool import ExifToolHelper
from geopy import geocoders
from peewee import DoubleField, Model, TextField
from playhouse.postgres_ext import PostgresqlExtDatabase
from playhouse.shortcuts import model_to_dict

from imgmeta import console

# geo_table = DataSet('postgresql://localhost/imgmeta')['geolocation']


class BaseModel(Model):
    class Meta:
        database = PostgresqlExtDatabase(
            'imgmeta', host='localhost', autorollback=True)

    def __str__(self):
        model = model_to_dict(self, recurse=False)
        return "\n".join(f'{k}: {v}' for k, v in model.items() if v is not None)


class Geolocation(BaseModel):
    query = TextField(primary_key=True)
    address = TextField()
    longitude = DoubleField()
    latitude = DoubleField()

    _addr_not_found = []
    locator = geocoders.GoogleV3(
        api_key=keyring.get_password("google_map", "api_key"))

    @classmethod
    def get_addr(cls, query) -> Self | None:
        if addr := Geolocation.get_or_none(query=query):
            return addr
        elif query in cls._addr_not_found:
            return
        try:
            addr = cls.locator.geocode(query, language='zh')
            assert addr
        except (geopy.exc.GeocoderUnavailable, AssertionError):
            time.sleep(1)
            cls._addr_not_found.append(query)
            return
        addr = Geolocation.create(
            query=query,
            address=addr.address,
            longitude=addr.longitude,
            latitude=addr.latitude)
        console.log(f'\nwrite geo_info: {addr.query, addr.address}\n')
        sleep(1.0)
        return addr


def get_img_path(path: Path, sort=False, skip_dir=None) -> Iterator[Path]:
    media_ext = ('.jpg', '.mov', '.png', '.jpeg', '.mp4', '.gif')
    files = []
    paths = [path] if path.is_file() else path.iterdir()
    for p in paths:
        if any(part.startswith('.') for part in p.parts):
            continue
        elif p.is_file():
            if not p.suffix.lower().endswith(media_ext):
                continue
            files.append(p)
        elif p.is_dir():
            if skip_dir and skip_dir in p.stem:
                continue
            yield from get_img_path(p, sort)
    if sort:
        yield from _sort_img(files)
    else:
        yield from files


def _sort_img(imgs: list[Path]) -> Iterator[Path]:
    with ExifToolHelper() as et:
        tags = et.get_tags(imgs, 'XMP:ImageUniqueID') if imgs else []
    imgs_dict = defaultdict(list)
    for tag in tags:
        imgs_dict[tag.get('XMP:ImageUniqueID')].append(tag['SourceFile'])
    for value in sorted(imgs_dict.values(), key=lambda x: -len(x)):
        for img in sorted(value):
            yield Path(img)


def diff_meta(modified: dict, original: dict):
    assert set(modified).issuperset(original)
    to_write = {}
    for k, v in modified.items():
        if k in original and str(v) == str(original[k]):
            continue
        assert k in original or v
        to_write[k] = v
    return to_write


def show_diff(modified: dict, original: dict):
    assert set(modified).issuperset(original)
    for k, v in modified.items():
        if k in original and str(v) == str(original[k]):
            continue
        assert k in original or v
        if v != '':
            console.log(f'+{k}: {v}', style='green')
        if k in original:
            console.log(f'-{k}: {original[k]}', style='red')
