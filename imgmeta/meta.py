import re
from pathlib import Path

import geopy.distance
import pendulum
import questionary
from aweme.model import Artist as AweArtist
from aweme.model import Post
from insmeta.model import Artist as InstaArtist
from insmeta.model import Insta
from redbook.model import Artist as RedArtist
from redbook.model import Note
from sinaspider.model import Artist as WeiboArtist
from sinaspider.model import Weibo, WeiboMissed
from twimeta.model import Artist as TwiArtist
from twimeta.model import Twitter

from imgmeta import console
from imgmeta.model import Geolocation


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
                from sinaspider.helper import encode_wb_id
                if unique_id.isdigit():
                    unique_id = encode_wb_id(int(unique_id))
                wb = Weibo.get_or_none(
                    bid=unique_id) or WeiboMissed.get_or_none(bid=unique_id)
                if not wb:
                    console.log(f'{unique_id} not found', style='error')
                else:
                    res |= wb.gen_meta(sn)
                    assert wb.user_id == user_id
            if user_id:
                artist = WeiboArtist.from_id(user_id)
                res |= artist.xmp_info
        case 'redbook':
            if unique_id:
                note = Note.get_by_id(unique_id)
                res |= note.gen_meta(sn)
            if user_id:
                artist = RedArtist.from_id(user_id)
                res |= artist.xmp_info

        case 'aweme':
            if unique_id:
                post = Post.from_id(unique_id)
                res |= post.gen_meta(sn)
            if user_id:
                artist = AweArtist.from_id(user_id)
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

    for v in res.values():
        if isinstance(v, str):
            assert v.strip() == v
    if res:
        res['XMP:Subject'] = supplier.lower()

    return res


def rename_single_img(img: Path, meta: dict, new_dir=False,
                      root=None, sep_mp4: bool = True,
                      sep_mov: bool = False,):
    new_dir = new_dir or root or sep_mov or sep_mp4
    raw_file_name = meta.get('XMP:RawFileName')
    artist = meta.get('XMP:Artist') or meta.get(
        'XMP:ImageCreatorName')
    date = meta.get('XMP:DateCreated', '')
    if not all([raw_file_name, artist, date]):
        console.log(img)
        return
    fmt = 'YYYY:MM:DD HH:mm:ss.SSSSSS'
    date = date.removesuffix('+08:00').removesuffix('.000000')
    date = pendulum.from_format(date, fmt=fmt[:len(date)])
    sn = meta.get('XMP:SeriesNumber')
    inc = 0
    mov = None
    if sep_mov:
        assert img.suffix != '.mov'
        if (mov := img.with_suffix('.mov')).exists():
            assert img.suffix == '.jpg'
        else:
            mov = None
    while True:
        filename = f'{artist}-{date:%y-%m-%d-%H%M}'
        filename += f'-{int(sn):d}' if sn else ''
        filename += f'-{inc:02d}' if inc else ''
        if 'edited' in img.name:
            filename += '_edited'
        filename += img.suffix
        if new_dir:
            if mov:
                subfolder = '_mov'
            elif sep_mp4 and filename.endswith('.mp4'):
                subfolder = '_mp4'
            else:
                subfolder = artist
            path = Path(root)/subfolder if root else Path(subfolder)
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
            if mov:
                mov_new = img_new.with_suffix('.mov')
                assert not mov_new.exists()
                mov.rename(mov_new)
            console.log(f'move {img} to {img_new}')
            if inc:
                console.log(f'inc: {inc} is used for {img_new}', style='error')
            break


