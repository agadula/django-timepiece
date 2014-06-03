import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))) 
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "timepiece_project.settings.production")

from django.contrib.auth.models import User, Group
from django.db import connection
from django.core.exceptions import ObjectDoesNotExist

import ldap


ldap_server="192.168.141.2"
timepiece_ldap_user_dn = "CN=Django Timepiece,OU=Special Users,OU=Agency Users,DC=agency,DC=dom"
timepiece_ldap_password = "Cowboy1234"
base_dn= "OU=Agency Staff,OU=Agency Users,DC=agency,DC=dom"

# LDAP GROUPS NEEDED IN TIMEPIECE
ldap_director = 'G-DIR'.split()
ldap_units = 'G-INF G-NET G-PRU G-ADM'.split()
ldap_hous = 'GD-HoU-CPU GD-HoU-NET GD-HoU-PRU GD-HoU-RSC'.split()
ldap_sections = 'G-ICT G-WebTeam G-HHRR'.split()
ldap_groups_needed = ldap_units+ldap_sections+ldap_hous+ldap_director



def test_ldap():
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

def get_ldap_users():
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
                        if group in ldap_groups_needed:
                            groups.append(group)


        user = {}
        user['username'] = username
        user['first_name'] = first_name
        user['last_name'] = last_name
        user['email'] = email
        user['groups'] = groups
        users.append(user)
        if not user_belongs_to_a_unit(user):
            print 'WARNING: '+user['username']+' is not assigned to any unit'
    return users


def user_belongs_to_a_unit(user):
    assigned_to_a_unit = False
    for group in user['groups']:
        if group in ldap_units:
            assigned_to_a_unit = True
            break
    return assigned_to_a_unit



if __name__ == "__main__":
    ldap_users = get_ldap_users()
    print 'INFO: '+str(len(ldap_users))+' users found in LDAP'
    for ldap_user in ldap_users:
        try:
            user = User.objects.get(username=ldap_user['username'])
        except ObjectDoesNotExist:
            user = User.objects.create_user(ldap_user['username'])
            if ldap_user['first_name'] is not None:
                user.first_name = ldap_user['first_name']
            if ldap_user['last_name'] is not None:
                user.last_name = ldap_user['last_name']
            user.save()
            print 'INFO: User '+ldap_user['username']+' created'

        old_groups = user.groups.order_by('name')
        old_groups_set = set(old_groups)
        user.groups.clear()
        for group_name in ldap_user['groups']:
            try:
                group = Group.objects.get(name=group_name)
            except ObjectDoesNotExist:
                group = Group.objects.create(name=group_name)
                print 'INFO: Group '+group_name+' created'
            user.groups.add(group)
        
        agency_group = Group.objects.get(name='Agency Staff')
        user.groups.add(agency_group) # default group with CRUD on entries

        new_groups = user.groups.order_by('name')
        new_groups_set = set(new_groups)
        if old_groups_set <> new_groups_set:
            print 'INFO: '+user.username+' now belongs to :'+str(new_groups)+', previously was:'+str(old_groups)
