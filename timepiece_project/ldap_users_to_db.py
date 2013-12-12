import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))) 
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "timepiece_project.settings.production")

from django.contrib.auth.models import User
from django.db.utils import IntegrityError
from django.db import connection

import ldap


ldap_server="192.168.141.2"
timepiece_ldap_user_dn = "CN=Django Timepiece,OU=Special Users,OU=Agency Users,DC=agency,DC=dom"
timepiece_ldap_password = "Cowboy1234"
base_dn= "OU=Agency Staff,OU=Agency Users,DC=agency,DC=dom"

def get_user_dn(username):
    connect = ldap.open(ldap_server)
    connect.bind_s(timepiece_ldap_user_dn,timepiece_ldap_password)
    search_filter = "(&(objectclass=user)(sAMAccountName="+username+"))"    
    result = connect.search_s(base_dn,ldap.SCOPE_SUBTREE,search_filter)
    connect.unbind_s()
    return result[0][0]

def get_all_users():
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

        user = {}
        user['username'] = username
        user['first_name'] = first_name
        user['last_name'] = last_name
        user['email'] = email
        
        users.append(user)
    return users


if __name__ == "__main__":    
    user_dn = get_user_dn(username = "gentisi")
    if (user_dn == "CN=Simone GENTILINI,OU=Agency Staff,OU=Agency Users,DC=agency,DC=dom"):
        print "LDAP connection works well!"
    
    new_users = []
    existing_users = []
    
    users = get_all_users()
    for user in users:
        try:
            new_user = User.objects.create_user(user['username'])
        except IntegrityError: 
            # username already exists, need to rollback the transaction
            connection._rollback()
            existing_users.append(user)
        else:
            if user['first_name'] is not None:
                new_user.first_name = user['first_name']
            if user['last_name'] is not None:
                new_user.last_name = user['last_name']
            new_user.save()
            new_users.append(user)
            
    print str(len(existing_users)) + " already existing users"
    print str(len(new_users)) + " new users inserted"