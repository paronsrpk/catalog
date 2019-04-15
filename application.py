from flask import Flask, render_template, url_for
from flask import request, redirect, flash, jsonify, g
from flask import make_response
from flask import session as login_session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Category, Item, User
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import datetime
import time
import random
import string
import httplib2
import json
import requests
from redis import Redis
from functools import update_wrapper


app = Flask(__name__)
redis = Redis()

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
FB_APP_ID = json.loads(open('fb_client_secrets.json', 'r').read(
    ))['web']['app_id']
APPLICATION_NAME = "Catalog Application"

engine = create_engine('sqlite:///catalog.db')
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)


class RateLimit(object):
    expiration_window = 10

    def __init__(self, key_prefix, limit, per, send_x_headers):
        self.reset = (int(time.time()) // per) * per + per
        self.key = key_prefix + str(self.reset)
        self.limit = limit
        self.per = per
        self.send_x_headers = send_x_headers
        p = redis.pipeline()
        p.incr(self.key)
        p.expireat(self.key, self.reset + self.expiration_window)
        self.current = min(p.execute()[0], limit)

    remaining = property(lambda x: x.limit - x.current)
    over_limit = property(lambda x: x.current >= x.limit)


def get_view_rate_limit():
    return getattr(g, '_view_rate_limit', None)


def on_over_limit(limit):
    return (jsonify({'data': 'You hit the rate limit', 'error': '429'}), 429)


# Limit number of times a user can request through API
def ratelimit(limit, per=300, send_x_headers=True,
              over_limit=on_over_limit,
              scope_func=lambda: request.remote_addr,
              key_func=lambda: request.endpoint):
    def decorator(f):
        def rate_limited(*args, **kwargs):
            key = 'rate-limit/%s/%s/' % (key_func(), scope_func())
            rlimit = RateLimit(key, limit, per, send_x_headers)
            g._view_rate_limit = rlimit
            if over_limit is not None and rlimit.over_limit:
                return over_limit(rlimit)
            return f(*args, **kwargs)
        return update_wrapper(rate_limited, f)
    return decorator


@app.after_request
def inject_x_rate_headers(response):
    limit = get_view_rate_limit()
    if limit and limit.send_x_headers:
        h = response.headers
        h.add('X-RateLimit-Remaining', str(limit.remaining))
        h.add('X-RateLimit-Limit', str(limit.limit))
        h.add('X-RateLimit-Reset', str(limit.reset))
    return response


# Create anti-forgery state token
@app.route('/login/')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    return render_template(
        'login.html', STATE=state, CLIENT_ID=CLIENT_ID, FB_APP_ID=FB_APP_ID)


@app.route('/fbconnect', methods=['POST'])
def fbconnect():
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    access_token = request.data
    print "access token received %s " % access_token
    app_id = json.loads(open('fb_client_secrets.json', 'r').read())[
        'web']['app_id']
    app_secret = json.loads(
        open('fb_client_secrets.json', 'r').read())['web']['app_secret']
    url = 'https://graph.facebook.com/oauth/access_token?' \
        'grant_type=fb_exchange_token&client_id=%s&client_secret=%s&' \
        'fb_exchange_token=%s' % (
            app_id, app_secret, access_token)
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]

    # Use token to get user info from API
    userinfo_url = "https://graph.facebook.com/v2.8/me"
    token = result.split(',')[0].split(':')[1].replace('"', '')
    url = 'https://graph.facebook.com/v2.8/me?' \
        'access_token=%s&fields=name,id,email' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)
    login_session['provider'] = 'facebook'
    login_session['username'] = data["name"]
    login_session['email'] = data["email"]
    login_session['facebook_id'] = data["id"]

    # The token must be stored in the login_session in order to properly logout
    login_session['access_token'] = token

    # Get user picture
    url = 'https://graph.facebook.com/v2.8/me/picture?' \
        'access_token=%s&redirect=0&height=200&width=200' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)

    login_session['picture'] = data["data"]["url"]

    # see if user exists
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']

    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;' \
        '-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '

    flash("Now logged in as %s" % login_session['email'])
    return output


