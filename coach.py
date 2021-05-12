from os import access
from flask_login import UserMixin
import sqlite3
# from db import get_db

class Coach():
    def __init__(self,id_, name, team_id, email):
        self.id = id_
        self.name = name
        self.team_id = team_id
        self.email = email

    def is_authenticated(self):
        return True

    def is_active(self):
        return True
    
    def is_anonymous(self):
        return False

    def get_id(self):
        return self.id



    @staticmethod
    def get(unique_id):
        db = sqlite3.connect('database.db')
        user = db.execute(
            "SELECT unique_id, coach_name, team_id, email FROM coaches WHERE unique_id = ?", (unique_id,)
        ).fetchone()
        if not user:
            return None

        user = Coach(
            id_=user[0], name=user[1], team_id=user[2], email=user[3]
        )
        return user

    @staticmethod
    def create(unique_id, name, email):
        db = sqlite3.connect('database.db')
        db.execute(
            "INSERT INTO coaches (unique_id, coach_name, email) "
            "VALUES (?,?,?)",
            (unique_id, name, email)
        )
        db.commit()
    
    # @staticmethod
    # def update_access_token(unique_id, access_token):
    #     db = sqlite3.connect('database.db')
    #     db.execute(
    #         "UPDATE players SET access_token = ? WHERE player_id = ?", (access_token, unique_id)
    #     )
    #     db.commit()
    
   