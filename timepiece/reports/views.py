import csv
from dateutil.relativedelta import relativedelta
from itertools import groupby
import json

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

    @method_decorator(permission_required('entries.view_entry_summary'))
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


class HourlyReport(ReportMixin, CSVViewMixin, TemplateView):
    template_name = 'timepiece/reports/hourly.html'

    def convert_context_to_csv(self, context):
        """Convert the context dictionary into a CSV file."""
        content = []
        date_headers = context['date_headers']

        headers = ['Name']
        headers.extend([date.strftime('%m/%d/%Y') for date in date_headers])
        headers.append('Total')
        content.append(headers)

        if self.export_projects:
            key = 'By Project'
        else:
            key = 'By User'

        summaries = context['summaries']
        summary = summaries[key] if key in summaries else []
        for rows, totals in summary:
            for name, user_id, hours in rows:
                data = [name]
                data.extend(hours)
                content.append(data)
            total = ['Totals']
            total.extend(totals)
            content.append(total)
        return content

    @property
    def defaults(self):
        """Default filter form data when no GET data is provided."""
        # Set default date span to previous week.
        (start, end) = get_week_window(timezone.now() - relativedelta(days=7))
        return {
            'from_date': start,
            'to_date': end,
            'billable': True,
            'non_billable': False,
            'paid_leave': False,
            'trunc': 'day',
            'projects': [],
        }

    def get(self, request, *args, **kwargs):
        self.export_users = request.GET.get('export_users', False)
        self.export_projects = request.GET.get('export_projects', False)
        context = self.get_context_data()
        if self.export_users or self.export_projects:
            kls = CSVViewMixin
        else:
            kls = TemplateView
        return kls.render_to_response(self, context)

    def get_context_data(self, **kwargs):
        context = super(HourlyReport, self).get_context_data(**kwargs)

        # Sum the hours totals for each user & interval.
        entries = context['entries']
        date_headers = context['date_headers']

        summaries = []
        if context['entries']:
            summaries.append(('By User', get_project_totals(
                    entries.order_by('user__last_name', 'user__id', 'date'),
                    date_headers, 'total', total_column=True, by='user')))

            entries = entries.order_by('project__type__label', 'project__name',
                    'project__id', 'date')
            func = lambda x: x['project__type__label']
            for label, group in groupby(entries, func):
                title = label + ' Projects'
                summaries.append((title, get_project_totals(list(group),
                        date_headers, 'total', total_column=True, by='project')))

        # Adjust date headers & create range headers.
        from_date = context['from_date']
        from_date = utils.add_timezone(from_date) if from_date else None
        to_date = context['to_date']
        to_date = utils.add_timezone(to_date) if to_date else None
        trunc = context['trunc']
        date_headers, range_headers = self.get_headers(date_headers,
                from_date, to_date, trunc)

        context.update({
            'date_headers': date_headers,
            'summaries': summaries,
            'range_headers': range_headers,
        })
        return context

    def get_filename(self, context):
        request = self.request.GET.copy()
        from_date = request.get('from_date')
        to_date = request.get('to_date')
        return 'hours_{0}_to_{1}_by_{2}.csv'.format(from_date, to_date,
            context.get('trunc', ''))

    def get_form(self):
        data = self.request.GET or self.defaults
        data = data.copy()  # make mutable
        # Fix booleans - the strings "0" and "false" are True in Python
        for key in ['billable', 'non_billable', 'paid_leave']:
            data[key] = key in data and \
                        str(data[key]).lower() in ('on', 'true', '1')

        return HourlyReportForm(data)


class BillableHours(ReportMixin, TemplateView):
    template_name = 'timepiece/reports/billable_hours.html'

    @property
    def defaults(self):
        """Default filter form data when no GET data is provided."""
        start, end = self.get_previous_month()
        return {
            'from_date': start,
            'to_date': end,
            'trunc': 'week',
        }

    def get_context_data(self, **kwargs):
        context = super(BillableHours, self).get_context_data(**kwargs)

        entries = context['entries']
        date_headers = context['date_headers']
        data_map = self.get_hours_data(entries, date_headers)

        from_date = context['from_date']
        to_date = context['to_date']
        trunc = context['trunc']
        kwargs = {trunc + 's': 1}  # For relativedelta

        keys = sorted(data_map.keys())
        data_list = [['Date', 'Billable', 'Non-billable']]
        for i in range(len(keys)):
            start = keys[i]
            start = start if start >= from_date else from_date
            end = start + relativedelta(**kwargs) - relativedelta(days=1)
            end = end if end <= to_date else to_date

            if start != end:
                label = ' - '.join([date_format_filter(d, 'M j') for d in (start, end)])
            else:
                label = date_format_filter(start, 'M j')
            billable = data_map[keys[i]]['billable']
            nonbillable = data_map[keys[i]]['nonbillable']
            data_list.append([label, billable, nonbillable])

        context.update({
            'data': json.dumps(data_list, cls=DecimalEncoder),
        })
        return context

    def get_form(self):
        if self.request.GET:
            return BillableHoursReportForm(self.request.GET)
        else:
            # Select all available users, activities, and project types.
            return BillableHoursReportForm(self.defaults,
                    select_all=True)

    def get_hours_data(self, entries, date_headers):
        """Sum billable and non-billable hours across all users."""
        project_totals = get_project_totals(entries, date_headers,
                total_column=False) if entries else []

        data_map = {}
        for rows, totals in project_totals:
            for user, user_id, periods in rows:
                for period in periods:
                    day = period['day']
                    if day not in data_map:
                        data_map[day] = {'billable': 0, 'nonbillable': 0}
                    data_map[day]['billable'] += period['billable']
                    data_map[day]['nonbillable'] += period['nonbillable']

        return data_map


