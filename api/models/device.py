from datetime import datetime
from peewee import CharField, DateTimeField
from . import BaseModel


class Device(BaseModel):
    serial = CharField(unique=True)
    imei = CharField(null=True)
    wifi_mac = CharField(null=True)
    ext_ip = CharField(null=True)
    lan_ip = CharField(null=True)
    last_noticed = DateTimeField(null=True)
    last_updated = DateTimeField(null=True)

