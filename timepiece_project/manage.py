#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    # add timepiece root to be able to import both the project and the app
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))) 

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "timepiece_project.settings.local")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
