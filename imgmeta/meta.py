import re
from pathlib import Path

import pendulum
import questionary
import sinaspider.exceptions
from insmeta.model import Artist as InstaArtist
from insmeta.model import Insta
from sinaspider.model import Artist as WeiboArtist
from sinaspider.model import Weibo
from twimeta.model import Artist as TwiArtist
from twimeta.model import Twitter

from imgmeta import console
from imgmeta.helper import Geolocation


def gen_xmp_info(meta) -> dict:
    supplier = meta.get('XMP:ImageSupplierName', '')
    user_id = meta.get('XMP:ImageSupplierID')
    unique_id = meta.get('XMP:ImageUniqueID')
    sn = meta.get('XMP:SeriesNumber')
    raw_filename = meta.get('XMP:RawFileName') or meta['File:FileName']
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
                    assert wb.user_id == user_id
            if user_id:
                artist = WeiboArtist.from_id(user_id)
                res |= artist.xmp_info
        case 'instagram':
            from insmeta.model import get_id_from_filename
            if unique_id:
                unique_id = int(unique_id)
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
            user_id = meta.get('XMP:ImageCreatorName')
            if unique_id and (twitter := Twitter.get_or_none(id=unique_id)):
                res |= twitter.gen_meta(sn)
                user_id = twitter.user_id
            if user_id and (artist := TwiArtist.from_id(user_id)):
                res |= artist.xmp_info

    return {k: str(v).strip() for k, v in res.items()}


def rename_single_img(img: Path, meta: dict, new_dir=False, root=None):
    raw_file_name = meta.get('XMP:RawFileName')
    artist = meta.get('XMP:Artist') or meta.get(
        'XMP:ImageCreatorName')
    date = meta.get('XMP:DateCreated', '')
    date = date.removesuffix('+08:00').removesuffix('.000000')
    sn = meta.get('XMP:SeriesNumber')
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
    def __init__(self, meta, prompt=False, time_fix=False):
        self.prompt = prompt
        self.time_fix = time_fix
        self.meta = meta.copy()
        self.filename = meta['File:FileName']
        self.filepath = meta['SourceFile']

    def process_meta(self):
        if xmp_info := gen_xmp_info(self.meta):
            for k, v in xmp_info.items():
                if v == '':
                    assert not self.meta.get(k)
                else:
                    assert v
            xmp_info = {k: v for k, v in xmp_info.items() if v != ''}
            self.meta.update(xmp_info)
        self.write_location()
        self.assign_raw_file_name()

        self.move_meta()
        description = gen_description(self.meta)
        title = gen_title(self.meta)
        self._assign_multi_tag('XMP:Title', 'XMP:Caption', title)
        self._assign_multi_tag(
            'XMP:Description', 'XMP:UserComment', description)
        self.copy_meta()
        self.fix_meta()
        return self.meta

    def assign_raw_file_name(self):
        raw_meta = self.meta.get('XMP:RawFileName')
        filename = self.meta['File:FileName']
        if raw_meta and raw_meta != filename:
            return
        raw_file_name = get_raw_file_name(self.meta)
        self.meta['XMP:RawFileName'] = raw_file_name or filename

    def write_location(self):
        location = self.meta.get('XMP:Location')
        if location == '无':
            location = ''
            self.meta['XMP:Location'] = location
        if not location:
            return
        if not (address := Geolocation.get_addr(location)):
            console.log(
                f'{self.filename}=>Cannot locate {location}', style='warning')
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

    def move_meta(self):
        tuple_tag_to_move = [
            (':BaseURL', 'XMP:BlogURL'),
            (':ImageDescription', 'XMP:Description'),
            ('IPTC:Keywords', 'XMP:Subject'),
            (':Artist', 'XMP:Artist'),
            (':Source', 'XMP:Source'),
            (':UserComment', 'XMP:UserComment'),
            (':ImageUnique', 'XMP:ImageUniqueID'),
            ('EXIF:CreateDate', 'XMP:DateCreated'),
            (':Title', 'XMP:Title'),
            (':Description', 'XMP:Description'),
        ]
        for src_tag, dst_tag in tuple_tag_to_move:
            self.transfer_tag(src_tag, dst_tag)

    def copy_meta(self):
        mp4_tag_to_copy = [
            ('XMP:DateCreated', 'QuickTime:CreateDate'),
            ('XMP:Title', 'QuickTime:Title'),
            ('XMP:Description', 'QuickTime:Description')
        ]
        if self.meta['File:MIMEType'] in ['video/mp4', 'video/quicktime']:
            for src_tag, dst_tag in mp4_tag_to_copy:
                self.transfer_tag(src_tag, dst_tag, is_move=False)

    def fix_meta(self):

        for k, v in self.meta.items():
            assert v is not None
            if v == '无':
                self.meta[k] = ''

    def _assign_multi_tag(self, tag, tag_aux, value):

        v = self.meta.get(tag, '')
        v_aux = self.meta.get(tag_aux, '')
        if v == v_aux == value:
            return
        if v_aux and v != v_aux:
            console.log(
                f"{self.filepath}: found unexpected tag {tag_aux}:{v_aux}",
                style='info')
            if not self.prompt:
                return
            console.log(
                f'[u b]{self.filepath}  {tag_aux}[/u b]: discard {v_aux}?')
            if questionary.confirm('discard or not').unsafe_ask():
                v_aux = ''
            else:
                return
        """
        case 1: v_aux == v:
            case 1.1: value != '' ==> update
            case 1.2 value == ''
        """

        to_update = {tag: value, tag_aux: value}
        if v == v_aux:
            if value:
                self.meta.update(to_update)
            elif self.prompt:
                console.log(
                    f'[u b]{self.filepath}  {tag}[/u b]: discard {v}?')
                if questionary.confirm('discard or not').unsafe_ask():
                    self.meta.update(to_update)
            return

        """
        case 2: v_aux == ''
            case 2.1: v == value ==> update
            case 2.2: v != value
        """

        if v == value:
            self.meta.update(to_update)
            return

        console.log(
            f"{self.filepath}: {tag} {v} not equal {value} "
            f"and no {tag_aux} found.", style='info')
        if self.prompt:
            console.log(
                f'[u b]{self.filepath}  {tag}[/u b]: discard '
                f'[b red]{v}[/b red] and write [b red]{value} ?[/b red]')
            if questionary.confirm('discard or not').unsafe_ask():
                self.meta.update(to_update)

    def transfer_tag(self, src_tag, dst_tag, is_move=True):
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
        src_value = str(src_values.pop())
        dst_value = str(self.meta.get(dst_tag, ''))
        if (dst_value != '' and dst_value != src_value):
            try:
                assert (dst_value and src_value)
                src_value = self._deal_conflict(src_value, dst_value)
            except ValueError as e:
                if 'time' in str(e) and not self.time_fix:
                    return

                console.log(
                    f"{self.filepath}: {src_meta} not equal "
                    f"{dst_tag} {dst_value}", style="info")
                if not self.prompt:
                    return
                console.print(f'[b u]{self.filepath} {dst_tag}[/b u]: '
                              'conflict value found')
                src_value = questionary.select(
                    'which one you want to keep',
                    choices=[src_value, dst_value],
                    use_shortcuts=True).unsafe_ask()
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
            is_same = (t2 - t1).in_seconds() == 0
            is_same |= t2 - t1 == pendulum.duration(hours=8)
            is_same |= (t1.date() == t2.date() and
                        t1.time() == pendulum.time(0, 0, 0))
            if is_same:
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
    description = ' '.join([text, url]).strip()

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
