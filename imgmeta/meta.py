import re
from pathlib import Path

import pendulum
from sinaspider.model import Weibo, Artist as WeiboArtist
from twimeta.model import Twitter, Artist as TwiArtist
from insmeta.model import Insta, Artist as InstaArtist
from imgmeta import console
from imgmeta.helper import get_addr
import sinaspider.exceptions


def gen_xmp_info(meta) -> dict:
    supplier = meta.get('XMP:ImageSupplierName', '')
    user_id = meta.get('XMP:ImageSupplierID')
    unique_id = meta.get('XMP:ImageUniqueID')
    sn = meta.get('XMP:SeriesNumber')
    raw_filename = meta.get('XMP:RawFileName', '')
    res = {}
    match supplier.lower():
        case 'weibo':
            if unique_id:
                try:
                    wb = Weibo.from_id(unique_id)
                except sinaspider.exceptions.WeiboNotFoundError as e:
                    console.log(f"{meta['File:FileName']}=>{unique_id}:{e}")
                else:
                    res |= wb.gen_meta(sn)
            if user_id:
                artist = WeiboArtist.from_id(user_id)
                res |= artist.xmp_info
        case 'instagram':
            from insmeta.model import (
                get_id_from_filename, normalize_ins_id)
            if unique_id:
                unique_id = normalize_ins_id(unique_id)
                assert user_id
            if user_id:
                user_id = int(user_id)
            if ids := get_id_from_filename(raw_filename):
                assert not unique_id or unique_id == ids[0]
                assert not user_id or user_id == ids[1]
                unique_id, user_id = ids
            if unique_id:
                res |= Insta.from_id(unique_id, user_id).meta
            if user_id:
                res |= InstaArtist.from_id(user_id).meta

        case 'twitter':
            if user_text_id := meta.get('XMP:ImageCreatorName'):
                if artist := TwiArtist.from_id(user_text_id):
                    res |= artist.xmp_info
            if unique_id and (twitter := Twitter.get_or_none(id=unique_id)):
                res |= twitter.gen_meta(sn)

    return res


def rename_single_img(img, et, new_dir=False, root=None):
    img = Path(img)
    raw_file_name = et.get_tag('XMP:RawFileName', str(img))
    artist = et.get_tag('XMP:Artist', str(img)) or et.get_tag(
        'XMP:ImageCreatorName', str(img))
    artist = str(artist)
    date = et.get_tag('XMP:DateCreated', str(img)) or ''
    date = date.removesuffix('+08:00').removesuffix('.000000')
    sn = et.get_tag('XMP:SeriesNumber', str(img))
    if not all([raw_file_name, artist, date]):
        console.log(img)
        return
    fmt = 'YYYY:MM:DD HH:mm:ss.SSSSSS'
    date = pendulum.from_format(date, fmt=fmt[:len(date)])
    inc = 0
    while True:
        filename = f'{artist}-{date:%y-%m-%d}'
        filename += f'-{inc:02d}' if inc else ''
        filename += f'-{int(sn):d}' if sn else ''
        filename += img.suffix
        if new_dir:
            path = Path(root)/artist if root else Path(artist)
            path.mkdir(exist_ok=True, parents=True)
        else:
            path = img.parent
        img_new = path / filename

        if img_new == img:
            break
        elif img_new.exists():
            inc += 1
        else:
            img.rename(img_new)
            console.log(f'move {img} to {img_new}')
            break


