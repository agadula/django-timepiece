import datetime
from decimal import Decimal
from random import randint

from django.contrib.auth.models import Permission
from django.db.models import Q
from django.utils import timezone

from timepiece import utils

from timepiece.entries.models import Entry, SimpleEntry
from timepiece.reports.tests.base import ReportsTestBase
from timepiece.reports.utils import get_project_totals, generate_dates
from timepiece.tests.base import ViewTestMixin, LogTimeMixin


class TestOshaReport(ViewTestMixin, LogTimeMixin, ReportsTestBase):
    url_name = 'report_osha'

#     def test_generate_months(self):
#         dates = [utils.add_timezone(datetime.datetime(2011, month, 1))
#             for month in xrange(1, 13)]
#         start = datetime.date(2011, 1, 1)
#         end = datetime.date(2011, 12, 1)
#         self.check_generate_dates(start, end, 'month', dates)
# 
#     def test_generate_weeks(self):
#         dates = [
#             utils.add_timezone(datetime.datetime(2010, 12, 27)),
#             utils.add_timezone(datetime.datetime(2011, 1, 3)),
#             utils.add_timezone(datetime.datetime(2011, 1, 10)),
#             utils.add_timezone(datetime.datetime(2011, 1, 17)),
#             utils.add_timezone(datetime.datetime(2011, 1, 24)),
#             utils.add_timezone(datetime.datetime(2011, 1, 31)),
#         ]
#         start = utils.add_timezone(datetime.datetime(2011, 1, 1))
#         end = utils.add_timezone(datetime.datetime(2011, 2, 1))
#         self.check_generate_dates(start, end, 'week', dates)
# 
#     def test_generate_days(self):
#         dates = [utils.add_timezone(datetime.datetime(2011, 1, day))
#             for day in xrange(1, 32)]
#         start = utils.add_timezone(datetime.datetime(2011, 1, 1))
#         end = utils.add_timezone(datetime.datetime(2011, 1, 31))
#         self.check_generate_dates(start, end, 'day', dates)
# 
    def check_truncs(self, trunc, hours, minutes):
        # creates for 6 days (2 days per week)
        # 5 entries (each on a different project) of 1 hour and 30 minutes
        self.make_simple_entries(user=self.user) 
        self.make_simple_entries(user=self.user2)
        entries = SimpleEntry.objects.date_trunc(trunc)
        for entry in entries:
            self.assertEqual(entry['hours'], hours)
            self.assertEqual(entry['minutes'], minutes)

    def test_trunc_month(self):
        self.check_truncs('month', 30, 900)

    def test_trunc_week(self):
        self.check_truncs('week', 10, 300)

    def test_trunc_day(self):
        self.check_truncs('day', 5, 150) # total hours/minutes per person per day

    def get_project_totals(self, date_headers, trunc, query=Q(),
                           hour_type='total'):
        """Helper function for testing project_totals utility directly"""
        entries = SimpleEntry.objects.date_trunc(trunc).filter(query)
        if entries:
            pj_totals = get_project_totals(entries, date_headers, hour_type)
            pj_totals = list(pj_totals)
            rows = pj_totals[0][0]
            hours = [hours for name, user_id, hours in rows]
            totals = pj_totals[0][1]
            return hours, totals
        else:
            return ''

    def log_daily(self, start, day2, end):
        self.log_simple_time(project=self.p1, date=start, delta=(1, 0))
        self.log_simple_time(project=self.p1, date=day2, delta=(0, 30))
        self.log_simple_time(project=self.p3, date=day2, delta=(1, 0))
        self.log_simple_time(project=self.p1, date=day2, delta=(3, 0),
                      user=self.user2)
        self.log_simple_time(project=self.sick, date=end, delta=(2, 0),
                      user=self.user2)

    def test_daily_total(self):
        start = utils.add_timezone(datetime.datetime(2011, 1, 1))
        day2 = utils.add_timezone(datetime.datetime(2011, 1, 2))
        end = utils.add_timezone(datetime.datetime(2011, 1, 3))
        self.log_daily(start, day2, end)
        trunc = 'day'
        date_headers = generate_dates(start, end, trunc)
        pj_totals = self.get_project_totals(date_headers, trunc)
        self.assertEqual(pj_totals[0][0], # User 1
                         [Decimal('1.00'), Decimal('1.50'), ''])
        self.assertEqual(pj_totals[0][1], # User 2
                         ['', Decimal('3.00'), Decimal('2.00')])
        self.assertEqual(pj_totals[1], # Total for all Users
                         [Decimal('1.00'), Decimal('4.50'), Decimal('2.00')])

    def test_weekly_total(self):
        start = utils.add_timezone(datetime.datetime(2011, 1, 3))
        end = utils.add_timezone(datetime.datetime(2011, 1, 6))
        # 5 projects (proj #2 twice), 4 days, user 1 each entry 2:15, user 2 each entry 1:30
        self.bulk_simple_entries(start, end)
        trunc = 'week'
        date_headers = generate_dates(start, end, trunc)
        pj_totals = self.get_project_totals(date_headers, trunc)
        self.assertEqual(pj_totals[0][0], [60]) # User 1
        self.assertEqual(pj_totals[0][1], [30]) # User 2
        self.assertEqual(pj_totals[1], [90])

    def test_monthly_total(self):
        start = utils.add_timezone(datetime.datetime(2011, 1, 1))
        end = utils.add_timezone(datetime.datetime(2011, 3, 1))
        trunc = 'month'
        last_day = randint(5, 10)
        worked1 = randint(1, 3)
        worked2 = randint(1, 3)
        for month in xrange(1, 7):
            for day in xrange(1, last_day + 1):
                day = utils.add_timezone(datetime.datetime(2011, month, day))
                self.log_simple_time(date=day, delta=(worked1, 0), user=self.user)
                self.log_simple_time(date=day, delta=(worked2, 0), user=self.user2)
        date_headers = generate_dates(start, end, trunc)
        pj_totals = self.get_project_totals(date_headers, trunc)
        for hour in pj_totals[0][0]:
            self.assertEqual(hour, last_day * worked1)
        for hour in pj_totals[0][1]:
            self.assertEqual(hour, last_day * worked2)

    def args_helper(self, **kwargs):
        start = utils.add_timezone(
                kwargs.pop('start', datetime.datetime(2011, 1, 2)))
        end = utils.add_timezone(
                kwargs.pop('end', datetime.datetime(2011, 1, 4)))
        defaults = {
            'from_date': start.strftime('%Y-%m-%d'), # was '%m-%d-%Y'
            'to_date': end.strftime('%Y-%m-%d'), # was '%m-%d-%Y'
            'trunc': 'week',
        }
        defaults.update(kwargs)
        return defaults

    def make_totals(self, args={}):
        """Return CSV from hourly report for verification in tests"""
        self.login_user(self.superuser)
        response = self._get(data=args, follow=True)
        csv_delimiter = ";"
        return [item.split(csv_delimiter) \
                for item in response.content.split('\r\n')][:-1]

    def check_totals(self, args, data):
        """assert that project_totals contains the data passed in"""
        totals = self.make_totals(args)
        is_testable = len(totals) >= len(data)

        is_a_special_export = (args.has_key('export_projects_and_users') and args['export_projects_and_users'] == True)
        is_a_special_export = is_a_special_export or (args.has_key('export_activities_and_users') and args['export_activities_and_users'] == True)

        columns_to_skip = 1 # avoid checking first column "name"
        if is_a_special_export:
            columns_to_skip = 2 # avoid checking columns "name" and "project"
        if is_testable:
            for row, datum in zip(totals, data):
                self.assertEqual(row[columns_to_skip:], datum) # take away the first column(s)
        else:
            err_msg = "Expecting at least "+str(len(data))+" lines in totals:\n"
            err_msg+= " [\n"
            for row in totals:
                err_msg+= str(row)+",\n"
            err_msg+= " ]"
            raise AssertionError(err_msg)

    def test_form_type__none(self):
        """When no types are checked, no results should be returned."""
        self.bulk_simple_entries()
        args = {
            'billable': False,
            'non_billable': False,
            'paid_leave': False, 
            'export_users' : True, # arg to export the CSV
            }
        args = self.args_helper(**args)
        data = []
        self.check_totals(args, data)

    def test_form_type__all(self):
        """When all types are checked, no filtering should occur."""
        self.bulk_simple_entries()
        args = { 'export_users' : True } # arg to export the CSV
        args = self.args_helper(**args)
        data = [
            ['01/02/2011', '01/03/2011', 'Total'], # two weeks header
            ['15.0', '30.0', '45.0'], # User 1
            ['7.50', '15.00', '22.50'], # User 2
            ['22.50', '45.00', '67.50'], # Total
        ]
        self.check_totals(args, data)

    def test_form_day(self):
        """Hours should be totaled for each day in the date range."""
        args = { 'trunc': 'day', 'export_users' : True }
        args = self.args_helper(**args)
        data = [
            ['01/02/2011', '01/03/2011', '01/04/2011', 'Total'],
            ['15.0', '15.0', '15.0', '45.0'], # User 1
            ['7.50', '7.50', '7.50', '22.50'], # User 2
            ['22.50', '22.50', '22.50', '67.50'], # Total
        ]
        self.bulk_simple_entries()
        self.check_totals(args, data)

    def test_form_week(self):
        """Hours should be totaled for each week in the date range."""
        args = { 'trunc': 'week', 'export_users' : True }
        args = self.args_helper(**args)
        data = [
            ['01/02/2011', '01/03/2011', 'Total'], # two weeks header
            ['15.0', '30.0', '45.0'], # User 1
            ['7.50', '15.00', '22.50'], # User 2
            ['22.50', '45.00', '67.50'], # Total
        ]
        self.bulk_simple_entries()
        self.check_totals(args, data)

    def test_form_month(self):
        """Hours should be totaled for each month in the date range."""
        tz = timezone.get_current_timezone()
        start = datetime.datetime(2011, 1, 4, tzinfo=tz)
        end = datetime.datetime(2011, 3, 28, tzinfo=tz)
        args = { 
            'trunc': 'month', # NOTE: 28 days per month!
            'export_users' : True,
             }
        args = self.args_helper(start=start, end=end, **args)
        data = [
            ['01/04/2011', '02/01/2011', '03/01/2011', 'Total'],
            ['420.0', '420.0', '420.0', '1260.0'],
            ['210.00', '210.00', '210.00', '630.00'],
            ['630.00', '630.00', '630.00', '1890.00'],
        ]
        self.bulk_simple_entries(start, end)
        self.check_totals(args, data)

    def test_form_projects(self):
        """Filter hours for specific projects."""
        self.bulk_simple_entries()

        #Test project 1
        args = {
            'trunc': 'day',
            'projects_1': self.p1.id,
            'export_projects' : True,
        }
        args = self.args_helper(**args)
        data = [
            ['01/02/2011', '01/03/2011', '01/04/2011', 'Total'],
            ['3.75', '3.75', '3.75', '11.25'], # project 1 for all users
            ['3.75', '3.75', '3.75', '11.25'],
        ]
        self.check_totals(args, data)

        #Test with project 2. Note that on prj 2 entries are double
        args = {
            'trunc': 'day',
            'projects_1': self.p2.id,
            'export_projects' : True,
        }
        args = self.args_helper(**args)
        data = [
            ['01/02/2011', '01/03/2011', '01/04/2011', 'Total'],
            ['7.50', '7.50', '7.50', '22.50'], # project 2 for all users
            ['7.50', '7.50', '7.50', '22.50'],
        ]
        self.check_totals(args, data)

        #Test with 2 project filters
        args = {
            'trunc': 'day',
            'projects_1': [self.p2.id, self.p4.id],
            'export_projects' : True,
        }
        args = self.args_helper(**args)
        data = [
            ['01/02/2011', '01/03/2011', '01/04/2011', 'Total'],
            ['7.50', '7.50', '7.50', '22.50'], # project 2 for all users
            ['3.75', '3.75', '3.75', '11.25'], # project 4 for all users
            ['11.25', '11.25', '11.25', '33.75'],
        ]
        self.check_totals(args, data)

    def test_no_permission(self):
        """view_entry_summary permission is required to view this report."""
        self.login_user(self.user)
        response = self._get()
        self.assertEqual(response.status_code, 302)

    def test_entry_summary_permission(self):
        """view_entry_summary permission is required to view this report."""
        self.login_user(self.user)
        entry_summ_perm = Permission.objects.get(codename='view_entry_summary')
        self.user.user_permissions.add(entry_summ_perm)
        self.user.save()
        response = self._get()
        self.assertEqual(response.status_code, 200)

    def test_user_project_report(self):
        start=datetime.datetime(2011, 1, 2)
        start = utils.add_timezone(start)
        end=datetime.datetime(2011, 1, 4)
        end = utils.add_timezone(end)
        dates = generate_dates(start, end, 'day')
        projects = [self.p1, self.p2, self.p2, self.p3]
        self.make_simple_entries(projects=projects, dates=dates,
                          user=self.user, hours=2, minutes=30)
        self.make_simple_entries(projects=projects, dates=dates,
                          user=self.user2, hours=1, minutes=15)

        # daily aggregation
        args = {
            'trunc': 'day',
            'export_projects_and_users' : True,
        }
        args = self.args_helper(**args)
        data = [
            ['01/02/2011', '01/03/2011', '01/04/2011', 'Total'],
            ['2.5', '2.5', '2.5', '7.5'], # project 1 user 1
            ['1.25', '1.25', '1.25', '3.75'], # project 1 user 2

            ['5.0', '5.0', '5.0', '15.0'], # project 2 user 1
            ['2.50', '2.50', '2.50', '7.50'], # project 2 user 2

            ['2.5', '2.5', '2.5', '7.5'], # project 3 user 1
            ['1.25', '1.25', '1.25', '3.75'], # project 3 user 2
        ]
        self.check_totals(args, data)

        # test monthly aggregation
        args = {
            'trunc': 'month',
            'export_projects_and_users' : True,
        }
        args = self.args_helper(**args)
        data = [
            ['01/02/2011', 'Total'], # the date here is the first date of the filter
            ['7.5', '7.5'], # project 1 user 1
            ['3.75', '3.75'], # project 1 user 2

            ['15.0', '15.0'], # project 2 user 1
            ['7.50', '7.50'], # project 2 user 2

            ['7.5', '7.5'], # project 3 user 1
            ['3.75', '3.75'], # project 3 user 2
        ]
        self.check_totals(args, data)

    def test_user_activity_report(self):
        start=datetime.datetime(2011, 1, 2)
        start = utils.add_timezone(start)
        end=datetime.datetime(2011, 1, 4)
        end = utils.add_timezone(end)
        dates = generate_dates(start, end, 'day')
        projects = [self.sick, self.p1, self.p2, self.p3, self.p4, self.p5]
        # p1 p2 p3 in the same business
        # p4 p5 same business
        self.make_simple_entries(projects=projects, dates=dates,
                          user=self.user, hours=2, minutes=30)
        self.make_simple_entries(projects=projects, dates=dates,
                          user=self.user2, hours=1, minutes=15)

        # daily aggregation
        args = {
            'trunc': 'day',
            'export_activities_and_users' : True,
        }
        args = self.args_helper(**args)

        # the result order is affected by the business_id
        data = [
            ['01/02/2011', '01/03/2011', '01/04/2011', 'Total'],
            ['2.5', '2.5', '2.5', '7.5'], # activity 3 (sick) user 1
            ['1.25', '1.25', '1.25', '3.75'], # activity 3 (sick) user 2

            ['7.5', '7.5', '7.5', '22.5'], # activity 1 user 1
            ['3.75', '3.75', '3.75', '11.25'], # activity 1 user 2

            ['5.0', '5.0', '5.0', '15.0'], # activity 2 user 1
            ['2.50', '2.50', '2.50', '7.50'], # activity 2 user 2
        ]
        self.check_totals(args, data)

        # monthly aggregation
        args = {
            'trunc': 'month',
            'export_activities_and_users' : True,
        }
        args = self.args_helper(**args)

        # the result order is affected by the business_id
        data = [
            ['01/02/2011', 'Total'],
            ['7.5', '7.5'], # activity 3 (sick) user 1
            ['3.75', '3.75'], # activity 3 (sick) user 2

            ['22.5', '22.5'], # activity 1 user 1
            ['11.25', '11.25'], # activity 1 user 2

            ['15.0', '15.0'], # activity 2 user 1
            ['7.50', '7.50'], # activity 2 user 2
        ]
        self.check_totals(args, data)