@permission_required('entries.view_payroll_summary')
def report_payroll_summary(request):
    date = timezone.now() - relativedelta(months=1)
    from_date = utils.get_month_start(date).date()
    to_date = from_date + relativedelta(months=1)

    year_month_form = PayrollSummaryReportForm(request.GET or None,
        initial={'month': from_date.month, 'year': from_date.year})

    if year_month_form.is_valid():
        from_date, to_date = year_month_form.save()
    last_billable = utils.get_last_billable_day(from_date)
    projects = utils.get_setting('TIMEPIECE_PAID_LEAVE_PROJECTS')
    weekQ = Q(end_time__gt=utils.get_week_start(from_date),
              end_time__lt=last_billable + relativedelta(days=1))
    monthQ = Q(end_time__gt=from_date, end_time__lt=to_date)
    workQ = ~Q(project__in=projects.values())
    statusQ = Q(status=Entry.INVOICED) | Q(status=Entry.APPROVED)
    # Weekly totals
    week_entries = Entry.objects.date_trunc('week').filter(
        weekQ, statusQ, workQ
    )
    date_headers = generate_dates(from_date, last_billable, by='week')
    weekly_totals = list(get_project_totals(week_entries, date_headers,
                                              'total', overtime=True))
    # Monthly totals
    leave = Entry.objects.filter(monthQ, ~workQ
                                  ).values('user', 'hours', 'project__name')
    extra_values = ('project__type__label',)
    month_entries = Entry.objects.date_trunc('month', extra_values)
    month_entries_valid = month_entries.filter(monthQ, statusQ, workQ)
    labels, monthly_totals = get_payroll_totals(month_entries_valid, leave)
    # Unapproved and unverified hours
    entries = Entry.objects.filter(monthQ).order_by()  # No ordering
    user_values = ['user__pk', 'user__first_name', 'user__last_name']
    unverified = entries.filter(status=Entry.UNVERIFIED, user__is_active=True) \
                        .values_list(*user_values).distinct()
    unapproved = entries.filter(status=Entry.VERIFIED) \
                        .values_list(*user_values).distinct()
    return render(request, 'timepiece/reports/payroll_summary.html', {
        'from_date': from_date,
        'year_month_form': year_month_form,
        'date_headers': date_headers,
        'weekly_totals': weekly_totals,
        'monthly_totals': monthly_totals,
        'unverified': unverified,
        'unapproved': unapproved,
        'labels': labels,
    })


