from onegov.activity import Attendee
from onegov.activity import Booking, BookingCollection, Occasion
from onegov.activity.matching import deferred_acceptance_from_database
from onegov.core.security import Secret
from onegov.feriennet import _, FeriennetApp
from onegov.feriennet.collections import MatchCollection
from onegov.feriennet.forms import MatchForm
from onegov.feriennet.layout import MatchCollectionLayout
from onegov.org.elements import Link


@FeriennetApp.form(
    model=MatchCollection,
    form=MatchForm,
    template='matches.pt',
    permission=Secret)
def handle_matches(self, request, form):

    layout = MatchCollectionLayout(self, request)

    if form.submitted(request):
        assert self.period.active and not self.period.confirmed

        deferred_acceptance_from_database(
            session=request.app.session(),
            period_id=self.period_id,
            score_function=form.scoring(request.app.session()))

        self.period.scoring = form.scoring(request.app.session())

        if form.confirm_period:
            self.period.confirm()
            request.success(_("The matching was confirmed successfully"))
        else:
            request.success(_("The matching run executed successfully"))

    elif not request.POST:
        form.process_scoring(self.period.scoring)

    def activity_link(oid):
        return request.class_link(Occasion, {'id': oid})

    def record_links(record):
        yield Link(
            self.period.wishlist_phase and _("Wishlist") or _("Bookings"),
            request.class_link(
                BookingCollection, {
                    'period_id': self.period.id,
                    'username': record.attendee_username
                }
            )
        )

        yield Link(
            _("Attendee"), request.return_here(
                request.class_link(
                    Attendee, {'id': record.attendee_id}
                )
            )
        )

    filters = {}
    filters['states'] = tuple(
        Link(
            text=request.translate(text),
            active=state in self.states,
            url=request.link(self.for_filter(state=state))
        ) for text, state in (
            (_("Full"), 'full'),
            (_("Operable"), 'operable'),
            (_("Unoperable"), 'unoperable'),
            (_("Empty"), 'empty')
        )
    )

    return {
        'layout': layout,
        'title': _("Matches for ${title}", mapping={
            'title': self.period.title
        }),
        'occasions': self.occasions,
        'activity_link': activity_link,
        'happiness': '{}%'.format(round(self.happiness * 100)),
        'operability': '{}%'.format(round(self.operability * 100)),
        'period': self.period,
        'periods': request.app.periods,
        'form': form,
        'button_text': _("Run Matching"),
        'model': self,
        'filters': filters,
        'record_links': record_links,
        'booking_link': lambda record, name=None: request.class_link(
            Booking, {'id': record.booking_id}, name
        )
    }


@FeriennetApp.view(
    model=MatchCollection,
    name='zuruecksetzen',
    permission=Secret,
    request_method="POST")
def reset_matching(self, request):
    assert self.period.active and not self.period.confirmed

    bookings = BookingCollection(request.app.session(), self.period_id)
    for booking in bookings.query():
        booking.state = 'open'

    request.success(_("The period was successfully reset"))
