import ldap

if __name__ == "__main__":
  	ldap_server="192.168.141.2"
	timepiece_ldap_user_dn = "CN=Django Timepiece,OU=Special Users,OU=Agency Users,DC=agency,DC=dom"
	timepiece_ldap_password = "Cowboy1234"

	connect = ldap.open(ldap_server)
	connect.bind_s(timepiece_ldap_user_dn,timepiece_ldap_password)

	username = "gentisi"
 	password = "" # fill with my password

	base_dn= "OU=Agency Staff,OU=Agency Users,DC=agency,DC=dom"
	search_filter = "(&(objectclass=*)(sAMAccountName="+username+"))"
	result = connect.search_s(base_dn,ldap.SCOPE_SUBTREE,search_filter)
	
	connect.unbind_s()

# 	# try to login with user credentials
# 	user_dn = "CN=Simone GENTILINI,OU=Agency Staff,OU=Agency Users,DC=agency,DC=dom"
	user_dn = result[0][0]

	connect = ldap.open(ldap_server)
 	connect.bind_s(user_dn,password)
 	connect.unbind_s()