@permission_required('entries.view_entry_summary')
def report_productivity(request):
    report = []
    organize_by = None

    form = ProductivityReportForm(request.GET or None)
    if form.is_valid():
        project = form.cleaned_data['project']
        organize_by = form.cleaned_data['organize_by']
        export = request.GET.get('export', False)

        actualsQ = Q(project=project, end_time__isnull=False)
        actuals = Entry.objects.filter(actualsQ)
        projections = ProjectHours.objects.filter(project=project)
        entry_count = actuals.count() + projections.count()

        if organize_by == 'week' and entry_count > 0:
            # Determine the project's time range.
            amin, amax, pmin, pmax = (None, None, None, None)
            if actuals.count() > 0:
                amin = actuals.aggregate(Min('start_time')).values()[0]
                amin = utils.get_week_start(amin).date()
                amax = actuals.aggregate(Max('start_time')).values()[0]
                amax = utils.get_week_start(amax).date()
            if projections.count() > 0:
                pmin = projections.aggregate(Min('week_start')).values()[0]
                pmax = projections.aggregate(Max('week_start')).values()[0]
            current = min(amin, pmin) if (amin and pmin) else (amin or pmin)
            latest = max(amax, pmax) if (amax and pmax) else (amax or pmax)

            # Report for each week during the project's time range.
            while current <= latest:
                next_week = current + relativedelta(days=7)
                actual_hours = actuals.filter(start_time__gte=current,
                        start_time__lt=next_week).aggregate(
                        Sum('hours')).values()[0]
                projected_hours = projections.filter(week_start__gte=current,
                        week_start__lt=next_week).aggregate(
                        Sum('hours')).values()[0]
                report.append([date_format_filter(current, 'M j, Y'),
                        actual_hours or 0, projected_hours or 0])
                current = next_week

        elif organize_by == 'user' and entry_count > 0:
            # Determine all users who worked on or were assigned to the
            # project.
            vals = ('user', 'user__first_name', 'user__last_name')
            ausers = list(actuals.values_list(*vals).distinct())
            pusers = list(projections.values_list(*vals).distinct())
            key = lambda x: (x[1] + x[2]).lower()  # Sort by name
            users = sorted(list(set(ausers + pusers)), key=key)

            # Report for each user.
            for user in users:
                name = '{0} {1}'.format(user[1], user[2])
                actual_hours = actuals.filter(user=user[0]) \
                        .aggregate(Sum('hours')).values()[0]
                projected_hours = projections.filter(user=user[0]) \
                        .aggregate(Sum('hours')).values()[0]
                report.append([name, actual_hours or 0, projected_hours or 0])

        col_headers = [organize_by.title(), 'Worked Hours', 'Assigned Hours']
        report.insert(0, col_headers)

        if export:
            response = HttpResponse(content_type='text/csv')
            filename = '{0}_productivity'.format(project.name)
            content_disp = 'attachment; filename={0}.csv'.format(filename)
            response['Content-Disposition'] = content_disp
            writer = csv.writer(response)
            for row in report:
                writer.writerow(row)
            return response

    return render(request, 'timepiece/reports/productivity.html', {
        'form': form,
        'report': json.dumps(report, cls=DecimalEncoder),
        'type': organize_by or '',
        'total_worked': sum([r[1] for r in report[1:]]),
        'total_assigned': sum([r[2] for r in report[1:]]),
    })


class OshaBaseReport(ReportMixin, CSVViewMixin, TemplateView):
    template_name = 'timepiece/reports/osha.html'

    def convert_context_to_csv(self, context):
        """Convert the context dictionary into a CSV file."""
        report_type = self.get_report_type()
        is_special_report = report_type in ['users_projects', 'users_activities'] # columns for both user and project (or activity). without final row "Total"

        content = []
        date_headers = context['date_headers']

        headers = ['Name']
        if report_type == 'users_projects': headers.append('Project')
        if report_type == 'users_activities': headers.append('Activity')
        headers.extend([date.strftime('%m/%d/%Y') for date in date_headers])
        headers.append('Total')
        content.append(headers)

        summaries = context['summaries'] # list of tuples: [(title, summary), (title, summary), ..]

        for title, summary in summaries:
            if report_type == 'users_projects': project_or_activity_name = title.replace("Project: ", "")
            if report_type == 'users_activities': project_or_activity_name = title.replace("Activity: ", "")
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
            'report_type': self.get_report_type(),
            'date_headers': date_headers,
            'summaries': self.summaries,
            'range_headers': range_headers,
        })
        return context

    def get_filename(self, context):
        request = self.request.GET.copy()
        from_date = request.get('from_date')
        to_date = request.get('to_date')
        prefix = self.get_report_type()
        return prefix+'_{0}_to_{1}_by_{2}'.format(from_date, to_date,
            context.get('trunc', ''))

    def get_form(self):
        data = self.request.GET or self.defaults
        data = data.copy()  # make mutable
        return OshaReportForm(data)


class UsersReport(OshaBaseReport):
    def get_report_type(self):
        return 'users'

    def run_report(self, context):
        entries = context['entries']
        date_headers = context['date_headers']
        include_users_without_entries = True

        summary_by_user = get_project_totals(
                entries.order_by('user__last_name', 'user__id', 'date'),
                date_headers, 'total', total_column=True, by='user')

        if include_users_without_entries:
            all_users = list( User.objects.all() )
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


class ProjectsReport(OshaBaseReport):
    def get_report_type(self):
        return 'projects'

    def run_report(self, context):
        entries = context['entries']
        date_headers = context['date_headers']

        self.summaries.append(('By Project', get_project_totals(
                entries.order_by('project__name', 'project__id', 'date'),
                date_headers, 'total', total_column=True, by='project')))


class ActivitiesReport(OshaBaseReport):
    def get_report_type(self):
        return 'activities'

    def run_report(self, context):
        entries = context['entries']
        date_headers = context['date_headers']
        self.summaries.append(('By Activity', get_project_totals(
                entries.order_by('project__business__name', 'project__business__id', 'date'),
                date_headers, 'total', total_column=True, by='project__business__name')))


