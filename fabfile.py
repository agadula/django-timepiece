import os

from fabric.api import *
from fabric.contrib.console import confirm
from contextlib import contextmanager as _contextmanager



STATIC_ABSPATH = "/var/www/django/timepiece/timepiece/static"
SITEPACKAGES = "/var/www/.virtualenvs/timepiece/lib/python2.7/site-packages"
CODE_PATH = "/var/www/django/timepiece"



@_contextmanager
def virtualenv():
    require('project_path', provided_by=('dev', 'stag', 'prod'))
    with cd(env.project_path):
        with prefix(env.activate):
            yield

def dev():
    env.environment = 'development'
    env.activate = 'source /Users/simonegentilini/.virtualenvs/timepiece_env/bin/activate'
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
    local("python timepiece_project/manage.py shell")

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
    apache_update_conf()

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

def createdb():
    db_name = "timepiece"
    db_user = "gentisi"
    linux_user = db_user

#     CHECK IF DB ALREADY EXISTS    
#     psql -lqt | cut -d \| -f 1 | grep -w <DB_NAME> | wc -l
    with settings(warn_only=True):
        result = run("sudo -u {} dropdb '{}'".format(db_user, db_name) )
    if result.failed and not confirm("Remove of db failed. Continue anyway?"):
        abort("Aborting at user request.")

#     CHECK IF USER ALREADY EXISTS IN THE DB
#     psql postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='USR_NAME'"
#     Yields 1 if found and nothing else.
    with settings(warn_only=True):
        result = run('sudo -u postgres createuser {} -P'.format(db_user) )
    if result.failed and not confirm("Creation of role failed. Continue anyway?"):
        abort("Aborting at user request.")

    run('sudo -u {} createdb -E utf8 -O {} {} -T template0'.format(linux_user, db_user, db_name) )
    syncdb()

def syncdb():
    with virtualenv():
        run('python manage.py syncdb --settings='+env.settings_file )
        run('python manage.py loaddata users.yaml activities-projects.yaml --settings='+env.settings_file )

def ldap_users_to_db():
    with virtualenv():
        run('python ldap_users_to_db.py')

def users_to_projects(user=None, activity=None):
    """Assign users to projects"""
    require('settings_file', provided_by=('dev', 'stag', 'prod'))
    cmd = 'python users_to_projects.py --settings='+env.settings_file
    if user and activity:
        cmd+= " --user="+user+" --activity="+activity
    
    if env.environment == 'development': 
        with lcd(env.project_path):
            local(cmd)
    else:
        with virtualenv():
            run(cmd)

def users_that_not_record_entries():
    """Prints active users that did not record any entry"""
    import sys
    require('settings_file', provided_by=('dev', 'stag', 'prod'))
    sys.path.append(os.path.abspath(os.path.dirname(__file__)))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "timepiece_project."+env.settings_file)
    from django.contrib.auth.models import User
    from timepiece.entries.models import SimpleEntry
    
    users = User.objects.all()
    for u in users:
        if not u.simple_entries.all() and u.is_active:
            print "("+u.username+") "+u.first_name+" "+u.last_name
