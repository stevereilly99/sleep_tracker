# Python standard libraries
import json
import os
import sqlite3
from datetime import datetime, date, timedelta
import time
from math import modf
import requests

# Third-party libraries
from flask import Flask, redirect, request, url_for, render_template
import flask
from flask.globals import session
from werkzeug.datastructures import Authorization
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from oauthlib.oauth2 import WebApplicationClient
import google_auth_oauthlib.flow
from google.auth.transport.requests import Request
import googleapiclient.discovery

# Internal imports
from db import init_db_command
from user import User
from coach import Coach


# Configuration
# Set client ID and client secret using export in command line
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", None)
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", None)
GOOGLE_DISCOVERY_URL = (
    "https://accounts.google.com/.well-known/openid-configuration"
) 
GOOGLE_FIT_URL = (
    "https://accounts.google.com/o/oauth2/v2/auth"
)
token_url = "https://accounts.google.com/o/oauth2/token"

SCOPE = ["https://www.googleapis.com/auth/fitness.sleep.read"]

# Flask app setup
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)

# User session management setup
# https://flask-login.readthedocs.io/en/latest
login_manager = LoginManager()
login_manager.init_app(app)

# # Naive database setup
# try:
#     init_db_command()
# except sqlite3.OperationalError:
#     # Assume it's already been created
#     pass

# OAuth 2 client setup
client = WebApplicationClient(GOOGLE_CLIENT_ID)

# Flask-Login helper to retrieve a user from our db
@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id, session["coach"])

# Gets Google's provider configuration
def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL).json()

