import ldap

ldap_server="192.168.141.2"
timepiece_ldap_user_dn = "CN=Django Timepiece,OU=Special Users,OU=Agency Users,DC=agency,DC=dom"
timepiece_ldap_password = "Cowboy1234"
base_dn= "OU=Agency Staff,OU=Agency Users,DC=agency,DC=dom"

def get_user_dn(username):
    connect = ldap.open(ldap_server)
    connect.bind_s(timepiece_ldap_user_dn,timepiece_ldap_password)
    search_filter = "(&(objectclass=*)(sAMAccountName="+username+"))"    
    result = connect.search_s(base_dn,ldap.SCOPE_SUBTREE,search_filter)
    connect.unbind_s()
    return result[0][0]

def get_all_users():
    connect = ldap.open(ldap_server)
    connect.bind_s(timepiece_ldap_user_dn,timepiece_ldap_password)
    search_filter = "(&(objectclass=*)(sAMAccountName="+username+"))"    
    result = connect.search_s(base_dn,ldap.SCOPE_SUBTREE,search_filter)
    connect.unbind_s()
    return result



if __name__ == "__main__":    
    user_dn = get_user_dn(username = "gentisi")
    if (user_dn == "CN=Simone GENTILINI,OU=Agency Staff,OU=Agency Users,DC=agency,DC=dom"):
        print "LDAP connection works well!"
    
    users = get_all_users()
    print users