from itsdangerous import BadSignature
from itsdangerous import SignatureExpired
from itsdangerous import URLSafeTimedSerializer
from onegov.core.utils import Bunch
from onegov.feriennet.models.notification_template import TemplateVariables
from onegov.feriennet.models.calendar import TokenProtected
from uuid import uuid4


def test_template_variables():

    class MockRequest(object):

        def __repr__(self):
            return 'MockRequest'

        def translate(self, text):
            return text.upper()

        def link(self, obj, *args, **kwargs):
            return repr(obj)

        def class_link(self, cls, *args, **kwargs):
            return cls.__name__

        @property
        def app(self):
            return Bunch(org=self)

    class MockPeriod(object):
        id = uuid4()
        title = 'Foobar Pass'

    t = TemplateVariables(MockRequest(), MockPeriod())

    assert sorted(t.bound.keys()) == [
        "[ACTIVITIES]",
        "[BOOKINGS]",
        "[HOMEPAGE]",
        "[INVOICES]",
        "[PERIOD]",
    ]

    assert t.render("Welcome to [PERIOD]") == "Welcome to Foobar Pass"
    assert t.render("Go to [INVOICES]") \
        == 'Go to <a href="InvoiceItemCollection">INVOICES</a>'
    assert t.render("Go to [BOOKINGS]") \
        == 'Go to <a href="BookingCollection">BOOKINGS</a>'
    assert t.render("Go to [ACTIVITIES]") \
        == 'Go to <a href="VacationActivityCollection">ACTIVITIES</a>'
    assert t.render("Go to [HOMEPAGE]") \
        == 'Go to <a href="MockRequest">HOMEPAGE</a>'


def test_token_protected_calendar():

    class MockRequest(object):

        @property
        def app(self):
            return Bunch(session=lambda: 'session')

        @property
        def serializer(self):
            return URLSafeTimedSerializer('foobar')

        def new_url_safe_token(self, data, salt=None, max_age=None):
            return self.serializer.dumps(data, salt=salt)

        def load_url_safe_token(self, data, salt=None, max_age=None):
            try:
                return self.serializer.loads(data, salt=salt)
            except (SignatureExpired, BadSignature):
                return None

    class FooCalendar(TokenProtected):

        def __init__(self, session, foo):
            self.session = session
            self.foo = foo

        @classmethod
        def from_keywords(cls, session, foo):
            if foo:
                return cls(session, foo)

    request = MockRequest()

    foo = FooCalendar(None, 'bar')
    token = foo.to_token(request)

    foo = FooCalendar.from_token(request, token)

    assert foo.session == 'session'
    assert foo.foo == 'bar'

    assert not FooCalendar.from_token(request, token + 'xyz')