# Gets Sleep data from Google Fit API
def get_google_fit_info(token_url, diff_days):
    # Headers to send to in request
    # need to have players access token to pass as authorization
    fitheaders = { 'content-type': 'application/json',
            'Authorization': 'Bearer %s' % token_url }
    url = "https://www.googleapis.com/fitness/v1/users/me/dataset:aggregate"
    current_time = int(time.time() * 1000)
    # create request body with correct datatype and start date along with end date
    requestBody = {
    "aggregateBy": [
        {
        "dataTypeName": "com.google.sleep.segment"
        }
    ],
    "endTimeMillis": current_time,
    "startTimeMillis": current_time - (8.64e7 * diff_days) #This is how many days back to start the request at
    }
    # This sends post request to google
    # save result in p
    p = requests.post(url, headers=fitheaders, json=requestBody)
    
    sleep_json = p.json()

    # THIS IS MUCH EASIER WAY TO LOOK AT JSON FROM GOOGLE FOR DEBUGGING
    # with open('sleep.json', 'w') as outfile:
    #     json.dump(sleep_json, outfile, indent=4)

    #IF THE ACCESS CODE IS EXPIRED GET A NEW ONE
    if p.status_code == 401:
        print("need to refresh token")
        return 1
    
    date = sleep_json["bucket"][0]["startTimeMillis"]
    date = datetime.fromtimestamp(int(date) / 1000)
    date = date.strftime('%Y-%m-%d')

    today = datetime.today()
    today = today.replace(hour=12, minute=0, second=0)
    # start_day = today - timedelta(diff_days+1)
    # print(start_day)

    #PARSE JSON
    total_sleep = 0
    sleep_dict = []

    # Only iterate if there is data in the point dictionary
    if(sleep_json["bucket"][0]["dataset"][0]["point"] != []):
        # This is the first date that is in the JSON
        # convert it to a datetime object to make comparisons easy
        start_day = datetime.fromtimestamp(int(sleep_json["bucket"][0]["dataset"][0]["point"][0]["startTimeNanos"]) // 1000000000)
        # Set time equal to 12:00 pm
        start_day = start_day.replace(hour=12, minute=0, second=0)
        # Iterate over all data points in JSON
        for i in range(len(sleep_json["bucket"][0]["dataset"][0]["point"])):
            # Convert start time in data point to datetime object
            st = datetime.fromtimestamp(int(sleep_json["bucket"][0]["dataset"][0]["point"][i]["startTimeNanos"]) // 1000000000)
            
            # If the start time of the data point is after 12 pm of the day we are calculating
            # go add that total time to the dictionary and update the day
            if st > start_day:
                if total_sleep > 0:
                    # convert from nano seconds to hours and minutes for total time
                    # returns an array
                    time_tup = modf(total_sleep / 3.6e12)
                    # Second element is the hours
                    hours = time_tup[1]
                    # First element is the minutes
                    min = int(time_tup[0] * 60)
                    # create a list to add to the large list
                    sleep_entry = [start_day.date(), hours, min]
                    sleep_dict.append(sleep_entry)
                    # reset total_sleep to 0 to calculate the next day
                    total_sleep = 0
                # Update what the date is we are calculating for
                if start_day.date() == st.date():
                    start_day = st.replace(hour=12, minute=0, second=0) + timedelta(days=1)
                else:
                    start_day = st.replace(hour=12, minute=0, second=0)
    
            # 2 is the value for sleep 1 is the value for being awake
            if sleep_json["bucket"][0]["dataset"][0]["point"][i]["value"][0]["intVal"] == 2:
                # subtract endtime by starttime
                total_sleep += float(sleep_json["bucket"][0]["dataset"][0]["point"][i]["endTimeNanos"]) - float(sleep_json["bucket"][0]["dataset"][0]["point"][i]["startTimeNanos"])
    # If total sleep is greater than 0 do not want to miss last bit of data
    if total_sleep > 0:
        time_tup = modf(total_sleep / 3.6e12)
        hours = time_tup[1]
        min = int(time_tup[0] * 60)
        sleep_entry = [start_day.date(), hours, min]
        sleep_dict.append(sleep_entry)      
    return sleep_dict


# Renders landing page
@app.route("/")
def index():
    return render_template('index.html')

# Create Coaches accounts
@app.route("/coach_login")
def coach_login():
    # Find out what URL to hit for Google login
    google_provider_cfg = get_google_provider_cfg()
    
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]
    
    # Use library to construct the request for Google login and provide
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        access_type="offline",
        redirect_uri=request.base_url + "/callback",
        scope=["openid", "email", "profile"]
    )
    # This redirects to the callback function
    return redirect(request_uri)

#Call back for Coaches
@app.route("/coach_login/callback")
def coach_callback():
    # Get authorization code Google sent back to you
    code = request.args.get("code")

    # Find out what URL to hit to get tokens that allow you to ask for
    # things on behalf of a user
    google_provider_cfg = get_google_provider_cfg()

    token_endpoint = google_provider_cfg["token_endpoint"]
    
    # Prepare and send a request to get tokens
    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        access_type="offline",
        approval_prompt="force",
        redirect_url=request.base_url,
        code=code
    )

    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
    )

    token_response_json = token_response.json()
    # Parse tokens
    client.parse_request_body_response(json.dumps(token_response.json()))

    # hit the URL from Google that gives you the user's profile information,
    # including their Google profile image and email
    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)
    
    # make sure their email is verified.
    # The user authenticated with Google
    if userinfo_response.json().get("email_verified"):
        unique_id = userinfo_response.json()["sub"]
        users_email = userinfo_response.json()["email"]
        users_name = userinfo_response.json()["given_name"]
    else:
        return "User email not available or not verified by Google.", 400
    
    # Create a user in your db with the information provided by Google
    coach = User(
        id_=unique_id, name=users_name, team_id=0, email=users_email, access_token=token_response_json["access_token"]
    )

    # Doesn't exist? Add it to the database.
    if not User.get(unique_id, 1):
        print("Coach does not exist")
        User.create(unique_id, users_name, users_email, 0, token_response_json["access_token"], token_response_json["refresh_token"], 1)
        login_user(coach)
        session["coach"] = 1
        # Redirect to finish registration of team
        return redirect(url_for("finish_registering"))
    coach = User.get(unique_id, 1)
    # Begin user session by logging the user in
    login_user(coach)
    session["team_id"] = coach.get_team_id()
    session["coach"] = 1
    print(coach.get_team_id())
    # Gather all sleep before logging in
    update_sleep(coach.get_team_id())

    # Send user back to homepage
    return redirect(url_for("logged_in"))

