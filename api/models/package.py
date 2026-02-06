from datetime import datetime
from peewee import CharField, DateTimeField
from . import BaseModel


class Package(BaseModel):
    name = CharField(unique=True)
    version = CharField()
    file = CharField()
    created_date = DateTimeField(default=datetime.utcnow)
