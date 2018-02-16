import icalendar
import inspect

from onegov.activity import Attendee
from onegov.core.orm import as_selectable_from_path
from onegov.core.utils import module_path
from onegov.feriennet import _
from sedate import standardize_date
from sqlalchemy import and_, select


class TokenProtected(object):
    """ Serializes the keywords of a class into a signed token and aides in
    instatiating the so serialized class back to an instance.

    """

    reserved_keywords = ('session', 'request')

    @classmethod
    def from_keywords(cls):
        """ Needs to be implemented by the child-class. They keywords given
        to this method are included in the token.

        Therefore be careful not to include any secrets in these.

        """
        raise NotImplementedError

    @property
    def keywords(self):
        return {
            name: getattr(self, name)
            for name in inspect.signature(self.from_keywords).parameters
            if name not in self.reserved_keywords
        }

    def to_token(self, request):
        return request.new_url_safe_token(data=self.keywords, salt='calendar')

    @classmethod
    def from_token(cls, request, token, max_age=None):
        kw = request.load_url_safe_token(
            data=token,
            salt='calendar',
            max_age=max_age)

        return kw and cls.from_keywords(request.app.session(), **kw)

    def enable_linking(self, request):
        self.token = self.to_token(request)

    def link(self, request):
        self.enable_linking(request)
        return request.link(self)


class Calendar(TokenProtected):
    """ A base for all calendars that return icalendar renderings. """

    calendars = {}

    def __init_subclass__(cls, name, **kwargs):
        super().__init_subclass__(**kwargs)

        assert name not in cls.calendars
        cls.name = name
        cls.calendars[name] = cls

    @classmethod
    def from_path(cls, request, name, token):
        calendar = cls.calendars.get(name)
        return calendar and calendar.from_token(request, token)

    @property
    def calendar(self):
        raise NotImplementedError

    def new(self):
        calendar = icalendar.Calendar()
        calendar.add('prodid', '-//OneGov//onegov.feriennet//')
        calendar.add('version', '2.0')

        return calendar


class AttendeeCalendar(Calendar, name='attendee'):
    """ Renders all confirmed activites of the given attendee. """

    attendee_calendar = as_selectable_from_path(
        module_path('onegov.feriennet', 'queries/attendee_calendar.sql'))

    def __init__(self, session, attendee):
        self.session = session
        self.attendee = attendee

    @property
    def attendee_id(self):
        return self.attendee.id.hex

    @classmethod
    def from_keywords(cls, session, attendee_id):
        attendee = session.query(Attendee).filter_by(id=attendee_id).first()
        return attendee and cls(session, attendee)

    def calendar(self, request):
        calendar = self.new()

        for event in self.events(request):
            calendar.add_component(event)

        return calendar.to_ical()

    def events(self, request):
        session = request.app.session()
        stmt = self.attendee_calendar

        records = session.execute(select(stmt.c).where(and_(
            stmt.c.attendee_id == self.attendee_id,
            stmt.c.state == 'accepted',
            stmt.c.confirmed == True
        )))

        def title(record):
            if record.cancelled:
                return f"${request.translate(_('Cancelled'))}: {record.title}"

            return record.title

        for record in records:
            event = icalendar.Event()

            event.add('summary', title(record))
            event.add('dtstart', standardize_date(record.start, 'UTC'))
            event.add('dtend', standardize_date(record.end, 'UTC'))

            yield event
