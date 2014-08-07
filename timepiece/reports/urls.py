from django.conf.urls import patterns, url
from timepiece.reports import views


def create_pattern(class_obj):
    report_filter, report_type = views.split_report_class(class_obj)
    regex = r'^reports/'+report_type+'/'+report_filter+'/$' # r'^reports/users_and_activities/agency/$'
    view = class_obj.as_view()
    url_name='report_'+report_filter+'_'+report_type # 'report_agency_users_and_activities'
    # url(regex, view, kwargs=None, name=None, prefix='')
    return url(regex, view, name=url_name)


urlpatterns = patterns('',
#     url(r'^reports/users_and_activities/my/$',
#         views.MyUsersAndActivitiesReport.as_view(),
#         name='report_my_users_and_activities'),
# 
#     url(r'^reports/users_and_activities/agency/$',
#         views.AgencyUsersAndActivitiesReport.as_view(),
#         name='report_agency_users_and_activities'),
)


for class_obj in views.get_report_classes():
    urlpatterns += patterns('', create_pattern(class_obj), )
