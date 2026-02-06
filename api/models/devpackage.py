from datetime import datetime
from peewee import ForeignKeyField, CharField, DateTimeField
from . import BaseModel
from .device import Device
from .package import Package


class DevicePackage(BaseModel):
    device = ForeignKeyField(Device, backref="device_packages", on_delete="CASCADE")
    package = ForeignKeyField(Package, backref="package_devices", on_delete="CASCADE")
    version = CharField()
    created_date = DateTimeField(default=datetime.utcnow)