# For Player registration
@app.route("/login")
def login():
    # Find out what URL to hit for Google login
    google_provider_cfg = get_google_provider_cfg()
    
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]
    
    # Use library to construct the request for Google login 
    # and provide scopes to access sleep data from players
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        access_type="offline",
        redirect_uri=request.base_url + "/callback",
        scope=["openid", "email", "profile","https://www.googleapis.com/auth/fitness.sleep.read"]
    )
    return redirect(request_uri)

# Callback for Players
@app.route("/login/callback")
def callback():
    # Get authorization code Google sent back to you
    code = request.args.get("code")

    # Find out what URL to hit to get tokens that allow you to ask for
    # things on behalf of a user
    google_provider_cfg = get_google_provider_cfg()

    token_endpoint = google_provider_cfg["token_endpoint"]
    
    # Prepare and send a request to get tokens
    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        access_type="offline",
        approval_prompt="force",
        redirect_url=request.base_url,
        code=code
    )

    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
    )
    session["coach"] = 0
    token_response_json = token_response.json()
    # Parse tokens
    client.parse_request_body_response(json.dumps(token_response.json()))

    # hit the URL from Google that gives you the user's profile information,
    # including their Google profile image and email
    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)
    
    # make sure their email is verified.
    # The user authenticated with Google
    if userinfo_response.json().get("email_verified"):
        unique_id = userinfo_response.json()["sub"]
        users_email = userinfo_response.json()["email"]
        picture = userinfo_response.json()["picture"]
        users_name = userinfo_response.json()["given_name"]
    else:
        return "User email not available or not verified by Google.", 400

    # Create a user in your db with the information provided by Google
    user = User(
        id_=unique_id, name=users_name, team_id=1, email=users_email, access_token=token_response_json["access_token"]
    )
    # Doesn't exist? Add it to the database.
    # Use the 0 to recognize that it is a player and not a coach
    if not User.get(unique_id, 0):
        User.create(unique_id, users_name, session["team"], users_email, token_response_json["access_token"], token_response_json["refresh_token"], 0)

    # Begin user session by logging the user in
    login_user(user)

    # Send Player to registered page
    return render_template('player_registered.html')

#Coaches input their team name and update database
@app.route("/finish_registering", methods=['GET', 'POST'])
@login_required
def finish_registering():
    if request.method == 'POST':
        #GET TEAM AND UPDATE TEAM NAME
        team_name = request.form.get("team_name")
        db = sqlite3.connect('database.db')
        db.execute(
            "UPDATE coaches SET team_name = ? WHERE unique_id = ?",
            (team_name, current_user.id)
        )
        db.commit()
        return redirect('/logged_in')
    else:
        return render_template('team_register.html', name=current_user.name)

@app.route("/logged_in")
@login_required
def logged_in():
    # Once coach has been added, can send hiim to logged_in page
    db = sqlite3.connect('database.db')
    team_id = db.execute(
        "SELECT team_id FROM coaches WHERE unique_id = ?", (current_user.id,)
    )
    return render_template('logged_in.html', name=current_user.name)

