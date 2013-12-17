import os, sys, io
import argparse


def _get_unique_activity(activityname):
    """ returns the activity or raises an error if 0 or more than 1 activity corresponds"""
    businesses = Business.objects.filter(name__startswith = activityname)
    if len(businesses) != 1:
        raise Exception("No activities or too many corresponding Activities starting with: "+activityname)
    b = businesses[0]
    return b


def assign_to_projects_in_activity(username, activityname):
    try:
        u = User.objects.filter(username = username)[0]
    except:
        raise Exception(username+" not found")

    b = _get_unique_activity(activityname)

    projects = b.new_business_projects.all()
    for p in projects:
        if u not in p.users.all():
            pr = ProjectRelationship()
            pr.user = u
            pr.project = p
            pr.save()
            print pr


def get_activities_from_file(filename):
    activities = []
    with io.open(filename, encoding = "ISO-8859-1") as f:
        lines = f.readlines()
        for line in lines:
            if line.startswith("Unit") or line.startswith("Name") or line.startswith(",,,") or line.startswith("0,,,,,,,,,,"):
                continue
            elements = line.split(",")
            activity = elements[0]
            users = elements[1:]

            if activity.startswith('"'):
                activity +=","+ users.pop(0)
                activity = activity.strip('"')

            a = {}
            a['name'] = activity.strip()
            a['users'] = []

            for user in users:
                user = user.strip('"')
                user = user.strip()
                if user != "":
                    a['users'].append(user)

            activities.append(a)
    return activities


def check_that_activities_exist_in_db(activities):
    """Check that only one corresponding activity exist in the database"""
    for a in activities:
        activityname = a['name']
        b = _get_unique_activity(activityname[:3])


def get_unique_users(activities):
    users = []
    for a in activities:
        for u in a['users']:
            if u not in users: users.append(u)
    users.sort()
    return users


def map_users_to_usernames(raw_users):
    users = {}
    for raw_user in raw_users:
        first_name = raw_user.split()[0]
        users_found = User.objects.filter(first_name__istartswith = first_name)
        if len(users_found) == 1:
            username = users_found[0].username
        else:
            username = None
        users[raw_user] = username
    return users


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--settings')
    args = parser.parse_args()

    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", args.settings)
    from django.contrib.auth.models import User
    from timepiece.crm.models import Business, Project, ProjectRelationship

    # Load activities and their users from the Matrix file
    activities = get_activities_from_file("./fixtures/users_to_activities.csv")

    # Remove activities which are in the Matrix but not available this year
    not_this_year = "2.6 3.3 5.3".split()
    activities = [a for a in activities if (a['name'][:3] not in not_this_year)]

    # Use the first three letters of the activity to
    check_that_activities_exist_in_db(activities)

    # Get a list of raw users name and surname
    raw_users = get_unique_users(activities)

    # Try to map the raw names and surnames to existing usernames
    users_usernames = map_users_to_usernames(raw_users)

    users_by_hands = {
                        u'AST 3': None,
                        u'BEGONA GRA\xd1A': 'granabe',
                        u'ENMMANUELLE BRUN': 'brunemm',
                        u'MARIA JOSE URKIDI': 'urkidma',
                        u'MONIZA AZAOLA': 'azaolmo',
                        u'NATALIA DIMITROVA': 'dimitna',
                        u'TIMOTY TREGENZA': 'tregeti',
                        u'MARI CARMEN DE LA CRUZ': 'cruzmar',
                        u'MARTA DE PRADO': 'deprama',
                        u'MARTA URRUTIA': 'urrutma',
                        u'MONICA VEGA': 'vegamon',
                        u'SILVIA GRADOS': 'gradosi',
                        u'XABIER ALTUBE': 'altubxa',
                        u'XABIER IRASTORZA': 'irastxa',
                    }
    users_usernames.update(users_by_hands)

    # Assign to all users the 0.1 Cross-cutting categories
    users = User.objects.all()
    for user in users:
        assign_to_projects_in_activity(user.username, "0.1")

    # Do special assignments
    assign_to_projects_in_activity('bolabog', "IPA") # Add Boglarka BOLA to IPA
    assign_to_projects_in_activity('tregeti', "ENP") # Add Tim TREGENZA to ENP

    # Mass assignments based on the matrix
    for activity in activities:
        for raw_user in activity['users']:
            if raw_user == "AST 3": continue
            username = users_usernames[raw_user]
            assign_to_projects_in_activity(username, activity['name'][:3])


    # Assign to admin every project
    businesses = Business.objects.all()
    for activity in businesses:
        assign_to_projects_in_activity('admin', activity.name[:3])

#     # reset passwords for cross check on development machine
#     default_password = "pbkdf2_sha256$10000$xKZKJn4h5ejo$uSlna78YyQfag7f0q7WdOWlMDyFzVjiPqoxjLrqedO4=" # password is password
#     users = User.objects.all()
#     for user in users:
#         user.password = default_password
#         user.groups.add(1)
#         user.save()
