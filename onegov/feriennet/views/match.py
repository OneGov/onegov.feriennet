from onegov.activity import Attendee
from onegov.activity import Booking, BookingCollection, Occasion
from onegov.activity import PeriodCollection
from onegov.activity.matching import deferred_acceptance_from_database
from onegov.activity.matching.score import PreferAdminChildren
from onegov.activity.matching.score import PreferOrganiserChildren
from onegov.activity.matching.score import Scoring
from onegov.core.cache import lru_cache
from onegov.core.security import Secret
from onegov.core.utils import normalize_for_url
from onegov.core.errors import TooManyWorkersError
from onegov.core.errors import TooManyInstancesError
from onegov.feriennet import _, FeriennetApp
from onegov.feriennet.collections import MatchCollection
from onegov.feriennet.forms import MatchForm
from onegov.feriennet.layout import DefaultLayout, MatchCollectionLayout
from onegov.feriennet.models import PeriodMessage
from onegov.org.new_elements import Block
from onegov.org.new_elements import Confirm
from onegov.org.new_elements import Intercooler
from onegov.org.new_elements import Link
from onegov.user import User, UserCollection
from sqlalchemy import and_
from sqlalchemy.orm import joinedload


@FeriennetApp.worker(name='matching')
def run_matching(request, period_id, confirm, prefer_organiser, prefer_admins):
    period = PeriodCollection(request.session).by_id(period_id)

    if period.confirmed:
        request.alert(_("The period was already confirmed"))
        return

    scoring = Scoring()

    if prefer_organiser:
        scoring.criteria.append(
            PreferOrganiserChildren.from_session(request.session))

    if prefer_admins:
        scoring.criteria.append(
            PreferAdminChildren.from_session(request.session))

    deferred_acceptance_from_database(
        session=request.session,
        period_id=period_id,
        score_function=scoring)

    if confirm:
        period.confirm()
        PeriodMessage.create(period, request, 'confirmed')
        request.success(_("The matching was confirmed successfully"))
    else:
        request.success(_("The matching run executed successfully"))


@FeriennetApp.form(
    model=MatchCollection,
    form=MatchForm,
    template='matches.pt',
    permission=Secret)
def handle_matching(self, request, form):

    layout = MatchCollectionLayout(self, request)

    if 'matching' in request.app.workers:
        worker = request.app.workers['matching']
    else:
        worker = None

    working = worker and worker.working

    if not working and form.submitted(request):
        assert self.period.active and not self.period.confirmed

        try:
            request.app.workers.spawn(
                name='matching',
                period_id=self.period.id,
                prefer_organisers=form.prefer_organiser.data,
                prefer_admins=form.prefer_admins.data,
                confirm_period=form.confirm_period
            )
        except TooManyInstancesError:
            request.error(_("Matching is already in progress"))
        except TooManyWorkersError:
            request.error(_(
                "Too many users are using matching at the same time, "
                "please wait a few minutes and try again."
            ))

    elif not request.POST:
        form.process_scoring(self.period.scoring)

    elif working:
        request.warn(
            _("Matching started ${time} ago and is still in progress"),
            mapping={'time': layout.format_date(worker.start, 'relative')}
        )

    def activity_link(oid):
        return request.class_link(Occasion, {'id': oid})

    def occasion_table_link(oid):
        return request.class_link(Occasion, {'id': oid}, name='bookings-table')

    filters = {}
    filters['states'] = tuple(
        Link(
            text=request.translate(text),
            active=state in self.states,
            url=request.link(self.for_filter(state=state))
        ) for text, state in (
            (_("Too many attendees"), 'overfull'),
            (_("Fully occupied"), 'full'),
            (_("Enough attendees"), 'operable'),
            (_("Not enough attendees"), 'unoperable'),
            (_("No attendees"), 'empty'),
            (_("Rescinded"), 'cancelled')
        )
    )

    return {
        'layout': layout,
        'title': _("Matches for ${title}", mapping={
            'title': self.period.title
        }),
        'occasions': self.occasions,
        'activity_link': activity_link,
        'occasion_table_link': occasion_table_link,
        'happiness': '{}%'.format(round(self.happiness * 100)),
        'operability': '{}%'.format(round(self.operability * 100)),
        'period': self.period,
        'periods': request.app.periods,
        'form': form,
        'button_text': _("Run Matching"),
        'model': self,
        'filters': filters,
        'working': working
    }


