from fabric.api import *
from fabric.contrib.console import confirm
import os

PROJECT_PATH = "timepiece_project"
STATIC_ABSPATH = "/var/www/django/timepiece/timepiece/static"
SITEPACKAGES = "/var/www/.virtualenvs/timepiece/lib/python2.7/site-packages"

env.hosts = ['root@192.168.141.235']

def test():
    with settings(warn_only=True):
        result = local("./run_tests.py")
    if result.failed and not confirm("Tests failed. Continue anyway?"):
        abort("Aborting at user request.")

def commit():
    local("git add -p && git commit")

def push():
    local("git push")

def prepare_deploy():
    #test()
    commit()
    push()

def deploy():
    code_dir = '/var/www/django/timepiece'
    with settings(warn_only=True):
        if run("test -d %s" % code_dir).failed:
            run("git clone https://github.com/agadula/django-timepiece.git -b eu-osha %s" % code_dir)
            
            # copy the django admin static to website static folder
            run("cp -r "+SITEPACKAGES+"/django/contrib/admin/static/admin"+" "+STATIC_ABSPATH)
            
            # change permissions to let www-data create the CACHE folder
            run("chmod 775 "+STATIC_ABSPATH)

    with cd(code_dir):
        run("git pull")
        run("touch app.wsgi")
    apache_update_conf()
    
def full_deploy():
    prepare_deploy()
    deploy()

def apache_update_conf():
    """ upload apache configuration to remote host """
    #require('root', provided_by=('staging', 'production'))
    source = os.path.join(PROJECT_PATH, 'apache', 'production.conf')
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