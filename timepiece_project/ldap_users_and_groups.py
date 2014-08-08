import os, sys
import argparse
import ldap



def test():
    user_dn = get_user_dn(username = "gentisi")
    if (user_dn == "CN=Simone GENTILINI,OU=Agency Staff,OU=Agency Users,DC=agency,DC=dom"):
        print "LDAP test ok"
    else:
        print 'Cannot get user gentisi. Please check the LDAP python connection.'

def get_user_dn(username):
    connect = ldap.open(ldap_server)
    connect.bind_s(timepiece_ldap_user_dn,timepiece_ldap_password)
    search_filter = "(&(objectclass=user)(sAMAccountName="+username+"))"
    result = connect.search_s(base_dn,ldap.SCOPE_SUBTREE,search_filter)
    connect.unbind_s()
    return result[0][0]

def get_users_from_ldap_users():
    connect = ldap.open(ldap_server)
    connect.bind_s(timepiece_ldap_user_dn,timepiece_ldap_password)
    search_filter = "(objectclass=user)"    
    ldap_users = connect.search_s(base_dn,ldap.SCOPE_SUBTREE,search_filter)
    connect.unbind_s()
    
    users = []
    for ldap_user in ldap_users:
        user_dn = ldap_user[0]
        ldap_user_info = ldap_user[1]
        username = ldap_user_info['sAMAccountName'][0]

        try: first_name = ldap_user_info["givenName"][0]
        except KeyError: first_name = None
        try: last_name = ldap_user_info["sn"][0]
        except: last_name = None
        email = ldap_user_info["mail"][0]
        ldap_groups = ldap_user_info['memberOf'] # e.g.: ['CN=P-MYRIAD,OU=Printer Groups,OU=Agency Groups,DC=agency,DC=dom', ...
        groups = []
        for ldap_group in ldap_groups:
            if 'Agency Groups' in ldap_group:
                elements = ldap_group.split(',')
                for elem in elements:
                    if elem.startswith('CN'):
                        cn, group = elem.split('=')
                        groups.append(group)

        user = {}
        user['username'] = username
        user['first_name'] = first_name
        user['last_name'] = last_name
        user['email'] = email
        user['groups'] = groups
        users.append(user)
        if not user_belongs_to_a_unit(user):
            print 'WARNING: '+user['username']+' is not assigned to any unit of '+str(ldap_units)
    return users


def user_belongs_to_a_unit(user):
    assigned_to_a_unit = False
    for group in user['groups']:
        if group in ldap_units:
            assigned_to_a_unit = True
            break
    return assigned_to_a_unit


def _create_group(group_name):
    try:
        group = Group.objects.get(name=group_name)
    except ObjectDoesNotExist:
        group = Group.objects.create(name=group_name)
        print 'INFO: Group '+group_name+' created'
    return group


def _reset_permission(codename):
    try:
        p = Permission.objects.get(codename=codename)
        p.delete()
        print 'INFO: Permission '+p.codename+' deleted'
    except ObjectDoesNotExist:
        pass
    return _create_permission(codename)


def _create_permission(codename):
    base_p = Permission.objects.get(codename='add_entry')
    try:
        p = Permission.objects.get(codename=codename)
    except ObjectDoesNotExist:
        p = Permission()
        p.codename = codename
        p.name = codename.replace('_',' ')
        p.content_type = base_p.content_type
        p.save()
        print 'INFO: Permission '+p.codename+' created'
    return p