@app.route('/fbdisconnect')
def fbdisconnect():
    facebook_id = login_session['facebook_id']
    # The access token must me included to successfully logout
    access_token = login_session['access_token']
    url = 'https://graph.facebook.com/%s/permissions?access_token=%s' % (
        facebook_id, access_token)
    h = httplib2.Http()
    result = h.request(url, 'DELETE')[1]
    return "you have been logged out"


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
        response = make_response(json.dumps(
            'Current user is already connected.'), 200)
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

    login_session['provider'] = 'google'
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
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;' \
        '-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
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


@app.route('/gdisconnect')
def gdisconnect():
    # Only disconnect a connected user.
    access_token = login_session.get('access_token')
    if access_token is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    if result['status'] == '200':
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        response = make_response(json.dumps(
            'Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


# Disconnect based on provider
@app.route('/disconnect')
def disconnect():
    if 'provider' in login_session:
        if login_session['provider'] == 'google':
            gdisconnect()
            del login_session['gplus_id']
            del login_session['access_token']
        if login_session['provider'] == 'facebook':
            fbdisconnect()
            del login_session['facebook_id']
            login_session['username']
        del login_session['email']
        del login_session['picture']
        del login_session['user_id']
        del login_session['provider']
        flash("You have successfully been logged out.")
        return redirect(url_for('showLatestItems'))
    else:
        flash("You were not logged in")
        return redirect(url_for('showLatestItems'))


# API for requesting categories
@app.route('/categories/JSON/')
@ratelimit(limit=10, per=60 * 1)
def categoriesJSON():
    session = DBSession()
    categories = session.query(Category).all()
    session.close()
    return jsonify(Categories=[c.serialize for c in categories])


# API for requesting items
@app.route('/items/JSON/')
@ratelimit(limit=10, per=60 * 1)
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
    return render_template(
        "showlatestitems.html", categories=categories,
        items=items, login_session=login_session)


@app.route('/category/<int:category_id>/')
@app.route('/category/<int:category_id>/items/')
def showCategoryItems(category_id):
    session = DBSession()
    categories = session.query(Category).all()
    category = session.query(Category).filter_by(id=category_id).one()
    items = session.query(Item).filter_by(category_id=category_id).all()
    session.close()
    return render_template(
        "showcategoryitems.html", categories=categories,
        category=category, items=items, login_session=login_session)


@app.route('/category/<int:category_id>/items/<int:item_id>/')
def showItemDetails(category_id, item_id):
    session = DBSession()
    item = session.query(Item).filter_by(
        category_id=category_id, id=item_id).one()
    session.close()
    # Only creator of item can edit or delete the item
    if (
        'user_id' not in login_session or
            login_session['user_id'] != item.user_id):
        return render_template(
            "showitemdetailspublic.html",
            item=item, login_session=login_session)
    else:
        return render_template(
            "showitemdetails.html",
            item=item, login_session=login_session)


@app.route('/category/<int:category_id>/items/new/', methods=['GET', 'POST'])
def newItem(category_id):
    if 'email' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        now = datetime.datetime.now()
        newItem = Item(
            category_id=category_id, name=request.form['name'],
            description=request.form['description'], ctime=now,
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
        return render_template(
            "newitem.html", category=category,
            login_session=login_session)


@app.route(
    '/category/<int:category_id>/items/<int:item_id>/edit/',
    methods=['GET', 'POST'])
def editItem(category_id, item_id):
    if 'email' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        session = DBSession()
        editedItem = session.query(Item).filter_by(
            category_id=category_id, id=item_id).one()
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
        item = session.query(Item).filter_by(
            category_id=category_id, id=item_id).one()
        session.close()
        return render_template(
            "edititem.html",
            item=item, login_session=login_session)


@app.route(
    '/category/<int:category_id>/items/<int:item_id>/delete/',
    methods=['GET', 'POST'])
def deleteItem(category_id, item_id):
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
        item = session.query(Item).filter_by(
            category_id=category_id, id=item_id).one()
        session.close()
        return render_template(
            "deleteitem.html",
            item=item, login_session=login_session)


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
