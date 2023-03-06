import itertools
import time
from time import sleep
from typing import Self

import keyring
from geopy import geocoders
from geopy.distance import geodesic
from peewee import DoubleField, Model, TextField
from playhouse.postgres_ext import PostgresqlExtDatabase
from playhouse.shortcuts import model_to_dict

from imgmeta import console


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

    _addr_not_found = set()
    locator = geocoders.GoogleV3(
        api_key=keyring.get_password("google_map", "api_key"))

    @classmethod
    def get_addr(cls, query) -> Self | None:
        if addr := Geolocation.get_or_none(query=query):
            return addr
        elif query in cls._addr_not_found:
            return
        if not (addr := cls.locator.geocode(query, language='zh')):
            cls._addr_not_found.add(query)
            time.sleep(1)
            return
        console.log(f'\nwrite geo_info: {query, addr.address}\n')
        lat, lng = cls.round_loc(addr.latitude, addr.longitude)
        addr = Geolocation.create(
            query=query,
            address=addr.address,
            latitude=lat,
            longitude=lng)
        sleep(1.0)
        return addr

    @staticmethod
    def round_loc(lat, lng, tolerance=0.01):
        for precision in itertools.count(start=1):
            lat_, lng_ = round(lat, precision), round(lng, precision)
            if (err := geodesic((lat, lng), (lat_, lng_)).meters) < tolerance:
                break
        if err:
            console.log(
                f'round loction: {lat, lng} -> {lat_, lng_}'
                f'with precision {precision} (err: {err}m)')
        return lat_, lng_