class ImageMetaUpdate:
    def __init__(self, meta):
        self.meta = meta.copy()
        self.filename = meta['File:FileName']
        while True:
            original = self.meta.copy()
            self.loop()
            if original == self.meta:
                break

    def loop(self):
        self.fix_meta()
        description = gen_description(self.meta)
        title = gen_title(self.meta)
        self._assign_multi_tag('XMP:Title', 'XMP:Caption', title)
        self._assign_multi_tag(
            'XMP:Description', 'XMP:UserComment', description)
        self.write_location()
        self.assign_raw_file_name()
        if xmp_info := gen_xmp_info(self.meta):
            self.meta.update(xmp_info)

    def assign_raw_file_name(self):
        raw_meta = self.meta.get('XMP:RawFileName')
        filename = self.meta['File:FileName']
        if raw_meta and raw_meta != filename:
            return
        if raw_file_name := get_raw_file_name(self.meta):
            self.meta['XMP:RawFileName'] = raw_file_name

    def _gen_location(self):
        location = self.meta.get('XMP:Location')
        if location == '无':
            location = ''
            self.meta['XMP:Location'] = location
        if not location:
            return
        address = get_addr(location)
        if not address:
            console.log(
                f'{self.filename}=>Cannot locate {location}', style='warning')
        return address

    def write_location(self):
        if not (address := self._gen_location()):
            return
        composite = self.meta.get('Composite:GPSPosition')
        geography = self.meta.get('XMP:Geography')
        if composite:
            if not geography:
                return
            com = [float(x) for x in composite.split()]
            geo = [float(x) for x in geography.split()]
            for x, y in zip(com, geo):
                if x - y > 1e-9:
                    console.log(
                        f'{self.filename}:composite {composite} not eq'
                        f'geography {geography}', style='warning')
                    return
        latitude = f"{address.latitude:.7f}"
        longitude = f"{address.longitude:.7f}"
        latitude, longitude = float(latitude), float(longitude)
        self.meta['XMP:GPSLatitude'] = latitude
        self.meta['XMP:GPSLongitude'] = longitude
        self.meta['XMP:Geography'] = f'{latitude} {longitude}'

    def fix_meta(self):
        tuple_tag_to_move = [
            (':BaseURL', 'XMP:BlogURL'),
            (':ImageDescription', 'XMP:Description'),
            ('IPTC:Keywords', 'XMP:Subject'),
            (':Artist', 'XMP:Artist'),
            (':Source', 'XMP:Source'),
            (':ImageUnique', 'XMP:ImageUniqueID'),
            ('EXIF:CreateDate', 'XMP:DateCreated'),
        ]

        for src_tag, dst_tag in tuple_tag_to_move:
            self.transfer_tag(src_tag, dst_tag)

        self.transfer_tag('File:FileName', 'XMP:RawFileName', diff_print=False, is_move=False)
        if self.meta['File:MIMEType'] in ['video/mp4', 'video/quicktime']:
            self.transfer_tag('XMP:DateCreated',
                              'QuickTime:CreateDate', is_move=False)
            self.transfer_tag('XMP:Title', 'QuickTime:Title',
                              diff_ignore=True, is_move=False)
            self.transfer_tag('XMP:Description',
                              'QuickTime:Description', 
                              diff_ignore=True, is_move=False)

        for k, v in self.meta.items():
            if str(v) in ['None', '无']:
                self.meta[k] = ''

    def _assign_multi_tag(self, tag, tag_aux, value):
        v = self.meta.get(tag, '')
        v_aux = self.meta.get(tag_aux, '')
        if v and v != v_aux:
            console.log(
                f"{self.filename}=>> > {tag}: {v}"
                f" not equal {tag_aux}: {v_aux}", style='info')
        else:
            self.meta[tag] = value
            self.meta[tag_aux] = value

    

    def transfer_tag(self, src_tag, dst_tag,
                     is_move=True, diff_print=True, diff_ignore=False):
        assert (src_tag != dst_tag)
        src_meta = {k: v for k, v in self.meta.items(
        ) if k.endswith(src_tag) and k != dst_tag and v != ''}
        if not (src_values := set(src_meta.values())):
            return
        if len(src_values) > 1:
            console.log(
                f"{self.meta.get('SourceFile')}: Multi values of src_meta "
                f"=> {src_meta}", style='warning')
            return
        src_value = src_values.pop()
        dst_value = self.meta.get(dst_tag, '')
        if (dst_value != '' and dst_value != src_value
                and not diff_ignore):
            try:
                assert isinstance(dst_value, str)
                assert isinstance(src_value, str)
                assert (dst_value and src_value)
                src_value = self._deal_conflict(src_value, dst_value)
            except ValueError as e:
                if diff_print:
                    console.log(e)
                    console.log(
                        f"{self.meta.get('SourceFile')}: Values not same =>"
                        f"src_meta:{src_meta},dst_meta =>{dst_tag}:{dst_value}",
                        style='warning')
                return
        dst_update = {dst_tag: src_value}

        if is_move:
            dst_update |= {k: '' for k in src_meta}
        self.meta.update(dst_update)

    @staticmethod
    def _deal_conflict(src_value: str, dst_value: str):
        t1, t2 = sorted([src_value, dst_value])
        # re_time = re.compile(r'\d{4}:\d{2}:\d{2}( \d{2}:\d{2}:\d{2})*')
        re_time = re.compile(r'^\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}')
        if not re_time.match(t1):
            raise ValueError(f'Conflict value: {t1} {t2}')
        else:
            assert re_time.match(t2)
            t1 = t1.removesuffix('+08:00')
            t2 = t2.removesuffix('+08:00')
            if t1 == '0000:00:00 00:00:00':
                return t2
            t1, t2 = pendulum.parse(t1), pendulum.parse(t2)
            if (t1 - t2).in_seconds() == 0 or t1 - t2 == pendulum.duration(hours=8):
                return t2.strftime('%Y:%m:%d %H:%M:%S')
            elif t1.date() == t2.date() and t1.time() == pendulum.time(0, 0, 0):
                return t2.strftime('%Y:%m:%d %H:%M:%S')
            else:
                raise ValueError(f'Conflict time: {t1} {t2}')


def gen_title(meta):
    artist = meta.get('XMP:Artist') or meta.get('XMP:ImageSupplierName')
    time = meta.get('XMP:DateCreated')
    sn = meta.get('XMP:SeriesNumber')
    if not artist:
        return ''
    if not time:
        return artist
    time = re.split('[: ]', time)
    year, month, day, *_ = time
    year = year[-2:]
    title = '-'.join([artist, year, month, day])
    if sn:
        title = f'{title}-{sn}'
    return title


def gen_description(meta):
    url = meta.get('XMP:BlogURL', '') or meta.get('XMP:ImageCreatorID', '')
    text = meta.get('XMP:BlogTitle', '')
    description = '  '.join(str(x).replace('\n', '\t')
                            for x in [text, url] if x)

    return description


def get_raw_file_name(meta):
    image_supplier_name = meta.get('XMP:ImageSupplierName')
    image_unique_id = meta.get('XMP:ImageUniqueID')
    image_supplier_id = meta.get('XMP:ImageSupplierID')
    sn = meta.get('XMP:SeriesNumber')
    ext = meta.get('File:FileTypeExtension').lower()
    if not image_unique_id:
        return
    if image_supplier_name == 'Weibo':
        raw_file_name = f'{image_supplier_id}_{image_unique_id}'
        raw_file_name += f'_{sn}.{ext}' if sn else f'.{ext}'
        return raw_file_name
