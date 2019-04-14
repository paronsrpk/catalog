from flask import Flask, render_template, url_for, request, redirect, flash, jsonify
from flask import make_response
from flask import session as login_session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Category, Item, User
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import datetime
import random
import string
import httplib2
import json
import requests

app = Flask(__name__)

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Catalog Application"

engine = create_engine('sqlite:///catalog.db')
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)


# Create anti-forgery state token
@app.route('/login/')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    return render_template('login.html', STATE=state, CLIENT_ID=CLIENT_ID)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is already connected.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    if getUserID(login_session['email']) is None:
        login_session['user_id'] = createUser(login_session)
    else:
        login_session['user_id'] = getUserID(login_session['email'])

    output = ''
    output += '<h1>Welcome, '
    output += login_session['email']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % login_session['email'])
    print "done!"
    return output


# User Helper Functions


def createUser(login_session):
	session = DBSession()
	newUser = User(email=login_session['email'], ctime=datetime.datetime.now())
	session.add(newUser)
	session.commit()
	user = session.query(User).filter_by(email=login_session['email']).one()
	session.close()
	return user.id

def getUserInfo(user_id):
	session = DBSession()
	user = session.query(User).filter_by(id=user_id).one()
	session.close()
	return user

def getUserID(email):
	try:
		session = DBSession()
		user = session.query(User).filter_by(email=email).one()
		session.close()
		return user.id
	except:
		return None


@app.route('/gdisconnect/')
def gdisconnect():
    access_token = login_session.get('access_token')
    if access_token is None:
        print 'Access Token is None'
        response = make_response(json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    print 'In gdisconnect access token is %s', access_token
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % login_session['access_token']
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    print 'result is '
    print result
    if result['status'] == '200':
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['user_id']
        del login_session['email']
        del login_session['picture']
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        response = make_response(json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


@app.route('/categories/JSON/')
def categoriesJSON():
	session = DBSession()
	categories = session.query(Category).all()
	session.close()
	return jsonify(Categories=[c.serialize for c in categories])

@app.route('/items/JSON/')
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
	if 'user_id' not in login_session or login_session['user_id'] != item.user_id:
		return render_template("showitemdetailspublic.html", item=item)
	else:
		return render_template("showitemdetails.html", item=item)

@app.route('/category/<int:category_id>/items/new/', methods=['GET','POST'])
def newItem(category_id):
	if 'email' not in login_session:
		return redirect('/login')
	if request.method == 'POST':
		now = datetime.datetime.now()
		newItem = Item(category_id=category_id,name=request.form['name'], description=request.form['description'], ctime=now, 
			mtime=now, user_id=login_session['user_id'])
		session = DBSession()
		session.add(newItem)
		session.commit()
		session.close()
		flash("New item has been created")
		return redirect(url_for('showCategoryItems', category_id=category_id))
	else:
		session = DBSession()
		category = session.query(Category).filter_by(id=category_id).one()
		session.close()
		return render_template("newitem.html", category=category)

@app.route('/category/<int:category_id>/items/<int:item_id>/edit/', methods=['GET','POST'])
def editItem(category_id,item_id):
	if 'email' not in login_session:
		return redirect('/login')
	if request.method == 'POST':
		session = DBSession()
		editedItem =  session.query(Item).filter_by(category_id=category_id, id=item_id).one()
		editedItem.name = request.form['name']
		editedItem.description = request.form['description']
		editedItem.mtime = datetime.datetime.now()
		session.add(editedItem)
		session.commit()
		session.close()
		flash("Item has been edited")
		return redirect(url_for('showCategoryItems', category_id=category_id))
	else:
		session = DBSession()
		item = session.query(Item).filter_by(category_id=category_id, id=item_id).one()
		session.close()
		return render_template("edititem.html", item=item)

@app.route('/category/<int:category_id>/items/<int:item_id>/delete/', methods=['GET','POST'])
def deleteItem(category_id,item_id):
	if 'email' not in login_session:
		return redirect('/login')
	if request.method == 'POST':
		session = DBSession()
		deletedItem = session.query(Item).filter_by(id=item_id).one()
		session.delete(deletedItem)
		session.commit()
		session.close()
		flash("Item has been deleted")
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