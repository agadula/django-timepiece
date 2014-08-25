import csv
from dateutil.relativedelta import relativedelta
from itertools import groupby
import json
import inspect
import re

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import User
from django.db.models import Sum, Q, Min, Max
from django.http import HttpResponse
from django.shortcuts import render
from django.template.defaultfilters import date as date_format_filter
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from timepiece import utils
from timepiece.utils.csv import CSVViewMixin, DecimalEncoder

from timepiece.entries.models import Entry, ProjectHours, SimpleEntry
from timepiece.reports.forms import BillableHoursReportForm, HourlyReportForm,\
        ProductivityReportForm, PayrollSummaryReportForm, OshaReportForm
from timepiece.reports.utils import get_project_totals, get_payroll_totals,\
        generate_dates, get_week_window


class ReportMixin(object):
    """Common data for the Hourly & Billable Hours reports."""

    @method_decorator(permission_required('entries.add_entry'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Processes form data to get relevant entries & date_headers."""
        context = super(ReportMixin, self).get_context_data(**kwargs)

        form = self.get_form()
        if form.is_valid():
            data = form.cleaned_data
            start, end = form.save()
            entryQ = self.get_entry_query(start, end, data)
            trunc = data['trunc']
            if entryQ:
                vals = ('pk', 'activity', 'project', 'project__name',
                        'project__status', 'project__type__label')
                entries = Entry.objects.date_trunc(trunc,
                        extra_values=vals).filter(entryQ)
            else:
                entries = Entry.objects.none()

            end = end - relativedelta(days=1)
            date_headers = generate_dates(start, end, by=trunc)
            context.update({
                'from_date': start,
                'to_date': end,
                'date_headers': date_headers,
                'entries': entries,
                'filter_form': form,
                'trunc': trunc,
            })
        else:
            context.update({
                'from_date': None,
                'to_date': None,
                'date_headers': [],
                'entries': Entry.objects.none(),
                'filter_form': form,
                'trunc': '',
            })

        return context

    def get_entry_query(self, start, end, data):
        """Builds Entry query from form data."""
        # Entry types.
        incl_billable = data.get('billable', True)
        incl_nonbillable = data.get('non_billable', True)
        incl_leave = data.get('paid_leave', True)

        # If no types are selected, shortcut & return nothing.
        if not any((incl_billable, incl_nonbillable, incl_leave)):
            return None

        # All entries must meet time period requirements.
        basicQ = Q(end_time__gte=start, end_time__lt=end)

        # Filter by project for HourlyReport.
        projects = data.get('projects', None)
        basicQ &= Q(project__in=projects) if projects else Q()

        # Filter by user, activity, and project type for BillableReport.
        if 'users' in data:
            basicQ &= Q(user__in=data.get('users'))
        if 'activities' in data:
            basicQ &= Q(activity__in=data.get('activities'))
        if 'project_types' in data:
            basicQ &= Q(project__type__in=data.get('project_types'))

        # If all types are selected, no further filtering is required.
        if all((incl_billable, incl_nonbillable, incl_leave)):
            return basicQ

        # Filter by whether a project is billable or non-billable.
        billableQ = None
        if incl_billable and not incl_nonbillable:
            billableQ = Q(activity__billable=True,
                    project__type__billable=True)
        if incl_nonbillable and not incl_billable:
            billableQ = Q(activity__billable=False) |\
                    Q(project__type__billable=False)

        # Filter by whether the entry is paid leave.
        leave_ids = utils.get_setting('TIMEPIECE_PAID_LEAVE_PROJECTS').values()
        leaveQ = Q(project__in=leave_ids)
        if incl_leave:
            extraQ = (leaveQ | billableQ) if billableQ else leaveQ
        else:
            extraQ = (~leaveQ & billableQ) if billableQ else ~leaveQ

        return basicQ & extraQ

    def get_headers(self, date_headers, from_date, to_date, trunc):
        """Adjust date headers & get range headers."""
        date_headers = list(date_headers)

        # Earliest date should be no earlier than from_date.
        if date_headers and date_headers[0] < from_date:
            date_headers[0] = from_date

        # When organizing by week or month, create a list of the range for
        # each date header.
        if date_headers and trunc != 'day':
            count = len(date_headers)
            range_headers = [0] * count
            for i in range(count - 1):
                range_headers[i] = (date_headers[i], date_headers[i + 1] -
                        relativedelta(days=1))
            range_headers[count - 1] = (date_headers[count - 1], to_date)
        else:
            range_headers = date_headers
        return date_headers, range_headers

    def get_previous_month(self):
        """Returns date range for the previous full month."""
        end = utils.get_month_start() - relativedelta(days=1)
        end = utils.to_datetime(end)
        start = utils.get_month_start(end)
        return start, end


class OshaBaseReport(ReportMixin, CSVViewMixin, TemplateView):
    template_name = 'timepiece/reports/osha.html'

    def convert_context_to_csv(self, context):
        """Convert the context dictionary into a CSV file."""
        report_type = self.get_report_type()
        is_special_report = report_type in ['users_and_projects', 'users_and_activities'] # columns for both user and project (or activity). without final row "Total"

        content = []
        date_headers = context['date_headers']

        headers = ['Name']
        if report_type == 'users_and_projects': headers.append('Project')
        if report_type == 'users_and_activities': headers.append('Activity')
        headers.extend([date.strftime('%m/%d/%Y') for date in date_headers])
        headers.append('Total')
        content.append(headers)

        summaries = context['summaries'] # list of tuples: [(title, summary), (title, summary), ..]

        for title, summary in summaries:
            if report_type == 'users_and_projects': project_or_activity_name = title.replace("Project: ", "")
            if report_type == 'users_and_activities': project_or_activity_name = title.replace("Activity: ", "")
            for rows, totals in summary:
                for user, user_id, hours in rows:
                    data = [user]
                    if is_special_report: data.append(project_or_activity_name)
                    data.extend(hours)
                    content.append(data)
                if not is_special_report:
                    total = ['Totals']
                    total.extend(totals)
                    content.append(total)
        return content

    @property
    def defaults(self):
        """Default filter form data when no GET data is provided."""
        end = utils.get_month_start(timezone.now())
        end-= relativedelta(days=1) # last day of the previous month
        start = utils.get_month_start(end)
#         # Set default date span to previous week.
#         (start, end) = get_week_window(timezone.now() - relativedelta(days=7))
        return {
            'from_date': start,
            'to_date': end,
            'trunc': 'month',
            'projects': [],
        }

    def get_entry_query(self, start, end, data):
        """Builds Entry query from form data."""

        # All entries must meet time period requirements.
        basicQ = Q(date__gte=start, date__lt=end)

        # Filter by project
        projects = data.get('projects', None)
        basicQ &= Q(project__in=projects) if projects else Q() # original

        # Filter by entries status
        include_non_confirmed = data.get('include_non_confirmed', False)
        if not include_non_confirmed: basicQ &= Q(status=SimpleEntry.VERIFIED)

#         # Filter by user, activity, and project type for BillableReport.
#         if 'users' in data:
#             basicQ &= Q(user__in=data.get('users'))
#         if 'activities' in data:
#             basicQ &= Q(activity__in=data.get('activities'))
#         if 'project_types' in data:
#             basicQ &= Q(project__type__in=data.get('project_types'))

        return basicQ

    def get(self, request, *args, **kwargs):
        context = self.get_context_data()
        export_as_csv = request.GET.get('export', False)
        if export_as_csv:
            kls = CSVViewMixin
        else:
            kls = TemplateView
        return kls.render_to_response(self, context)

    def get_context_data(self, **kwargs):
        context = {}

        form = self.get_form()
        if form.is_valid():
            data = form.cleaned_data
            start, end = form.save()
            entryQ = self.get_entry_query(start, end, data)
            trunc = data['trunc']
            if entryQ:
                vals = ('pk', 'project', 'project__name',
                        'project__status', 'project__type__label',
                        'project__business', 'project__business__name')
                entries = SimpleEntry.objects.date_trunc(trunc,
                        extra_values=vals).filter(entryQ)
            else:
                entries = SimpleEntry.objects.none()

            end = end - relativedelta(days=1)
            date_headers = generate_dates(start, end, by=trunc)
            context.update({
                'from_date': start,
                'to_date': end,
                'date_headers': date_headers,
                'entries': entries,
                'filter_form': form,
                'trunc': trunc,
            })
        else:
            context.update({
                'from_date': None,
                'to_date': None,
                'date_headers': [],
                'entries': SimpleEntry.objects.none(),
                'filter_form': form,
                'trunc': '',
            })


        # Sum the hours totals for each user & interval.
        entries = context['entries']
        date_headers = context['date_headers']

        self.summaries = []
        if context['entries']:
            self.run_report(context)


#             entries = entries.order_by('project__type__label', 'project__name',
#                     'project__id', 'date')
#
#             func = lambda x: x['project__type__label']
#             for label, group in groupby(entries, func): # group is a list of projects of the same type
#                 title = label + ' Projects'
#                 summaries.append(
#                     (title, get_project_totals(
#                         list(group),
#                         date_headers, 'total', total_column=True, by='project')
#                     )
#                 )

        # Adjust date headers & create range headers.
        from_date = context['from_date']
        from_date = utils.add_timezone(from_date) if from_date else None
        to_date = context['to_date']
        to_date = utils.add_timezone(to_date) if to_date else None
        trunc = context['trunc']
        date_headers, range_headers = self.get_headers(date_headers,
                from_date, to_date, trunc)

        context.update({
            'curr_name': self.get_report_name(), # e.g. my_activities OR agency_users_and_activities
            'curr_type': self.get_report_type(), # e.g. activities OR users_and_activities
            'nice_type': ' '.join( self.get_report_type().split('_') ), # e.g. activities OR users and activities
            'report_filters': self.get_report_filters(), # ['my', 'agency', 'cpu', ... ]
            'date_headers': date_headers,
            'summaries': self.summaries,
            'range_headers': range_headers,
        })
        return context

    def get_filename(self, context):
        request = self.request.GET.copy()
        from_date = request.get('from_date')
        to_date = request.get('to_date')
        prefix = self.get_report_name()
        return prefix+'_{0}_to_{1}_by_{2}'.format(from_date, to_date,
            context.get('trunc', ''))

    def get_report_name(self):
        return self.get_name_prefix()+'_'+self.get_report_type()
    
    def get_report_filters(self):
        curr_report_type = self.get_report_type() # users_activities 
        curr_report_class = get_report_class_naming(curr_report_type) # users_and_activities > UsersAndActivities
        curr_report_class = 'UsersAndActivities'

        filters = []
        for class_obj in get_report_classes(that_contain=curr_report_class):
            report_filter, report_type = split_report_class(class_obj)
            visible = self.is_filter_visible_by_the_user(report_filter, curr_report_type)
            
            if report_filter == 'my': priority=1
            elif report_filter == 'agency': priority=2
            elif report_filter in ['cpu', 'net', 'rsc', 'pru']: priority=3
            else: priority=4
            
            filter_data = {'name':report_filter, 'priority':priority, 'visible':visible}
            if not filter_data in filters:
                filters.append(filter_data)

        sorted_filters = sorted(filters, key=lambda x: x['priority'])
        return sorted_filters

    def is_filter_visible_by_the_user(self, report_filter, report_type): # agency, users_and_activities
        result = False
        if report_type in ['projects', 'activities']:
            result = True
        else:
            user = self.request.user
            if user.has_perm('entries.view_some_report'):
                if user.has_perm('entries.view_all_report') or report_filter=='my':
                    result = True
                else:
                    permission = 'entries.view_'+report_filter+'_report' # view_cpu_report
                    result = user.has_perm(permission)
        return result

    def get_form(self):
        data = self.request.GET or self.defaults
        data = data.copy()  # make mutable
        return OshaReportForm(data)

    def filter_entries(self, entries):
        return entries.filter(user__in=self.accessible_users())



class ProjectsReportMixin(OshaBaseReport):
    def get_report_type(self):
        return 'projects'

    def run_report(self, context):
        entries = self.filter_entries(context['entries'])
        date_headers = context['date_headers']

        self.summaries.append(('By Project', get_project_totals(
                entries.order_by('project__name', 'project__id', 'date'),
                date_headers, 'total', total_column=True, by='project')))


class ActivitiesReportMixin(OshaBaseReport):
    def get_report_type(self):
        return 'activities'

    def run_report(self, context):
        entries = self.filter_entries(context['entries'])
        date_headers = context['date_headers']
        self.summaries.append(('By Activity', get_project_totals(
                entries.order_by('project__business__name', 'project__business__id', 'date'),
                date_headers, 'total', total_column=True, by='project__business__name')))


class UsersReportMixin(OshaBaseReport):        
    def get_report_type(self):
        return 'users'

    def run_report(self, context):
        entries = self.filter_entries(context['entries'])
        date_headers = context['date_headers']
        include_users_without_entries = True

        summary_by_user = get_project_totals(
                entries.order_by('user__last_name', 'user__id', 'date'),
                date_headers, 'total', total_column=True, by='user')

        if include_users_without_entries:
            all_users = list( self.accessible_users() )
            entries.order_by('user')

            users_with_entries = []
            func = lambda x: x['user']
            for user_id, group in groupby(entries, func):
                user = User.objects.get(id=user_id)
                if user not in users_with_entries:
                    users_with_entries.append(user)

            # remove non active users and the admin user
            users_without_entries = []
            for u in all_users:
                if u not in users_with_entries and u.is_active and u.username != "admin":
                    users_without_entries.append(u)

            summary_by_user_also_without_entries = []
            rows = []
            for curr_rows, curr_totals in summary_by_user:
                for name, pk, hours in curr_rows:
                    row = (name, pk, hours)
                    rows.append(row)
                totals = curr_totals

            for user in users_without_entries:
                name = user.first_name + " " + user.last_name
                pk = user.id
                hours = ['' for date in date_headers]
                hours.append('')
                rows.append( (name, pk, hours) )

            summary_by_user_also_without_entries.append( (rows, totals) )
            summary_by_user = summary_by_user_also_without_entries

        self.summaries.append(('By User', summary_by_user))


class UsersAndProjectsReportMixin(OshaBaseReport):
    def get_report_type(self):
        return 'users_and_projects'

    def run_report(self, context):
        entries = context['entries'].filter(user__in=self.accessible_users() )
        entries = entries.order_by('project__name',
                'project__id', 'user__last_name', 'user__id', 'date')

        func = lambda x: x['project__name']
        for label, group in groupby(entries, func):
            title = 'Project: ' + label
            self.summaries.append(
                (title, get_project_totals(
                    list(group),
                    context['date_headers'], 'total', total_column=True, by='user')
                )
            )


class UsersAndActivitiesReportMixin(OshaBaseReport):
    def get_report_type(self):
        return 'users_and_activities'

    def run_report(self, context):
        entries = context['entries'].filter(user__in=self.accessible_users() )
        entries = entries.order_by('project__business__name',
                'project__business__id', 'user__last_name', 'user__id', 'date')

        func = lambda x: x['project__business__name']
        for label, group in groupby(entries, func):
            title = 'Activity: ' + label
            self.summaries.append(
                (title, get_project_totals(
                    list(group),
                    context['date_headers'], 'total', total_column=True, by='user')
                )
            )



class MyReportMixin():
    def get_name_prefix(self):
        return 'my'

    def accessible_users(self):
        return User.objects.filter(username=self.request.user.username)


class MyProjectsReport(ProjectsReportMixin, MyReportMixin):
    pass

class MyActivitiesReport(ActivitiesReportMixin, MyReportMixin):
    pass

class MyUsersReport(UsersReportMixin, MyReportMixin):
    @method_decorator(permission_required('entries.view_some_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

class MyUsersAndActivitiesReport(UsersAndActivitiesReportMixin, MyReportMixin):
    @method_decorator(permission_required('entries.view_some_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

class MyUsersAndProjectsReport(UsersAndProjectsReportMixin, MyReportMixin):
    @method_decorator(permission_required('entries.view_some_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)



class AgencyReportMixin():
    def get_name_prefix(self):
        return 'agency'

    def accessible_users(self):
        return User.objects.all().distinct().order_by('last_name')


class AgencyProjectsReport(ProjectsReportMixin, AgencyReportMixin):
    pass

class AgencyActivitiesReport(ActivitiesReportMixin, AgencyReportMixin):
    pass

class AgencyUsersReport(UsersReportMixin, AgencyReportMixin):
    @method_decorator(permission_required('entries.view_agency_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

class AgencyUsersAndActivitiesReport(UsersAndActivitiesReportMixin, AgencyReportMixin):
    @method_decorator(permission_required('entries.view_agency_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

class AgencyUsersAndProjectsReport(UsersAndProjectsReportMixin, AgencyReportMixin):
    @method_decorator(permission_required('entries.view_agency_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)



class CpuReportMixin():
    def get_name_prefix(self):
        return 'cpu'

    def accessible_users(self):
        return User.objects.filter(groups__name__in=['G-INF']).distinct().order_by('last_name')


class CpuProjectsReport(ProjectsReportMixin, CpuReportMixin):
    pass

class CpuActivitiesReport(ActivitiesReportMixin, CpuReportMixin):
    pass

class CpuUsersReport(UsersReportMixin, CpuReportMixin):
    @method_decorator(permission_required('entries.view_cpu_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

class CpuUsersAndActivitiesReport(UsersAndActivitiesReportMixin, CpuReportMixin):
    @method_decorator(permission_required('entries.view_cpu_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

class CpuUsersAndProjectsReport(UsersAndProjectsReportMixin, CpuReportMixin):
    @method_decorator(permission_required('entries.view_cpu_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)



class NetReportMixin():
    def get_name_prefix(self):
        return 'net'

    def accessible_users(self):
        return User.objects.filter(groups__name__in=['G-NET']).distinct().order_by('last_name')


class NetProjectsReport(ProjectsReportMixin, NetReportMixin):
    pass

class NetActivitiesReport(ActivitiesReportMixin, NetReportMixin):
    pass

class NetUsersReport(UsersReportMixin, NetReportMixin):
    @method_decorator(permission_required('entries.view_net_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

class NetUsersAndActivitiesReport(UsersAndActivitiesReportMixin, NetReportMixin):
    @method_decorator(permission_required('entries.view_net_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

class NetUsersAndProjectsReport(UsersAndProjectsReportMixin, NetReportMixin):
    @method_decorator(permission_required('entries.view_net_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)



class PruReportMixin():
    def get_name_prefix(self):
        return 'pru'

    def accessible_users(self):
        return User.objects.filter(groups__name__in=['G-PRU']).distinct().order_by('last_name')


class PruProjectsReport(ProjectsReportMixin, PruReportMixin):
    pass

class PruActivitiesReport(ActivitiesReportMixin, PruReportMixin):
    pass

class PruUsersReport(UsersReportMixin, PruReportMixin):
    @method_decorator(permission_required('entries.view_pru_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

class PruUsersAndActivitiesReport(UsersAndActivitiesReportMixin, PruReportMixin):
    @method_decorator(permission_required('entries.view_pru_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

class PruUsersAndProjectsReport(UsersAndProjectsReportMixin, PruReportMixin):
    @method_decorator(permission_required('entries.view_pru_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)



class RscReportMixin():
    def get_name_prefix(self):
        return 'rsc'

    def accessible_users(self):
        return User.objects.filter(groups__name__in=['G-ADM']).distinct().order_by('last_name')


class RscProjectsReport(ProjectsReportMixin, RscReportMixin):
    pass

class RscActivitiesReport(ActivitiesReportMixin, RscReportMixin):
    pass

class RscUsersReport(UsersReportMixin, RscReportMixin):
    @method_decorator(permission_required('entries.view_rsc_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

class RscUsersAndActivitiesReport(UsersAndActivitiesReportMixin, RscReportMixin):
    @method_decorator(permission_required('entries.view_rsc_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

class RscUsersAndProjectsReport(UsersAndProjectsReportMixin, RscReportMixin):
    @method_decorator(permission_required('entries.view_rsc_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)



class IctReportMixin():
    def get_name_prefix(self):
        return 'ict'

    def accessible_users(self):
        return User.objects.filter(groups__name__in=['G-ABB-ICT']).distinct().order_by('last_name')


class IctProjectsReport(ProjectsReportMixin, IctReportMixin):
    pass

class IctActivitiesReport(ActivitiesReportMixin, IctReportMixin):
    pass

class IctUsersReport(UsersReportMixin, IctReportMixin):
    @method_decorator(permission_required('entries.view_ict_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

class IctUsersAndActivitiesReport(UsersAndActivitiesReportMixin, IctReportMixin):
    @method_decorator(permission_required('entries.view_ict_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)

class IctUsersAndProjectsReport(UsersAndProjectsReportMixin, IctReportMixin):
    @method_decorator(permission_required('entries.view_ict_report'))
    def dispatch(self, request, *args, **kwargs):
        return super(ReportMixin, self).dispatch(request, *args, **kwargs)




def get_report_classes(that_contain=None):
    import sys
    classes = []
    for name, obj in inspect.getmembers(sys.modules[__name__], inspect.isclass):
        if (not 'Base' in name) and (not 'Mixin' in name) and (name.endswith('Report')):
            if that_contain and that_contain in name:
                classes.append(obj)
            elif not that_contain:
                classes.append(obj)
    return classes

def split_report_class(class_obj):
    class_name = class_obj.__name__.replace('Report','')     # AgencyUsersAndActivitiesReport > AgencyUsersAndActivities
    class_name_elems = re.findall('[A-Z][a-z]*', class_name) # AgencyUsersAndActivities > [Agency, Users, And, Activities]
    report_filter = class_name_elems[0].lower()              # Agency > agency
    report_type = '_'.join(class_name_elems[1:]).lower()     # [Users, And, Activities] > users_and_activities
    return report_filter, report_type                        # agency, users_and_activities

def get_report_class_naming(report_type):
    elems = report_type.split('_') # users_and_activities > [users, and, activities]
    elems = [elem.capitalize() for elem in elems] # [users, and, activities] > [Users, And, Activities]
    result = ''.join(elems) # [Users, And, Activities] > UsersAndActivities
    return result
