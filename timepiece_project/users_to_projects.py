import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))) 
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "timepiece_project.settings.production")

from django.contrib.auth.models import User

from timepiece.crm.models import Business, Project, ProjectRelationship


def assign_to_projects_in_activity(username, activityname):
    try:
        u = User.objects.filter(username = username)[0]
    except:
        raise Exception(username+" not found")
    
    businesses = Business.objects.filter(name__startswith = activityname)
    if len(businesses) != 1: 
        raise Exception("No activities or too many corresponding Activities starting with: "+activityname)
    b = businesses[0]

    projects = b.new_business_projects.all()
    for p in projects:
        if u not in p.users.all():
            pr = ProjectRelationship()
            pr.user = u
            pr.project = p
            pr.save()
            print pr


if __name__ == "__main__":
    users = User.objects.all()
    for user in users:
        assign_to_projects_in_activity(user.username, "0.1")

    assignments = {
                'munarlo' : '2.3 3.1 3.2 5.2 6.3 7.1 A.3'.split(),
                'azaolmo' : '1.1 1.2 2.1 2.2 2.3 2.4 2.5 2.6 3.1 3.2 3.3 4.1 4.2 4.3 4.4 5.1 5.2 6.1 6.2 6.3 7.1 A.3'.split(),
                'cruzmar' : 'A.1 A.3'.split(),
                'izaguan' : '3.1 5.2 6.2 6.3 7.1 A.2 A.3'.split(),
                'mullebi' : '1.1 1.2 2.1 2.2 2.3 2.4 2.5 2.6 3.1 3.2 3.3 4.1 4.2 4.3 4.4 5.1 5.2 6.1 6.2 6.3 7.1 A.3'.split(),
                'smithan' : '1.1 1.2 2.1 2.2 2.3 2.4 2.5 2.6 3.1 3.2 3.3 4.1 4.2 4.3 4.4 5.1 5.2 6.1 6.2 6.3 7.1 A.2 A.3 C.1 C.3'.split(),
                }

    for username, activities in assignments.iteritems():
        for activity in activities:
            assign_to_projects_in_activity(username, activity)
