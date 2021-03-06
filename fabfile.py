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
def _virtualenv():
    require('project_path', provided_by=('dev', 'stag', 'prod'))
    with cd(env.project_path):
        with prefix(env.activate):
            yield

def dev():
    """ use development environment on localhost"""
    env.environment = 'development'
    env.activate = 'source ~/.virtualenvs/timepiece/bin/activate'
    env.settings_file = "settings.local"
    CODE_PATH = os.path.dirname(os.path.realpath(__file__))
    env.project_path = os.path.join(CODE_PATH, "timepiece_project")

def _stag_and_prod():
    env.activate = 'source /var/www/.virtualenvs/timepiece/bin/activate'
    env.settings_file = "settings.production"
    env.project_path = os.path.join(CODE_PATH, "timepiece_project")

def stag():
    """ use staging environment on remote host"""
    env.environment = 'staging'
    env.hosts = ['root@192.168.141.235']
    _stag_and_prod()

def prod():
    """ use production environment on remote host"""
    env.environment = 'production'
    env.hosts = ['root@192.168.141.11']
    _stag_and_prod()


# LOCAL COMMANDS
def test():
    '''runs all the tests'''
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
        with _virtualenv():
            run('python manage.py shell --settings='+env.settings_file )

def shell_plus():
    if env.environment == 'development':
        local("python timepiece_project/manage.py shell_plus --ipython")
    else:
        with _virtualenv():
            run('python manage.py shell_plus --ipython --settings='+env.settings_file )


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
        if env.environment == 'staging':
#             write in the banner menu that it's test version
            filename = os.path.join(CODE_PATH, 'timepiece/templates/timepiece/navigation.html')
            run("git checkout "+filename)
            run("git pull")
            before = '>Timepiece<'
            after = 'style="color: red;">Timepiece TEST<'
            sed(filename, before, after)
        else:
            run("git pull")
        run("touch app.wsgi")
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
    """ show the tail of Apache error.log on remote host """
    run('tail /var/log/apache2/error.log')

def _create_user_in_db():
#     CHECK IF USER ALREADY EXISTS IN THE DB
#     psql postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='USR_NAME'"
#     Yields 1 if found and nothing else.
    with settings(warn_only=True):
        result = run('sudo -u postgres createuser {} -P'.format(db_user) )
    if result.failed and not confirm("Creation of role failed. Continue anyway?"):
        abort("Aborting at user request.")

def  _create_db_on_linux():
    run('sudo -u {} createdb -E utf8 -O {} {} -T template0'.format(linux_user, db_user, db_name) )

def _remove_db_if_exists():
    with settings(warn_only=True):
        cmd = 'dropdb '+db_name
        if confirm("WARNING! You are removing the "+env.environment+" DB. Continue?"):
            if env.environment == 'development':
                result = local(cmd)
            else:
                result = run('sudo -u '+db_user+' '+cmd)
        else:
            abort("Aborting at user request.")

        if result.failed and not confirm("Remove of DB failed. Continue anyway?"):
            abort("Aborting at user request.")

def createdb():
    """Removes DB, creates user, creates DB"""
    _remove_db_if_exists()
    _create_user_in_db()
    _create_db_on_linux()

def backupdb():
    """Copy locally a DB backup"""
    cmd = 'pg_dump {} > {}'.format(db_name, db_backup_file)
    if env.environment == 'development':
        local(cmd)
    else:
        # pg_dump -U {user-name} {source_db} -f {dumpfilename.sql}
        run('sudo -u postgres '+cmd )
        get(db_backup_file, db_backup_file)
        run("rm "+db_backup_file)

def restoredb():
    """Restores the db from the local backup file"""
    # psql -U {user-name} -d {desintation_db} -f {dumpfilename.sql}
    restore_cmd = 'psql {} < {}'.format(db_name, db_backup_file)
    _remove_db_if_exists()
    if env.environment == 'development':
        local('psql --command="CREATE DATABASE {}"'.format(db_name) )
        local(restore_cmd)
    else:
        _create_db_on_linux()
        put(db_backup_file, db_backup_file)
        run('sudo -u '+db_user+' '+restore_cmd)
        run("rm "+db_backup_file)

def syncdb():
    require('settings_file', provided_by=('dev', 'stag', 'prod'))
    cmd = 'python manage.py syncdb --settings='+env.settings_file
    if env.environment == 'development':
        with lcd(env.project_path):
            local(cmd)
    else:
        with _virtualenv():
            run(cmd)

def obfuscatedb():
    '''Randomizes the owner of each entry'''
    require('settings_file', provided_by=('dev', 'stag', 'prod'))
    cmd = 'python obfuscatedb.py --settings='+env.settings_file
    if env.environment == 'development':
        with lcd(env.project_path):
            local(cmd)
    else:
        with _virtualenv():
            run(cmd)

def loaddata(fixture):
    with _virtualenv():
        run('python manage.py loaddata '+fixture+' --settings='+env.settings_file )


def _ldap_users_and_groups(do):
    require('settings_file', provided_by=('dev', 'stag', 'prod'))
    cmd = 'python ldap_users_and_groups.py'
    cmd+= ' --settings='+env.settings_file
    cmd+= " --do="+do
    if env.environment == 'development':
        with lcd(env.project_path):
            local(cmd)
    else:
        with _virtualenv():
            run(cmd)

def ldap_users_and_groups_sync():
    '''Creates Users and Groups if necessary, synchronises Users and Groups relations. Runs ldap_users_and_groups_prepare_permissions_and_groups.'''
    _ldap_users_and_groups('sync')

def ldap_users_and_groups_prepare_permissions_and_groups():
    '''Prepares the needed Groups and Permissions.'''
    _ldap_users_and_groups('preparedb')

def ldap_users_and_groups_test():
    _ldap_users_and_groups('test')


def _user_to_activity(user=None, do=None, activity=None):
    require('settings_file', provided_by=('dev', 'stag', 'prod'))
    cmd = 'python user_to_activity.py --settings='+env.settings_file
    cmd+= " --user="+user+" --do="+do+" --activity="+activity
    if env.environment == 'development':
        with lcd(env.project_path):
            local(cmd)
    else:
        with _virtualenv():
            run(cmd)

def add_user_to_activity(user=None, activity=None):
    """Add user to activity: e.g. fab prod add_user_to_activity:user=username,activity=1.1"""
    _user_to_activity(user=user, do="add", activity=activity)

def remove_user_from_activity(user=None, activity=None):
    """Remove user from activity: e.g. fab prod remove_user_from_activity:user=username,activity=1.1"""
    _user_to_activity(user=user, do="remove", activity=activity)