def sync_users_and_groups():
    users = get_users_from_ldap_users()
    print 'INFO: '+str(len(users))+' users found in LDAP'
    for user in users:
        try:
            u = User.objects.get(username=user['username'])
        except ObjectDoesNotExist:
            u = User.objects.create_user(user['username'])
            if user['first_name'] is not None:
                u.first_name = user['first_name']
            if user['last_name'] is not None:
                u.last_name = user['last_name']
            u.save()
            print 'INFO: User '+user['username']+' created'

        old_groups = u.groups.order_by('name')
        old_groups_set = set(old_groups)
        u.groups.clear()
        for group_name in user['groups']:
            group = _create_group(group_name)
            u.groups.add(group)

        new_groups = u.groups.order_by('name')
        new_groups_set = set(new_groups)
        if old_groups_set <> new_groups_set:
            print 'INFO: '+u.username
            print 'now: '+str(new_groups)
            print 'was: '+str(old_groups)
    prepare_permissions_and_groups()


def _give_permission_to_groups(perm, groups):
    for group_name in groups:
        group = Group.objects.get(name=group_name)
        group.permissions.add(perm)
        print 'INFO: Permission '+perm.codename+' given to '+group_name


def _give_permission_to_users(perm, users):
    for user_name in users:
        user = User.objects.get(username=user_name)
        user.user_permissions.add(perm)
        print 'INFO: Permission '+perm.codename+' given to '+user_name


def prepare_permissions_and_groups():
    # set basic permissions
    basic_perms = ['add_entry', 'change_entry', 'delete_entry']
    basic_perms+= ['can_clock_in', 'can_clock_out', 'can_pause']
    basic_perms+= ['can_download_report'] # can download reports

    for ldap_group in ldap_units:
        group = Group.objects.get(name=ldap_group)
        for perm in basic_perms:
            p = _create_permission(perm)
            group.permissions.add(p)
        print 'INFO: Basic Permissions given to '+group.name

    # reset (delete+set) special reports permissions, groups and users must exist
    see_all_reports_groups = ['G-ABB-DIRECTOR', 'G-ABB-ADMIN-HR', 'G-ABB-ADMIN-FIN']
    see_all_reports_users = []
    reports_permissions_map = [
        # (report filter, groups, users)
        ('cpu', ['G-ABB-HOU-CPU'], [] ),
        ('net', ['G-ABB-DIRECTOR'], [] ),
        ('pru', ['G-ABB-HOU-PRU'], [] ),
        ('rsc', ['G-ABB-HOU-RSC'], [] ),
        ('ict', ['G-ABB-ICT'], [] ),
    ]

    view_some_report = _reset_permission('view_some_report') # basic special reports permission
    _give_permission_to_groups(view_some_report, see_all_reports_groups)
    _give_permission_to_users(view_some_report, see_all_reports_users)

    for report_permission in reports_permissions_map:
        report_filter, groups, users = report_permission
        perm = 'view_'+report_filter+'_report'
        p = _reset_permission(perm)
        # give basic special reports permission
        _give_permission_to_groups(view_some_report, groups)
        _give_permission_to_users(view_some_report, users)
        
        # give specific special report permissions and groups/user that can see all reports get all the permissions
        groups+=see_all_reports_groups
        users+=see_all_reports_users
        _give_permission_to_groups(p, groups)
        _give_permission_to_users(p, users)



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--settings', required=True)
    parser.add_argument('--do', choices=["sync", 'preparedb', 'test'], required=True)
    args = parser.parse_args()

    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", args.settings)
    from django.contrib.auth.models import User, Group, Permission
    from django.db import connection
    from django.core.exceptions import ObjectDoesNotExist
    from django.conf import settings


    ldap_server = getattr(settings, "AUTH_LDAP_SERVER_URI", None).replace('ldap://','')
    timepiece_ldap_user_dn = getattr(settings, "AUTH_LDAP_BIND_DN", None)
    timepiece_ldap_password = getattr(settings, "AUTH_LDAP_BIND_PASSWORD", None)
    base_dn = getattr(settings, "AUTH_LDAP_USER_SEARCH_BASEDN", None)

    ldap_units = 'G-INF G-NET G-PRU G-ADM'.split() # CPU NET PRU RSC

    if args.do == "sync": sync_users_and_groups()
    if args.do == "preparedb": prepare_permissions_and_groups()
    if args.do == "test": test()
