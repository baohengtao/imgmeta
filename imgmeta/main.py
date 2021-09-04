import exiftool
from tqdm import tqdm

from imgmeta.helper import get_img_path, diff_meta, sort_img_path, update_single_img
from imgmeta.meta import ImageMetaUpdate, rename_single_img, gen_weibo_xmp_info


class Main:
    def __init__(self, img_path):
        self.et = exiftool.ExifTool()
        imgs = get_img_path(img_path)
        self.imgs = list(sort_img_path(imgs))

    def xmp_writer(self, func):
        self.et.start()
        for img in tqdm(self.imgs):
            meta = self.et.get_metadata(img)
            xmp_info = func(meta)
            to_write = diff_meta(xmp_info, meta)
            update_single_img(img, to_write, self.et)
        self.et.terminate()

    def rename_img(self):
        self.et.start()
        for img in tqdm(self.imgs):
            rename_single_img(img, self.et, new_dir=True)
        self.et.terminate()

    def write_weibo(self):
        self.xmp_writer(gen_weibo_xmp_info)

    def meta_update(self):
        self.xmp_writer(lambda meta: ImageMetaUpdate(meta).meta)
