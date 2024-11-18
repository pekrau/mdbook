"Users database and permissions handling."

import hashlib
from http import HTTPStatus as HTTP
import os
from pathlib import Path
import uuid

import yaml

import constants
import utils
from utils import Error


class Users:
    "In-memory users database."

    def __init__(self, filepath):
        self.filepath = filepath
        self.users = {}
        self.apikey_lookup = {}
        self.email_lookup = {}
        self.read()

    def read(self):
        "Read entire database."
        self.users.clear()
        try:
            with self.filepath.open() as infile:
                for user in yaml.safe_load(infile.read())["users"]:
                    self.users[user["id"]] = user
                    self.apikey_lookup[user["apikey"]] = user
                    self.email_lookup[user["email"]] = user
        except FileNotFoundError:
            pass

    def write(self):
        "Write entire database."
        with self.filepath.open("w") as outfile:
            outfile.write(
                yaml.dump(dict(users=list(self.users.values())), allow_unicode=True)
            )

    def __getitem__(self, key):
        "Get the user data given either the userid, apikey or email."
        for lookup in [self.users, self.apikey_lookup, self.email_lookup]:
            try:
                return lookup[key]
            except KeyError:
                pass
        raise Error(f"no such user '{key}'", HTTP.BAD_REQUEST)

    def __contains__(self, key):
        return (
            key in self.users or key in self.apikey_lookup or key in self.email_lookup
        )

    def login(self, userid, password):
        "Get the user if the userid and password are correct, else None."
        try:
            user = self.users[userid]
        except KeyError:
            return None
        h = hashlib.sha256()
        h.update(user["salt"].encode(constants.ENCODING))
        h.update(password.encode(constants.ENCODING))
        if h.hexdigest() == user["password"]:
            return user
        else:
            return None

    def add_user(self, userid, password, name, email, groups=None):
        "Add a new user, and write out."
        if userid in self.users:
            raise Error(f"user '{userid}' already registered", HTTP.BAD_REQUEST)
        if email in self.email_lookup:
            raise Error(f"user '{email}' already registered", HTTP.BAD_REQUEST)
        self.users[userid] = user = dict(
            id=userid,
            name=name,
            email=email,
            groups=groups or [constants.USER_ROLE],
            apikey=uuid.uuid4().hex,
        )
        self.apikey_lookup[user["apikey"]] = user
        self.email_lookup[user["email"]] = user
        self._set_password(userid, password)
        self.write()

    def set_password(self, userid, password):
        "Set the new passwor for the user, and write out."
        self._set_password(userid, password)
        self.write()

    def _set_password(self, userid, password):
        "Actually set the new password for the user, but do not write out."
        user = self[userid]
        salt = uuid.uuid4().hex.encode(constants.ENCODING)
        h = hashlib.sha256()
        h.update(salt)
        h.update(password.encode(constants.ENCODING))
        user["salt"] = salt.decode()
        user["password"] = h.hexdigest()


# Singleton instance of in-memory users database.
_users = None


def get_users():
    global _users
    if not _users:
        _users = Users(
            Path(os.environ["MDBOOK_DIR"]) / constants.USERS_DATABASE_FILENAME
        )
    return _users


if __name__ == "__main__":
    users = get_users()
    userid = "pekrau"
    password = "01glurg"
    if not userid in users:
        print("adding", userid)
        users.add_user(
            userid,
            password=password,
            name="Kraulis, Per",
            email="per.kraulis@gmail.com",
            groups=[constants.ADMIN_GROUP, constants.USER_GROUP],
        )
    else:
        print("login", users.login(userid, password))