@FeriennetApp.html(
    model=Occasion,
    template='occasion_bookings_table.pt',
    name='bookings-table',
    permission=Secret)
def view_occasion_bookings_table(self, request):
    layout = DefaultLayout(self, request)

    wishlist_phase = self.period.wishlist_phase
    booking_phase = self.period.booking_phase
    phase_title = wishlist_phase and _("Wishlist") or _("Bookings")

    users = UserCollection(request.session).query()
    users = users.with_entities(User.username, User.id)
    users = {u.username: u.id.hex for u in users}

    def occasion_links(oid):
        if self.period.finalized:
            yield Link(
                text=_("Signup Attendee"),
                url='#',
                traits=(
                    Block(_(
                        "The period has already been finalized. No new "
                        "attendees may be added."
                    )),
                )
            )
        else:
            yield Link(
                text=_("Signup Attendee"),
                url=request.return_to(
                    request.class_link(Occasion, {'id': oid}, 'book'),
                    request.class_link(MatchCollection)
                )
            )

    @lru_cache(maxsize=10)
    def bookings_link(username):
        return request.class_link(
            BookingCollection, {
                'period_id': self.period.id,
                'username': username
            }
        )

    @lru_cache(maxsize=10)
    def user_link(username):
        return request.return_here(
            request.class_link(
                User, {'id': users[username]}
            )
        )

    @lru_cache(maxsize=10)
    def attendee_link(attendee_id):
        return request.return_here(
            request.class_link(
                Attendee, {'id': attendee_id}
            )
        )

    def booking_links(booking):
        yield Link(_("User"), user_link(booking.attendee.username))
        yield Link(_("Attendee"), attendee_link(booking.attendee_id))
        yield Link(phase_title, bookings_link(booking.attendee.username))

        if wishlist_phase:
            yield Link(
                text=_("Remove Wish"),
                url=layout.csrf_protected_url(
                    request.class_link(Booking, {'id': booking.id})
                ),
                traits=(
                    Confirm(_(
                        "Do you really want to remove ${attendee}'s wish?",
                        mapping={
                            'attendee': booking.attendee.name
                        }
                    ), yes=_("Remove Wish")),
                    Intercooler(
                        request_method='DELETE',
                        target='#{}'.format(booking.id)
                    )
                )
            )

        elif booking_phase and booking.state != 'accepted':
            yield Link(
                text=_("Remove Booking"),
                url=layout.csrf_protected_url(
                    request.class_link(Booking, {'id': booking.id})
                ),
                traits=(
                    Confirm(_(
                        "Do you really want to delete ${attendee}'s booking?",
                        mapping={
                            'attendee': booking.attendee.name
                        }
                    ), yes=_("Remove Booking")),
                    Intercooler(
                        request_method='DELETE',
                        target='#{}'.format(booking.id)
                    )
                )
            )
        elif booking_phase and booking.state == 'accepted':
            yield Link(
                text=_("Cancel Booking"),
                url=layout.csrf_protected_url(
                    request.class_link(
                        Booking, {'id': booking.id}, 'cancel'
                    )
                ),
                traits=(
                    Confirm(_(
                        "Do you really want to cancel ${attendee}'s booking?",
                        mapping={
                            'attendee': booking.attendee.name
                        }
                    ), _("This cannot be undone."), yes=_("Cancel Booking")),
                    Intercooler(
                        request_method='POST',
                    )
                )
            )

    bookings = {'accepted': [], 'other': []}

    q = request.session.query(Booking).filter_by(occasion_id=self.id)
    q = q.options(joinedload(Booking.attendee))

    for booking in q:
        state = booking.state == 'accepted' and 'accepted' or 'other'
        bookings[state].append(booking)

    bookings['accepted'].sort(key=lambda b: normalize_for_url(b.attendee.name))
    bookings['other'].sort(key=lambda b: normalize_for_url(b.attendee.name))

    return {
        'layout': layout,
        'bookings': bookings,
        'oid': self.id,
        'occasion_links': occasion_links,
        'booking_links': booking_links,
        'period': self.period
    }


@FeriennetApp.view(
    model=MatchCollection,
    name='reset',
    permission=Secret,
    request_method="POST")
def reset_matching(self, request):
    assert self.period.active and not self.period.confirmed

    bookings = BookingCollection(request.session, self.period_id)
    bookings = bookings.query().filter(and_(
        Booking.state != 'cancelled',
        Booking.state != 'open'
    ))

    for booking in bookings:
        booking.state = 'open'

    request.success(_("The matching was successfully reset"))
