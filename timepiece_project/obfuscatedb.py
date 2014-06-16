import os, sys
import argparse
from random import randrange


def get_random_user(user_list):
    index = randrange(0, len(user_list)-1)
    return user_list[index]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--settings', required=True)
    args = parser.parse_args()

    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", args.settings)
    from django.contrib.auth.models import User
    from timepiece.entries.models import SimpleEntry

    entries = SimpleEntry.objects.all()
    users = User.objects.filter(is_active=True)
    number_of_users_without_entries = 15
    number_of_users_with_entries = len(users)-number_of_users_without_entries
    random_users = []
    for i in range(number_of_users_with_entries):
        random_users.append(get_random_user(users))
    
    for e in entries:
        e.user = get_random_user(random_users)
        e.save()
