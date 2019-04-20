import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Item, Category, User
import datetime
import pytz
from config import DATABASE_URI


df_items = pd.read_excel('data/items.xlsx')
df_categories = pd.read_excel('data/categories.xlsx')
df_users = pd.read_excel('data/users.xlsx')

now = datetime.datetime.now(pytz.utc)
df_users['ctime'] = now
df_items['ctime'] = now
df_items['mtime'] = now

# engine = create_engine('sqlite:///catalog.db')
engine = create_engine(DATABASE_URI)

Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)
session = DBSession()
session.bulk_insert_mappings(User, df_users.to_dict(orient="records"))
session.bulk_insert_mappings(Category, df_categories.to_dict(orient="records"))
session.bulk_insert_mappings(Item, df_items.to_dict(orient="records"))


session.commit()
session.close()

# Resync primary key fields in Postgres
with engine.connect() as con:
	con.execute("SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));")
	con.execute("SELECT setval('categories_id_seq', (SELECT MAX(id) FROM categories));")
	con.execute("SELECT setval('items_id_seq', (SELECT MAX(id) FROM items));")
