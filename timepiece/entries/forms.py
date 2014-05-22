import datetime
from dateutil.relativedelta import relativedelta

from django import forms

from timepiece import utils
from timepiece.crm.models import Project
from timepiece.entries.models import Entry, Location, ProjectHours, SimpleEntry
from timepiece.crm.models import Business
from timepiece.forms import INPUT_FORMATS, TimepieceSplitDateTimeWidget,\
        TimepieceDateInput
from timepiece.templatetags.timepiece_tags import humanize_hours


class ClockInForm(forms.ModelForm):
    active_comment = forms.CharField(label='Notes for the active entry',
            widget=forms.Textarea, required=False)

    class Meta:
        model = Entry
        fields = ('active_comment', 'location', 'project', 'activity',
                'start_time', 'comments')

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        self.active = kwargs.pop('active', None)

        initial = kwargs.get('initial', {})
        default_loc = utils.get_setting('TIMEPIECE_DEFAULT_LOCATION_SLUG')
        if default_loc:
            try:
                loc = Location.objects.get(slug=default_loc)
            except Location.DoesNotExist:
                loc = None
            if loc:
                initial['location'] = loc.pk
        project = initial.get('project', None)
        try:
            last_project_entry = Entry.objects.filter(
                user=self.user, project=project).order_by('-end_time')[0]
        except IndexError:
            initial['activity'] = None
        else:
            initial['activity'] = last_project_entry.activity.pk

        super(ClockInForm, self).__init__(*args, **kwargs)

        self.fields['start_time'].required = False
        self.fields['start_time'].initial = datetime.datetime.now()
        self.fields['start_time'].widget = TimepieceSplitDateTimeWidget()
        self.fields['project'].queryset = Project.trackable.filter(
                users=self.user)
        if not self.active:
            self.fields.pop('active_comment')
        else:
            self.fields['active_comment'].initial = self.active.comments
        self.instance.user = self.user

    def clean_start_time(self):
        """
        Make sure that the start time doesn't come before the active entry
        """
        start = self.cleaned_data.get('start_time')
        if not start:
            return start
        active_entries = self.user.timepiece_entries.filter(
            start_time__gte=start, end_time__isnull=True)
        for entry in active_entries:
            output = 'The start time is on or before the current entry: ' + \
            '%s - %s starting at %s' % (entry.project, entry.activity,
                entry.start_time.strftime('%H:%M:%S'))
            raise forms.ValidationError(output)
        return start

    def clean(self):
        start_time = self.clean_start_time()
        data = self.cleaned_data
        if not start_time:
            return data
        if self.active:
            self.active.unpause()
            self.active.comments = data['active_comment']
            self.active.end_time = start_time - relativedelta(seconds=1)
            if not self.active.clean():
                raise forms.ValidationError(data)
        return data

    def save(self, commit=True):
        self.instance.hours = 0
        entry = super(ClockInForm, self).save(commit=commit)
        if self.active and commit:
            self.active.save()
        return entry


class ClockOutForm(forms.ModelForm):
    start_time = forms.DateTimeField(widget=TimepieceSplitDateTimeWidget)
    end_time = forms.DateTimeField(widget=TimepieceSplitDateTimeWidget)

    class Meta:
        model = Entry
        fields = ('location', 'start_time', 'end_time', 'comments')

    def __init__(self, *args, **kwargs):
        kwargs['initial'] = kwargs.get('initial', None) or {}
        kwargs['initial']['end_time'] = datetime.datetime.now()
        super(ClockOutForm, self).__init__(*args, **kwargs)

    def save(self, commit=True):
        entry = super(ClockOutForm, self).save(commit=False)
        entry.unpause(entry.end_time)
        if commit:
            entry.save()
        return entry


class AddUpdateEntryForm(forms.ModelForm):
    start_time = forms.DateTimeField(widget=TimepieceSplitDateTimeWidget(),
            required=True)
    end_time = forms.DateTimeField(widget=TimepieceSplitDateTimeWidget())

    class Meta:
        model = Entry
        exclude = ('user', 'pause_time', 'site', 'hours', 'status',
                   'entry_group')

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super(AddUpdateEntryForm, self).__init__(*args, **kwargs)
        self.instance.user = self.user

        self.fields['project'].queryset = Project.trackable.filter(
                users=self.user)
        # If editing the active entry, remove the end_time field.
        if self.instance.start_time and not self.instance.end_time:
            self.fields.pop('end_time')

    def clean(self):
        """
        If we're not editing the active entry, ensure that this entry doesn't
        conflict with or come after the active entry.
        """
        active = utils.get_active_entry(self.user)
        if active and active.pk != self.instance.pk:
            start_time = self.cleaned_data.get('start_time', None)
            end_time = self.cleaned_data.get('end_time', None)
            if (start_time and start_time > active.start_time) or \
                    (end_time and end_time > active.start_time):
                raise forms.ValidationError('The start time or end time '
                        'conflict with the active entry: {activity} on '
                        '{project} starting at {start_time}.'.format(**{
                            'project': active.project,
                            'activity': active.activity,
                            'start_time': active.start_time.strftime('%H:%M:%S'),
                        }))
        return self.cleaned_data