class ImageMetaUpdate:
    def __init__(self, meta, prompt=False, time_fix=False):
        self.prompt = prompt
        self.time_fix = time_fix
        self.meta = meta.copy()
        self.filename = meta['File:FileName']
        self.filepath = meta['SourceFile']

    def process_meta(self):
        if ',' in self.meta.get('QuickTime:Keywords', ''):
            self.meta['QuickTime:Keywords'] = self.meta[
                'QuickTime:Keywords'].split(',')
        if subj := self.meta.get('XMP:Subject'):
            if isinstance(subj, str):
                subj = {subj}
            else:
                subj = set(subj)
        else:
            subj = set()
        if xmp_info := gen_xmp_info(self.meta):
            for k, v in xmp_info.items():
                if v == '':
                    assert not self.meta.get(k)
                else:
                    assert v
            xmp_info = {k: v for k, v in xmp_info.items() if v != ''}
            subj.add(xmp_info.pop('XMP:Subject'))

            self.meta.update(xmp_info)
        self.move_meta()
        if subj:
            self.meta['XMP:Subject'] = sorted(subj)
        self.write_location()

        self.assign_raw_file_name()
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
        subject = self.meta.get('XMP:Subject', [])
        assert isinstance(subject, list)
        subject = set(subject)
        if subject:
            subject -= {'NoInstagramLocation', 'NoWeiboLocation'}
            self.meta['XMP:Subject'] = sorted(subject)

        if lat_lng := self.meta.pop('InstagramLocation', None):
            if lat_lng == 'not_found':
                if 'XMP:Location' in self.meta:
                    self.meta['XMP:Location'] = ''
                return
            lat, lng = lat_lng
            if lat is None:
                subject.add('NoInstagramLocation')
                self.meta['XMP:Subject'] = sorted(subject)
                return
        elif lat_lng := self.meta.pop('WeiboLocation', None):
            lat, lng = lat_lng
            if lat is None:
                subject.add('NoWeiboLocation')
                self.meta['XMP:Subject'] = sorted(subject)
                return
        elif lat_lng := self.meta.pop('AwemeLocation', None):
            lat, lng = lat_lng
            assert lat is not None
        else:
            if not (location := self.meta.get('XMP:Location')):
                return
            else:
                console.log(
                    f'has locaiton but no latlng: {location}', style='error')
                return
                assert False
            if not (addr := Geolocation.get_addr(location)):
                city, *_ = location.split('·', maxsplit=1)
                if not (addr := Geolocation.get_addr(city)):
                    console.log(
                        f'{self.filepath}=>Cannot locate {location}', style='warning')
                    return
            lat, lng = addr.latitude, addr.longitude
        composite = self.meta.get('Composite:GPSPosition')
        geography = self.meta.get('XMP:Geography')
        if composite:
            if not geography:
                return
            if (dist := geopy.distance.distance(composite, geography).km) > 1:
                console.log(
                    f'{self.filepath}: distance between {composite} and {geography} is {dist}km',
                    style='warning')
                return
        if 'Keys:GPSCoordinates' in self.meta:
            if self.meta['Keys:GPSCoordinates'] == self.meta.get('XMP:Geography', ''):
                self.meta['Keys:GPSCoordinates'] = ''
        self.meta['XMP:GPSLatitude'] = lat
        self.meta['XMP:GPSLongitude'] = lng
        self.meta['XMP:Geography'] = f'{lat} {lng}'

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
            ('XMP:CreateDate', 'XMP:DateCreated'),
            ('QuickTime:CreateDate', 'XMP:DateCreated'),
            (':Title', 'XMP:Title'),
            (':Description', 'XMP:Description'),
            # ('Keys:GPSCoordinates', 'XMP:Geography'),
            ('QuickTime:Keywords', 'XMP:Subject')
        ]
        for src_tag, dst_tag in tuple_tag_to_move:
            self.transfer_tag(src_tag, dst_tag)

    def copy_meta(self):
        mp4_tag_to_copy = [
            ('XMP:DateCreated', 'QuickTime:CreateDate'),
            ('XMP:Title', 'QuickTime:Title'),
            ('XMP:Description', 'QuickTime:Description'),
            ('XMP:Geography', 'Keys:GPSCoordinates'),
            ('XMP:Subject', 'QuickTime:Keywords')
        ]
        if self.meta['File:MIMEType'] in ['video/mp4', 'video/quicktime']:
            for src_tag, dst_tag in mp4_tag_to_copy:
                self.transfer_tag(src_tag, dst_tag, is_move=False)
            create_date = self.meta['QuickTime:CreateDate']
            if create_date == self.meta['XMP:DateCreated']:
                assert not create_date.endswith('+08:00')
                create_date = pendulum.parse(
                    create_date, tz='local').in_tz('UTC')
                self.meta['QuickTime:CreateDate'] = create_date.format(
                    'YYYY:MM:DD HH:mm:ss')

    def fix_meta(self):

        for k, v in self.meta.items():
            assert v is not None
            if v == '无':
                self.meta[k] = ''
        if keywords := self.meta.get('QuickTime:Keywords'):
            if isinstance(keywords, list):
                self.meta['QuickTime:Keywords'] = ','.join(keywords)
        if len(subj := self.meta.get('XMP:Subject') or []) == 1:
            self.meta['XMP:Subject'] = subj.pop()

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
        src_meta = {k:  v if isinstance(v, list) else str(v) for k, v in
                    self.meta.items() if k.endswith(src_tag)
                    and k != dst_tag and v != ''}
        if not (src_values := list(src_meta.values())):
            return
        src_value = src_values[0]
        for v in src_values[1:]:
            if v != src_value:
                console.log(
                    f"{self.filepath}: Multi values of src_meta "
                    f"=> {src_meta}", style='warning')
                return
        dst_value = self.meta.get(dst_tag, '')
        dst_value = dst_value if isinstance(dst_value, list) else str(
            dst_value)
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
    fmt = "YYYY:MM:DD HH:mm:ss"
    time = pendulum.from_format(time[:len(fmt)], fmt)
    if sn:
        title = f'{artist}-{time:%y-%m-%d-%H%M}-{sn}'
    else:
        title = f'{artist}-{time:%y-%m-%d}'
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
