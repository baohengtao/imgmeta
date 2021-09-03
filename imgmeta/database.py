from sqlalchemy import ARRAY, Text, Integer, Boolean
import dataset

geo_table = dataset.Database('postgresql://localhost/imgmeta')['geolocation']