class UsersActivitiesReport(OshaBaseReport):
    def get_report_type(self):
        return 'users_activities'

    def run_report(self, context):
        entries = context['entries']
        date_headers = context['date_headers']

        entries = entries.order_by('project__business__name',
                'project__business__id', 'user__last_name', 'user__id', 'date')

        func = lambda x: x['project__business__name']
        for label, group in groupby(entries, func):
            title = 'Activity: ' + label
            self.summaries.append(
                (title, get_project_totals(
                    list(group),
                    date_headers, 'total', total_column=True, by='user')
                )
            )


class UsersProjectsReport(OshaBaseReport):
    def get_report_type(self):
        return 'users_projects'

    def run_report(self, context):
        entries = context['entries']
        date_headers = context['date_headers']

        entries = entries.order_by('project__name',
                'project__id', 'user__last_name', 'user__id', 'date')

        func = lambda x: x['project__name']
        for label, group in groupby(entries, func):
            title = 'Project: ' + label
            self.summaries.append(
                (title, get_project_totals(
                    list(group),
                    date_headers, 'total', total_column=True, by='user')
                )
            )



class OshaReport(ReportMixin, CSVViewMixin, TemplateView):
    template_name = 'timepiece/reports/osha.html'

    def convert_context_to_csv(self, context):
        """Convert the context dictionary into a CSV file."""

        if self.export_projects:
            report_type = 'By Project'
        elif self.export_users:
            report_type = 'By User'
        elif self.export_projects_and_users:
            report_type = 'Project'
        elif self.export_activities_and_users:
            report_type = 'Activity'

        is_special_report = report_type in ['Project', 'Activity'] # columns for both user and project (or activity). without final row "Total"

        content = []
        date_headers = context['date_headers']

        headers = ['Name']
        if self.export_projects_and_users: headers.append('Project')
        if self.export_activities_and_users: headers.append('Activity')
        headers.extend([date.strftime('%m/%d/%Y') for date in date_headers])
        headers.append('Total')
        content.append(headers)

        summaries = context['summaries'] # list of tuples: [(title, summary), (title, summary), ..]

        for title, summary in summaries:
            if title.startswith(report_type):
                if is_special_report: project_or_activity_name = title.replace(report_type+": ", "") # e.g. remove "Project: " or "Activity: "
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
        # Set default date span to previous week.
        (start, end) = get_week_window(timezone.now() - relativedelta(days=7))
        return {
            'from_date': start,
            'to_date': end,
            'trunc': 'day',
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
        self.export_users = request.GET.get('export_users', False)
        self.export_projects = request.GET.get('export_projects', False)
        self.export_projects_and_users = request.GET.get('export_projects_and_users', False)
        self.export_activities_and_users = request.GET.get('export_activities_and_users', False)
        context = self.get_context_data()
        export_as_csv = (self.export_users or self.export_projects or self.export_projects_and_users or self.export_activities_and_users)
        if export_as_csv:
            kls = CSVViewMixin
        else:
            kls = TemplateView
        return kls.render_to_response(self, context)

    def get_context_data(self, **kwargs):
#         context = super(OshaReport, self).get_context_data(**kwargs)
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

        summaries = []
        if context['entries']:
            include_users_without_entries = data.get('include_users_without_entries', False)

            summary_by_user = get_project_totals(
                    entries.order_by('user__last_name', 'user__id', 'date'),
                    date_headers, 'total', total_column=True, by='user')

            if include_users_without_entries:
                all_users = list( User.objects.all() )
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


            summaries.append(('By User', summary_by_user))

            summaries.append(('By Project', get_project_totals(
                    entries.order_by('project__name', 'project__id', 'date'),
                    date_headers, 'total', total_column=True, by='project')))


            entries = entries.order_by('project__name',
                    'project__id', 'user__last_name', 'user__id', 'date')

            func = lambda x: x['project__name']
            for label, group in groupby(entries, func):
                title = 'Project: ' + label
                summaries.append(
                    (title, get_project_totals(
                        list(group),
                        date_headers, 'total', total_column=True, by='user')
                    )
                )


            entries = entries.order_by('project__business__name',
                    'project__business__id', 'user__last_name', 'user__id', 'date')

            func = lambda x: x['project__business__name']
            for label, group in groupby(entries, func):
                title = 'Activity: ' + label
                summaries.append(
                    (title, get_project_totals(
                        list(group),
                        date_headers, 'total', total_column=True, by='user')
                    )
                )

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
            'date_headers': date_headers,
            'summaries': summaries,
            'range_headers': range_headers,
        })
        return context

    def get_filename(self, context):
        request = self.request.GET.copy()
        from_date = request.get('from_date')
        to_date = request.get('to_date')
        return 'hours_{0}_to_{1}_by_{2}'.format(from_date, to_date,
            context.get('trunc', ''))

    def get_form(self):
        data = self.request.GET or self.defaults
        data = data.copy()  # make mutable
        return OshaReportForm(data)
