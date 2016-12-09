from itertools import chain
from onegov.activity import BookingCollection
from onegov.activity import PeriodCollection
from onegov.activity import InvoiceItemCollection
from onegov.feriennet import _, FeriennetApp
from onegov.feriennet.collections import VacationActivityCollection
from onegov.feriennet.layout import DefaultLayout
from onegov.org.elements import Link


@FeriennetApp.template_variables()
def get_template_variables(request):

    front = []

    # inject an activites link in front of all top navigation links
    front.append(Link(
        text=_("Activities"),
        url=request.class_link(VacationActivityCollection)
    ))

    # for logged-in users show the number of open bookings
    if request.is_logged_in:
        session = request.app.session()
        username = request.current_username

        period = PeriodCollection(session).active()
        bookings = BookingCollection(session)

        if period:
            count = bookings.booking_count(username)

            if count:
                attributes = {'data-count': str(count)}
            else:
                attributes = {}

            front.append(Link(
                text=period.confirmed and _("Bookings") or _("Wishlist"),
                url=request.link(bookings),
                classes=('count', period.confirmed and 'success' or 'alert'),
                attributes=attributes
            ))
        else:
            front.append(Link(
                text=_("Bookings"),
                url=request.link(bookings)
            ))

        invoice_items = InvoiceItemCollection(session, username)
        unpaid = invoice_items.count_unpaid_invoices()

        if unpaid:
            attributes = {'data-count': str(unpaid)}
        else:
            attributes = {}

        front.append(Link(
            text=_("Invoices"),
            url=request.class_link(BookingCollection),
            classes=('count', 'alert'),
            attributes=attributes
        ))

    layout = DefaultLayout(request.app.org, request)
    links = chain(front, layout.top_navigation)

    return {
        'top_navigation': links
    }
