from os import access
from flask_login import UserMixin
import sqlite3
from db import get_db

class User(UserMixin):
    def __init__(self,id_, name, team_id, email, access_token, refresh_token=None):
        self.id = id_
        self.name = name
        self.team_id = team_id
        self.email = email
        self.access_token = access_token
        self.refresh_token = refresh_token

    def is_authenticated(self):
        return True

    def is_active(self):
        return True
    
    def is_anonymous(self):
        return False

    def get_id(self):
        return self.id

    def get_team_id(self):
        return self.team_id
        
    @staticmethod
    def get(unique_id, coach):
        db = sqlite3.connect('database.db')
        if coach == 0:
            user = db.execute(
                "SELECT * FROM players WHERE player_id = ?", (unique_id,)
            ).fetchone()
            if not user:
                return None

            user = User(
                id_=user[0], name=user[1], team_id=user[2], email=user[3], access_token=user[4], refresh_token=user[5]
            )
            return user
        else:
            user = db.execute(
            "SELECT unique_id, coach_name, team_id, email FROM coaches WHERE unique_id = ?", (unique_id,)
            ).fetchone()
            if not user:
                return None

            user = User(
                id_=user[0], name=user[1], team_id=user[2], email=user[3], access_token=None, refresh_token=None
            )
            return user

    @staticmethod
    def create(unique_id, name, email, team_id, access_token, refresh_token, coach):
        db = sqlite3.connect('database.db')
        # Not a coach
        if coach == 0:
            db.execute(
                "INSERT INTO players (player_id, name, team_id, email, access_token, refresh_token) "
                "VALUES (?,?, ?, ?, ?, ?)",
                (unique_id, name, email, team_id, access_token, refresh_token)
            )
            db.commit()
        else:
            db.execute(
                "INSERT INTO coaches (unique_id, coach_name, email) "
                "VALUES (?,?,?)",
                (unique_id, name, email)
            )
            db.commit()
    
    @staticmethod
    def update_access_token(unique_id, access_token):
        db = sqlite3.connect('database.db')
        db.execute(
            "UPDATE players SET access_token = ? WHERE player_id = ?", (access_token, unique_id)
        )
        db.commit()
    
   