# Sleep Tracker

Sleep Tracker is an application that allows coaches to easily track the sleep of their players.
Sleep Tracker uses the Google Fit API in order to gain access to this data. The backend is written in 
Python and is a Flask application with a SQLite Database to manage data.

## File Layout

All the routes are in app.py as is standard for a Flask application. All templates are in the templates folder.
The User class can be found is User.py which has methods able to easily create users and connect with the Database.
The database is under database.db. There are three tables, one for the coaches, players and players sleep. 

## Running the application

While the application is in development you must export the Google client ID and Client Secret so the application
can use this to authorize users to login. Without this Google with not authorize the applications request for data.
Due to Google's rules and my own information security, I cannot post my client secret or client ID for this application.
Next you just run 
    python app.py
then flask begins and will give you a URL to go to. This will start the application.

A coach can login which will then load all the data for their team and then send them to Google Login. From their they will be
authorized and sent back to the application where they can then view their athletes' sleep data in a variety of ways. 
