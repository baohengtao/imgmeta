import sys
sys.path.insert(1, '/Users/htao/package/sinaspider')
from tqdm import tqdm
from photoscript import PhotosLibrary
from osxphotos import PhotosDB

columns = [
    'Artist',
    'ImageCreatorName', 
    'ImageCreatorID', 
    'ImageSupplierID', 
    'ImageSupplierName',
    'ImageUniqueID', 
    'SeriesNumber',  
    'DateCreated', 
    'BlogTitle', 
    'BlogURL', 
    'uuid'
    ]


def create_table():
    import dataset
    database_url = 'postgresql://localhost/imgmeta'
    pg = dataset.connect(database_url)
    table = pg.create_table(
        table_name='photos',
        primary_id='uuid',
        primary_increment=False,
        primary_type=pg.types.text)
    return table


def write_table():
    table = create_table()
    photos = PhotosDB().photos()
    for p in tqdm(photos):
        xmp = p.exiftool.asdict()
        meta = xmp2meta(xmp)
        meta['uuid'] = p.uuid
        table.upsert(meta, ['uuid'])
    
def update_table(a=1):
    table = create_table()
    pd = PhotosDB()
    for p in tqdm(pd.photos()):
        if not table.find_one(uuid=p.uuid):
            xmp = p.exiftool.asdict()
            meta = xmp2meta(xmp)
            meta['uuid'] = p.uuid
            table.insert(meta, ['uuid'])
    for row in tqdm(table):
        uuid = row['uuid']
        if not pd.get_photo(uuid):
            print(f'delete {uuid}')
            table.delete(uuid=row['uuid'])
        
        
    



def read_table():
    uuids = []
    table=create_table()
    for row in table.all():
        if (blog_url := row['BlogURL']):
            assert row['ImageUniqueID']

def create_albums(uuids):
    pl=PhotosLibrary()
    photos=pl.photos(uuid=uuids)
    pl.create_album('prob').add(photos)
    


def xmp2meta(xmp):
    meta = dict()
    for c in columns:
        if v:=xmp.get('XMP:'+c):
            meta[c]=str(v)
    return meta
