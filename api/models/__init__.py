import os
from datetime import datetime
from peewee import Model, SqliteDatabase

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
DB_DIR = os.path.join(PROJECT_ROOT, "db")
DB_PATH = os.path.join(DB_DIR, "data.sqlite")

os.makedirs(DB_DIR, exist_ok=True)

db = SqliteDatabase(DB_PATH, pragmas={
    "journal_mode": "wal",
    "cache_size": -1024 * 64,
    "foreign_keys": 1,
})


class BaseModel(Model):
    class Meta:
        database = db