class ProjectHoursForm(forms.ModelForm):

    class Meta:
        model = ProjectHours


class ProjectHoursSearchForm(forms.Form):
    week_start = forms.DateField(label='Week of', required=False,
            input_formats=INPUT_FORMATS, widget=TimepieceDateInput())

    def clean_week_start(self):
        week_start = self.cleaned_data.get('week_start', None)
        return utils.get_week_start(week_start, False) if week_start else None


class BusinessSelectionForm(forms.ModelForm):

    class Meta:
        model = Project # to have dropdown menu with Businesses (foreign key from project)
        fields = 'business'.split()

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        try:
            disabled = kwargs.pop('disabled')
        except:
            disabled = False

        super(BusinessSelectionForm, self).__init__(*args, **kwargs)
        self.instance.user = self.user

        self.fields['business'].queryset = Business.objects.filter(new_business_projects__users=self.user).distinct()
        if disabled: self.fields['business'].widget.attrs['disabled'] = True


def validate_daily_hours_limit(cleaned_data, user, instance, curr_date=None):
    date = curr_date
    if not curr_date: date = cleaned_data.get("date")
    hours = cleaned_data.get("hours")
    minutes = cleaned_data.get("minutes")
    new_hours = hours+(minutes/60)

    daily_entries_summary = SimpleEntry.summary(user, date, date+datetime.timedelta(days=1))
    current_hours = daily_entries_summary['total']

    hours_balance = current_hours + new_hours
    if instance.id:
        # it's an update, thus dont consider the old value
        hours_balance -= instance.total_hours()

    if hours_balance > SimpleEntry.MAXIMUM_HOURS_PER_DAY:
        exceeding_time = hours_balance - SimpleEntry.MAXIMUM_HOURS_PER_DAY
        err_msg = "You cannot enter more than {0} hours per day, ".format(SimpleEntry.MAXIMUM_HOURS_PER_DAY)
        err_msg+= "today's total is {0}.".format(humanize_hours(current_hours, '{hours:02d}:{minutes:02d}'))
        raise forms.ValidationError(err_msg)


class AddUpdateSimpleEntryForm(forms.ModelForm):

    class Meta:
        model = SimpleEntry
        fields = 'project date hours minutes comments'.split()

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        self.business = kwargs.pop('business')
        super(AddUpdateSimpleEntryForm, self).__init__(*args, **kwargs)
        self.instance.user = self.user

        self.fields['project'].queryset = Project.trackable.filter(
                users=self.user
                ).filter(
                business=self.business
                )

    def clean(self):
        cleaned_data = super(AddUpdateSimpleEntryForm, self).clean()
        validate_daily_hours_limit(cleaned_data, self.user, self.instance)
        return cleaned_data


def make_simple_entries_formset(user, business, curr_date, request=None):
    class _AddUpdateMultiSimpleEntryForm(forms.ModelForm):

        class Meta:
            model = SimpleEntry
            fields = 'project hours minutes comments'.split()
            widgets = {
                'project': forms.widgets.Select(attrs={'class':'span12'}),
                'hours': forms.widgets.TextInput(attrs={'style':'width: 30px;'}),
                'minutes': forms.widgets.Select(attrs={'style':'width: 50px;'}),
                'comments': forms.widgets.TextInput(attrs={'style':'width: 500px;'}),
            }

        def __init__(self, *args, **kwargs):
            super(_AddUpdateMultiSimpleEntryForm, self).__init__(*args, **kwargs)
            self.instance.user = user
            self.fields['project'].queryset = Project.trackable.filter(
                users=user
                ).filter(
                business=business
                )

    from django.forms.models import modelformset_factory
    SimpleEntryFormset = modelformset_factory(SimpleEntry, form=_AddUpdateMultiSimpleEntryForm)

    queryset = SimpleEntry.objects.filter(
        user=user
        ).filter(
        project__business=business
        ).filter(
        date=curr_date
        )

    if not request:
        formset = SimpleEntryFormset(queryset=queryset, prefix='business_'+str(business.id))
    else:
        formset = SimpleEntryFormset(request.POST, queryset=queryset, prefix='business_'+str(business.id))
    return formset


class SimpleDateForm(forms.Form):
    curr_date = forms.DateField(widget=forms.DateInput(attrs={'class':'input-small'}))
