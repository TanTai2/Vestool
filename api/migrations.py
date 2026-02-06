import os
from models import db
from models.device import Device
from models.package import Package
from models.devpackage import DevicePackage

def run_migrations():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    packages_dir = os.path.join(base_dir, "packages")
    os.makedirs(packages_dir, exist_ok=True)
    try:
        db.connect(reuse_if_open=True)
        db.create_tables([Device, Package, DevicePackage], safe=True)
    finally:
        if not db.is_closed():
            db.close()

