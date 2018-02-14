import inspect

from onegov.activity import Attendee


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


class AttendeeCalendar(Calendar, name='attendee'):
    """ Renders all confirmed activites of the given attendee. """

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

    @property
    def calendar(self):
        pass