@app.route("/player_registration", methods = ['GET', 'POST'])
def new_login():
    if request.method=='POST':
        #FORM STUFF
        firstname = request.form.get('fname')
        lastname = request.form.get('lname')

        team = request.form.get('team_name')
        # Set session variable
        session["team"] = team
        #Send them to get authorized through google
        return redirect("/login")
    else:
        db = sqlite3.connect('database.db')
        # Get all team options for the form
        teams = db.execute(
            "SELECT team_id, team_name FROM coaches"
        )
        # Create list of dictionaries to pass to frontend
        teamlist=[]        
        for i in teams:
            dictI = {}
            dictI["id"] = i[0]
            dictI["name"] = i[1]
            teamlist.append(dictI)
        return render_template("player_registration.html", teams=teamlist)

#display sleep table with average sleep for past 7 days for each player
@app.route("/sleep_stat", methods=['GET', 'POST'])
@login_required
def sleep_stat():
    if request.method=="GET":
        db = sqlite3.connect('database.db')
        # Get last seven days worth of data from DB for 
        # averages in table
        num_days = 7
        # Convert num_days to a date object to allow comparison in query below
        num_days = date.today() - timedelta(days=num_days)
        
        player_list = []
        # Querie for sleep data
        # have query calculate the average hours and hour minutes for each player over
        # past seven days
        players_info = db.execute(
            "SELECT player_name, AVG(hours_slept), AVG(minutes_slept), player_id FROM sleep WHERE team_id = ? AND date >= ? GROUP BY player_name",
            (current_user.team_id, num_days,)
        )
        players_info = players_info.fetchall()
        for i in players_info:
            player = {}
            player["name"] = i[0]
            # Have to round to 0 or else get decimal poins
            player["sleep_hours"] = round(i[1], 0)
            player["sleep_minutes"] = round(i[2], 0)
            player["id"] = i[3]
            # add to list that will be passed to front end
            player_list.append(player)
        
        db.close()

        return render_template('sleep_table.html', sleep_dict=player_list)

#Get entire sleep history for player of coach choosing
@app.route("/sleep_table", methods=['GET', 'POST'])
@login_required
def sleep_table():
    if request.method == "POST":
        #Gets data on only the one player a coach wants to see
        player_id = request.form.get("player_list")
        db = sqlite3.connect('database.db')
        # Make selection based off of unique id in case of duplicate names
        player_info = db.execute(
            "SELECT player_name, date, hours_slept, minutes_slept FROM sleep WHERE player_id = ?", (player_id,)
        )
        player_info = player_info.fetchall()
        # Create dictionary to pass to frontend
        player_list = []
        for i in player_info:
            player = {}
            player["name"] = i[0]
            player["date"] = i[1]
            # No averages this time
            # Getting raw numbers from DB
            player["sleep_hours"] = i[2]
            player["sleep_minutes"] = i[3]
            player_list.append(player)

        db.close()
        return render_template("individual_player.html", sleep_dict=player_list)
    else:
        return render_template('sleep_stat.html')

# Finish registering a team
@app.route("/team_register", methods=['GET', 'POST'])
def team_register():
    return redirect('/coach_login')

#Let Coach know team was registered
@app.route("/team_registered", methods=['GET', 'POST'])
def team_registered():
    return render_template("team_registered.html")

