import datetime

from django.conf import settings
from django.test import TestCase

from timepiece import utils
from timepiece.tests import factories

from timepiece.reports.utils import generate_dates

from timepiece.entries.models import SimpleEntry


class ReportsTestBase(TestCase):

    def setUp(self):
        super(ReportsTestBase, self).setUp()
        self.user = factories.User()
        self.user2 = factories.User()
        self.superuser = factories.Superuser()
        self.devl_activity = factories.Activity(billable=True)
        self.activity = factories.Activity()
        self.sick = factories.Project(name="sick")
        self.vacation = factories.Project()
        settings.TIMEPIECE_PAID_LEAVE_PROJECTS = {
            'sick': self.sick.pk,
            'vacation': self.vacation.pk,
        }
        self.leave = [self.sick.pk, self.vacation.pk]
        self.p1 = factories.BillableProject(name='prj p1')
        self.p2 = factories.NonbillableProject(name='prj p2')
        self.p4 = factories.BillableProject(name='prj p4')
        self.p3 = factories.NonbillableProject(name='prj p3')
        self.p5 = factories.BillableProject(name='prj p5')

        # give business grouping to projects
        # p1 p2 p3 in the same business
        self.p2.business = self.p1.business
        self.p2.save()
        self.p3.business = self.p1.business
        self.p3.save()
        # p4 p5 same business
        self.p5.business = self.p4.business
        self.p5.save()

        self.default_projects = [self.p1, self.p2, self.p3, self.p4, self.p5]
        self.default_dates = [
            utils.add_timezone(datetime.datetime(2011, 1, 3)),
            utils.add_timezone(datetime.datetime(2011, 1, 4)),
            utils.add_timezone(datetime.datetime(2011, 1, 10)),
            utils.add_timezone(datetime.datetime(2011, 1, 16)),
            utils.add_timezone(datetime.datetime(2011, 1, 17)),
            utils.add_timezone(datetime.datetime(2011, 1, 18)),
        ]

    def make_entries(self, user=None, projects=None, dates=None,
                 hours=1, minutes=0):
        """Make several entries to help with reports tests"""
        if not user:
            user = self.user
        if not projects:
            projects = self.default_projects
        if not dates:
            dates = self.default_dates
        for project in projects:
            for day in dates:
                self.log_time(project=project, start=day,
                              delta=(hours, minutes), user=user)

    def bulk_entries(self, start=datetime.datetime(2011, 1, 2),
                   end=datetime.datetime(2011, 1, 4)):
        start = utils.add_timezone(start)
        end = utils.add_timezone(end)
        dates = generate_dates(start, end, 'day')
        projects = [self.p1, self.p2, self.p2, self.p4, self.p5, self.sick]
        self.make_entries(projects=projects, dates=dates,
                          user=self.user, hours=2)
        self.make_entries(projects=projects, dates=dates,
                          user=self.user2, hours=1)

    def make_simple_entries(self, user=None, projects=None, dates=None,
                 hours=1, minutes=30, status=None):
        """Make several simple entries to help with reports tests"""
        if not user:
            user = self.user
        if not projects:
            projects = self.default_projects
        if not dates:
            dates = self.default_dates
        for project in projects:
            for day in dates:
                self.log_simple_time(project=project, date=day,
                              delta=(hours, minutes), user=user, status=status)

    def bulk_simple_entries(self, start=datetime.datetime(2011, 1, 2),
                   end=datetime.datetime(2011, 1, 4), status=None):
        start = utils.add_timezone(start)
        end = utils.add_timezone(end)
        dates = generate_dates(start, end, 'day')
        projects = [self.p1, self.p2, self.p2, self.p4, self.p5, self.sick]
        self.make_simple_entries(projects=projects, dates=dates,
                          user=self.user, hours=2, minutes=30, status=status)
        self.make_simple_entries(projects=projects, dates=dates,
                          user=self.user2, hours=1, minutes=15, status=status)


    def bulk_simple_entries_for_unverified_filtering(self, projects=None):
        first_day=datetime.datetime(2011, 1, 2)
        first_day = utils.add_timezone(first_day)
        second_day=datetime.datetime(2011, 1, 3)
        second_day = utils.add_timezone(second_day)
        third_day=datetime.datetime(2011, 1, 4)
        third_day = utils.add_timezone(third_day)

        if not projects:
            projects = [self.sick, self.p1, self.p2, self.p3, self.p4, self.p5]
        # p1 p2 p3 in the same business
        # p4 p5 same business

        # entries on the first day are verified
        dates=[first_day]
        self.make_simple_entries(projects=projects, dates=dates,
                          user=self.user, hours=2, minutes=30, status=SimpleEntry.VERIFIED)
        self.make_simple_entries(projects=projects, dates=dates,
                          user=self.user2, hours=1, minutes=15, status=SimpleEntry.VERIFIED)

        # 2nd day entries are unverified
        dates=[second_day]
        self.make_simple_entries(projects=projects, dates=dates,
                          user=self.user, hours=2, minutes=30, status=SimpleEntry.UNVERIFIED)
        self.make_simple_entries(projects=projects, dates=dates,
                          user=self.user2, hours=1, minutes=15, status=SimpleEntry.UNVERIFIED)

        # 3rd day entries are verified
        dates=[third_day]
        self.make_simple_entries(projects=projects, dates=dates,
                          user=self.user, hours=2, minutes=30, status=SimpleEntry.VERIFIED)
        self.make_simple_entries(projects=projects, dates=dates,
                          user=self.user2, hours=1, minutes=15, status=SimpleEntry.VERIFIED)



    def check_generate_dates(self, start, end, trunc, dates):
        for index, day in enumerate(generate_dates(start, end, trunc)):
            if isinstance(day, datetime.datetime):
                day = day.date()
            self.assertEqual(day, dates[index].date())
