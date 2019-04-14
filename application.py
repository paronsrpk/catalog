from flask import Flask, render_template, url_for, request, redirect, flash, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Category, Item
import datetime

app = Flask(__name__)

engine = create_engine('sqlite:///catalog.db')
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)


@app.route('/categories/JSON')
def categoriesJSON():
	session = DBSession()
	categories = session.query(Category).all()
	session.close()
	return jsonify(Categories=[c.serialize for c in categories])

@app.route('/items/JSON')
def ItemsJSON():
	session = DBSession()
	items = session.query(Item).all()
	session.close()
	return jsonify(Items=[i.serialize for i in items])

@app.route('/')
@app.route('/categories/')
def showLatestItems():
	session = DBSession()
	categories = session.query(Category).all()
	items = session.query(Item).order_by(Item.ctime.desc())[0:10]
	session.close()
	return render_template("showlatestitems.html", categories=categories, items=items)

@app.route('/category/<int:category_id>/')
@app.route('/category/<int:category_id>/items/')
def showCategoryItems(category_id):
	session = DBSession()
	categories = session.query(Category).all()
	category = session.query(Category).filter_by(id=category_id).one()
	items = session.query(Item).filter_by(category_id=category_id).all()
	session.close()
	return render_template("showcategoryitems.html", categories=categories, category=category, items=items)

@app.route('/category/<int:category_id>/items/<int:item_id>/')
def showItemDetails(category_id,item_id):
	session = DBSession()
	item = session.query(Item).filter_by(category_id=category_id, id=item_id).one()
	session.close()
	return render_template("showitemdetails.html", item=item)

@app.route('/category/<int:category_id>/items/new/', methods=['GET','POST'])
def newItem(category_id):
	if request.method == 'POST':
		now = datetime.datetime.now()
		newItem = Item(category_id=category_id,name=request.form['name'], description=request.form['description'], ctime=now, mtime=now)
		session = DBSession()
		session.add(newItem)
		session.commit()
		session.close()
		return redirect(url_for('showCategoryItems', category_id=category_id))
	else:
		session = DBSession()
		category = session.query(Category).filter_by(id=category_id).one()
		session.close()
		return render_template("newitem.html", category=category)

@app.route('/category/<int:category_id>/items/<int:item_id>/edit', methods=['GET','POST'])
def editItem(category_id,item_id):
	if request.method == 'POST':
		session = DBSession()
		editedItem =  session.query(Item).filter_by(category_id=category_id, id=item_id).one()
		editedItem.name = request.form['name']
		editedItem.description = request.form['description']
		editedItem.mtime = datetime.datetime.now()
		session.add(editedItem)
		session.commit()
		session.close()
		return redirect(url_for('showCategoryItems', category_id=category_id))
	else:
		session = DBSession()
		item = session.query(Item).filter_by(category_id=category_id, id=item_id).one()
		session.close()
		return render_template("edititem.html", item=item)

@app.route('/category/<int:category_id>/items/<int:item_id>/delete', methods=['GET','POST'])
def deleteItem(category_id,item_id):
	if request.method == 'POST':
		session = DBSession()
		deletedItem = session.query(Item).filter_by(id=item_id).one()
		session.delete(deletedItem)
		session.commit()
		session.close()
		return redirect(url_for('showCategoryItems', category_id=category_id))
	else:
		session = DBSession()
		item = session.query(Item).filter_by(category_id=category_id, id=item_id).one()
		session.close()
		return render_template("deleteitem.html", item=item)


if __name__ == '__main__':
	app.secret_key = 'super_secret_key'
	app.debug = True
	app.run(host='0.0.0.0', port=5000)