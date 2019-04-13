import os
import sys
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine

Base = declarative_base()


class Category(Base):
	__tablename__ = 'categories'

	id = Column(Integer, primary_key=True)
	name = Column(String(100), nullable=False)

class Item(Base):
	__tablename__ = 'items'

	id = Column(Integer, primary_key=True)
	category_id = Column(Integer,ForeignKey('categories.id'))
	name = Column(String(100), nullable=False)
	description = Column(String(1000), nullable=False)
	category = relationship(Category)


engine = create_engine('sqlite:///catalog.db')


Base.metadata.create_all(engine)