import os

from fabric.api import *
from fabric.contrib.console import confirm
from fabric.contrib.files import sed
from fabric.operations import get

from contextlib import contextmanager as _contextmanager



STATIC_ABSPATH = "/var/www/django/timepiece/timepiece/static"
SITEPACKAGES = "/var/www/.virtualenvs/timepiece/lib/python2.7/site-packages"
CODE_PATH = "/var/www/django/timepiece"


db_name = "timepiece"
db_user = "gentisi"
linux_user = db_user
db_backup_file = 'dump_'+db_name+'.sql'


@_contextmanager
def virtualenv():
    require('project_path', provided_by=('dev', 'stag', 'prod'))
    with cd(env.project_path):
        with prefix(env.activate):
            yield

def dev():
    env.environment = 'development'
    env.activate = 'source /Users/simonegentilini/.virtualenvs/timepiece/bin/activate'
    env.project_path = "/Users/simonegentilini/Dropbox/workspace/timepiece/timepiece_project"
    env.settings_file = "settings.local"

def stag():
    """ use staging environment on remote host"""
    env.environment = 'staging'
    env.hosts = ['root@192.168.141.235']
    env.activate = 'source /var/www/.virtualenvs/timepiece/bin/activate'
    env.project_path = "/var/www/django/timepiece/timepiece_project"
    env.settings_file = "settings.production"

def prod():
    """ use production environment on remote host"""
    env.environment = 'production'
    env.hosts = ['root@192.168.141.11']
    env.activate = 'source /var/www/.virtualenvs/timepiece/bin/activate'
    env.project_path = "/var/www/django/timepiece/timepiece_project"
    env.settings_file = "settings.production"


# LOCAL COMMANDS
def test():
    with settings(warn_only=True):
        result = local("./run_tests.py")
    if result.failed and not confirm("Tests failed. Continue anyway?"):
        abort("Aborting at user request.")

def runserver():
    local("python timepiece_project/manage.py runserver")

def shell():
    if env.environment == 'development':
        local("python timepiece_project/manage.py shell")
    else:
        with virtualenv():
            run('python manage.py shell --settings='+env.settings_file )

def commit():
    local("git add -p && git commit")

def push():
    local("git push")

def prepare_deploy():
    #test()
    commit()
    push()


# REMOTE COMMANDS
def deploy():
    with settings(warn_only=True):
        if run("test -d %s" % CODE_PATH).failed:
            run("git clone https://github.com/agadula/django-timepiece.git -b eu-osha %s" % CODE_PATH)
            
            # copy the django admin static to website static folder
            run("cp -r "+SITEPACKAGES+"/django/contrib/admin/static/admin"+" "+STATIC_ABSPATH)
            
            # change permissions to let www-data create the CACHE folder
            run("chmod 775 "+STATIC_ABSPATH)

    with cd(CODE_PATH):
        run("git pull")
        run("touch app.wsgi")
        if env.environment == 'staging':
#             add in the banner menu that it's test version
            before = '>Timepiece<'
            after = 'style="color: red;">Timepiece TEST<'
            filename = os.path.join(CODE_PATH, 'timepiece/templates/timepiece/navigation.html')
            sed(filename, before, after)
    apache_restart()

def apache_update_conf():
    """ upload apache configuration to remote host """
    #require('root', provided_by=('staging', 'production'))
    with cd(env.project_path+"/apache"):
        source = os.path.join(env.project_path, 'apache', 'production.conf')
        dest = os.path.join("/etc/apache2/sites-available", 'timepiece')
        put(source, dest, mode=0755)
        apache_reload()

def apache_reload():
    """ reload Apache on remote host """
    #require('root', provided_by=('staging', 'production'))
    run('sudo /etc/init.d/apache2 reload')
    
def apache_restart():    
    """ restart Apache on remote host """
    #require('root', provided_by=('staging', 'production'))
    run('sudo /etc/init.d/apache2 restart')
    
def apache_errlog():
    run('tail /var/log/apache2/error.log')

def _remove_db_if_exists(remote=False):
    with settings(warn_only=True):
        cmd = 'dropdb '+db_name
        if remote:
            result = run('sudo -u '+db_user+' '+cmd)
        else:
            result = local(cmd)
    if result.failed and not confirm("Remove of db failed. Continue anyway?"):
        abort("Aborting at user request.")

def createdb():
    _remove_db_if_exists(remote=True)

#     CHECK IF USER ALREADY EXISTS IN THE DB
#     psql postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='USR_NAME'"
#     Yields 1 if found and nothing else.
    with settings(warn_only=True):
        result = run('sudo -u postgres createuser {} -P'.format(db_user) )
    if result.failed and not confirm("Creation of role failed. Continue anyway?"):
        abort("Aborting at user request.")

    run('sudo -u {} createdb -E utf8 -O {} {} -T template0'.format(linux_user, db_user, db_name) )
    syncdb()

def backupdb():
	"""Backups the db and copies it locally"""
	# pg_dump -U {user-name} {source_db} -f {dumpfilename.sql}
	run('sudo -u postgres pg_dump {} > {}'.format(db_name, db_backup_file) )
	get(db_backup_file, db_backup_file)
	run("rm "+db_backup_file)

def restoredb():
	# psql -U {user-name} -d {desintation_db} -f {dumpfilename.sql}
	_remove_db_if_exists()
	local('psql --command="CREATE DATABASE {}"'.format(db_name) )
	local('psql -d {} -f {}'.format(db_name, db_backup_file) )

def copyremotedb():
	backupdb()
	restoredb()

def syncdb():
    with virtualenv():
        run('python manage.py syncdb --settings='+env.settings_file )
        run('python manage.py loaddata users.yaml activities-projects.yaml --settings='+env.settings_file )

def ldap_users_to_db():
    with virtualenv():
        run('python ldap_users_to_db.py')


def _user_to_projects(user=None, do=None, activity=None):
    require('settings_file', provided_by=('dev', 'stag', 'prod'))
    cmd = 'python users_to_projects.py --settings='+env.settings_file
    cmd+= " --user="+user+" --do="+do+" --activity="+activity
    
    if env.environment == 'development': 
        with lcd(env.project_path):
            local(cmd)
    else:
        with virtualenv():
            run(cmd)

def add_user_to_projects(user=None, activity=None):
    """Add user to projects: e.g. fab prod add_user_to_projects:user=username,activity=1.1"""
    _user_to_projects(user=user, do="add", activity=activity)

def remove_user_from_projects(user=None, activity=None):
    """Remove user form projects: e.g. fab prod remove_user_from_projects:user=username,activity=1.1"""
    _user_to_projects(user=user, do="remove", activity=activity)


def users_that_not_record_entries():
    """Prints active users that did not record any entry"""
    require('settings_file', provided_by=('dev', 'stag', 'prod'))
    cmd = 'python helpers/users_that_not_record_entries.py --settings='+env.settings_file
    
    if env.environment == 'development': 
        with lcd(env.project_path):
            local(cmd)
    else:
        with virtualenv():
            run(cmd)
