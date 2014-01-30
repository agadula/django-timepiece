import os, sys
import argparse

PROJ_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
BASE_DIR = os.path.abspath(os.path.join(PROJ_DIR, os.path.pardir))
sys.path.append(PROJ_DIR)
sys.path.append(BASE_DIR)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--settings', required=True)
    args = parser.parse_args()
    
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", args.settings)
    from django.contrib.auth.models import User
    from timepiece.entries.models import SimpleEntry
    
    users = User.objects.all()
    for u in users:
        if not u.simple_entries.all() and u.is_active:
            print "("+u.username+") "+u.first_name+" "+u.last_name