# Update sleep table for coach during login
def update_sleep(team_id):
    
    today = date.today()

    yesterday = today - timedelta(days=1)

    db = sqlite3.connect('database.db')
    # Find the latest date in the DB
    # Use it to create post request to google
    latest_date = db.execute(
        'SELECT DISTINCT date FROM sleep  WHERE team_id = ? ORDER BY date DESC ',
        (team_id,)
    )
    # db.close()
    print(latest_date)
    # print(latest_date.fetchall()[0][0])
    # latest_date = latest_date.fetchall()[0][0]
    # latest_date = datetime.strptime(latest_date, "%Y-%m-%d").date()
    # print(latest_date)
    if latest_date != []:
        # diff = yesterday - latest_date
        # diff = diff.days
        
        diff = 30

        # GOING TO UPDATE DATABASE FOR EACH PLAYER INDIVUDALLY
        if diff > 0:
            # Select data needed to create request to Google Fit
            players = db.execute(
                "SELECT player_id, name, access_token, refresh_token FROM players WHERE team_id = ?",
                (team_id,)
            )
            # Check that there are players in this coaches team
            if players is not None:
                player_list = []
                players = players.fetchall()
                for player in players:
                    player_dict = {}
                    player_dict["player_id"] = player[0]
                    player_dict["team_id"] = team_id
                    player_dict["name"] = player[1]
                    player_dict["access_token"] = player[2]
                    player_dict["refresh_token"] = player[3]
                    player_list.append(player_dict)

                players_sleep_data = []
                for player in player_list:
                    # Call function to get sleep data from Google Fit
                    retVal = get_google_fit_info(player["access_token"], diff)
                    # This means access token is expired
                    # use refresh token to get a new one
                    if retVal == 1:
                        access_token_request = {
                            "client_id": GOOGLE_CLIENT_ID,
                            "client_secret": GOOGLE_CLIENT_SECRET,
                            "refresh_token": player["refresh_token"],
                            "grant_type": "refresh_token" 
                        }
                        p = requests.post(token_url, data=access_token_request)
                        p = p.json()
                        with open('new_acccess_token.json', 'a') as outfile:
                            json.dump(p, outfile, indent=4)
                        
                        # Call User function to update player access token
                        User.update_access_token(player["player_id"], p["access_token"])
                        retVal = get_google_fit_info(p["access_token"], diff)
                    # Loops over sleep data passed back and inserts it into the DB for that player
                    for i in retVal:
                        player["date"] = i[0]
                        player["sleep_hours"] = i[1]
                        player["sleep_minutes"] = i[2]
                        db.execute("BEGIN TRANSACTION")  
                        db.execute(
                            "INSERT INTO sleep (player_name, player_id, team_id, hours_slept, minutes_slept, date) VALUES (?, ?, ?, ?, ?, ?)",
                            (player["name"], player["player_id"], player["team_id"], player["sleep_hours"], player["sleep_minutes"], player["date"])
                        )
                        db.execute("COMMIT")
        db.close()

@app.route("/sleep_chart", methods=['GET', 'POST'])
@login_required
def sleep_chart():
    if request.method == 'POST':
        # Gets the data from the DB and passes in the correct format to chart.js
        # to create the dynamic graph of sleep data
        db = sqlite3.connect('database.db')
        player_id = request.form.get("player_list")
        # Use player ID incase of duplicate names
        chart_info = db.execute(
            "SELECT date, hours_slept FROM sleep WHERE player_id = ?", (player_id,)
        )
        chart_info = chart_info.fetchall()
        # Create labels for chartjs
        labels = [i[0] for i in chart_info]
        # Create values for data points for Chartjs
        values= [i[1] for i in chart_info]
        db.close()
        # Passing necessary labels and values to create line
        # graph using Chartjs
        return render_template("sleep_graph.html", labels=labels, values=values) 
    else:
        # Create form for coach to choose which player they want to see
        # graph of sleep data for
        db = sqlite3.connect('database.db')
        players = db.execute(
            "SELECT name, player_id FROM players WHERE team_id =?", (session["team_id"],)
        )
        players_info = players.fetchall()
        
        players = []
        for player in players_info:
            temp = {}
            temp["name"] = player[0]
            temp["id"] = player[1]
            players.append(temp)
        # Passing player info to create drop down options for coach
        return render_template('sleep_chart_get.html', players=players)

@app.route("/logout")
@login_required
def logout():

    # Thank you Flask Login Manager
    logout_user()
    return redirect(url_for("index"))

if __name__ == "__main__":
    # This is being used to test application
    conn = sqlite3.connect('database.db')
    conn.execute("DELETE FROM sleep WHERE date > 2021-03-24" )
    conn.commit()
    conn.close
    
    app.run(ssl_context="adhoc")