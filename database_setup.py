import os
import sys
from sqlalchemy import Column, ForeignKey, Integer, String, DATETIME
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine

Base = declarative_base()


class Category(Base):
	__tablename__ = 'categories'

	id = Column(Integer, primary_key=True)
	name = Column(String(100))

	@property
	def serialize(self):
		return {
			'id': self.id,
			'name': self.name
		}

class Item(Base):
	__tablename__ = 'items'

	id = Column(Integer, primary_key=True)
	category_id = Column(Integer,ForeignKey('categories.id'))
	name = Column(String(100))
	description = Column(String(1000))
	ctime = Column(DATETIME, nullable=False)
	mtime = Column(DATETIME, nullable=False)
	category = relationship(Category)

	@property
	def serialize(self):
		return {
			'id': self.id,
			'category_id': self.category_id,
			'name': self.name,
			'description': self.description,
			'ctime': self.ctime.strftime("%d-%m-%Y %H:%M"),
			'mtime': self.mtime.strftime("%d-%m-%Y %H:%M")
		}


engine = create_engine('sqlite:///catalog.db')


Base.metadata.create_all(engine)