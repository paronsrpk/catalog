import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Item, Category, User
import datetime
import pytz


df_items = pd.read_excel('data/items.xlsx')
df_categories = pd.read_excel('data/categories.xlsx')
df_users = pd.read_excel('data/users.xlsx')

now = datetime.datetime.now(pytz.utc)
df_users['ctime'] = now
df_items['ctime'] = now
df_items['mtime'] = now

engine = create_engine('sqlite:///catalog.db')
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)
session = DBSession()
session.bulk_insert_mappings(Item, df_items.to_dict(orient="records"))
session.bulk_insert_mappings(Category, df_categories.to_dict(orient="records"))
session.bulk_insert_mappings(User, df_users.to_dict(orient="records"))

session.commit()
session.close()
