import json
import onegov.feriennet
import transaction

from datetime import datetime, timedelta, date
from onegov.activity import ActivityCollection
from onegov.activity import AttendeeCollection
from onegov.activity import BookingCollection
from onegov.activity import OccasionCollection
from onegov.activity import PeriodCollection
from onegov.activity.utils import generate_xml
from onegov.core.utils import Bunch
from onegov.org.testing import Client, get_message, select_checkbox
from onegov.testing import utils
from onegov.user import UserCollection
from psycopg2.extras import NumericRange
from webtest import Upload


def get_post_url(page, css_class):
    return page.pyquery('a.{}'.format(css_class)).attr('ic-post-to')


def get_delete_link(page, index=0):
    return page.pyquery('a[ic-delete-from]')[index].attrib['ic-delete-from']


def test_view_permissions():
    utils.assert_explicit_permissions(
        onegov.feriennet, onegov.feriennet.FeriennetApp)


def test_activity_permissions(es_feriennet_app):
    anon = Client(es_feriennet_app)

    admin = Client(es_feriennet_app)
    admin.login_admin()

    editor = Client(es_feriennet_app)
    editor.login_editor()

    new = editor.get('/angebote').click("Angebot erfassen")
    new.form['title'] = "Learn How to Program"
    new.form['lead'] = "Using a Raspberry Pi we will learn Python"
    new.form.submit()

    periods = PeriodCollection(es_feriennet_app.session())
    activities = ActivityCollection(es_feriennet_app.session())
    occasions = OccasionCollection(es_feriennet_app.session())

    # for the overview we need an active period and existing occasions
    # (at least for anonymous)
    period = periods.add(
        title="2016",
        prebooking=(datetime(2015, 1, 1), datetime(2015, 12, 31)),
        execution=(datetime(2016, 1, 1), datetime(2016, 12, 31)),
        active=True
    )
    for activity in activities.query():
        occasions.add(
            activity, period,
            datetime(2016, 1, 1, 10),
            datetime(2016, 1, 1, 18),
            'Europe/Zurich'
        )

    transaction.commit()

    url = '/angebot/learn-how-to-program'

    assert "Learn How to Program" in editor.get('/angebote')
    assert "Learn How to Program" not in anon.get('/angebote')
    assert "Learn How to Program" in admin.get('/angebote')
    assert editor.get(url, status=200)
    assert anon.get(url, status=404)
    assert admin.get(url, status=200)

    editor.post(get_post_url(editor.get(url), 'request-publication'))

    assert "Learn How to Program" in editor.get('/angebote')
    assert "Learn How to Program" not in anon.get('/angebote')
    assert "Learn How to Program" in admin.get('/angebote')
    assert editor.get(url, status=200)
    assert anon.get(url, status=404)
    assert admin.get(url, status=200)

    ticket = admin.get('/tickets/ALL/open').click("Annehmen").follow()
    admin.post(get_post_url(ticket, 'accept-activity'))

    assert "Learn How to Program" in editor.get('/angebote')
    assert "Learn How to Program" in anon.get('/angebote')
    assert "Learn How to Program" in admin.get('/angebote')
    assert editor.get(url, status=200)
    assert anon.get(url, status=200)
    assert admin.get(url, status=200)

    ticket = admin.get(ticket.request.url)
    admin.post(get_post_url(ticket, 'archive-activity'))

    assert "Learn How to Program" in editor.get('/angebote')
    assert "Learn How to Program" not in anon.get('/angebote')
    assert "Learn How to Program" in admin.get('/angebote')
    assert editor.get(url, status=200)
    assert anon.get(url, status=404)
    assert admin.get(url, status=200)


def test_activity_communication(feriennet_app):
    admin = Client(feriennet_app)
    admin.login_admin()

    editor = Client(feriennet_app)
    editor.login_editor()

    new = editor.get('/angebote').click("Angebot erfassen")
    new.form['title'] = "Learn Python"
    new.form['lead'] = "Using a Raspberry Pi we will learn Python"
    new.form.submit()

    editor.post(get_post_url(
        editor.get('/angebot/learn-python'), 'request-publication'))

    assert len(feriennet_app.smtp.outbox) == 1
    assert "Ein neues Ticket" in get_message(feriennet_app, 0)

    ticket = admin.get('/tickets/ALL/open').click("Annehmen").follow()
    assert "Learn Python" in ticket

    admin.post(get_post_url(ticket, 'accept-activity'))
    assert len(feriennet_app.smtp.outbox) == 2
    message = get_message(feriennet_app, 1)
    assert "wurde veröffentlicht" in message
    assert "Learn Python" in message
    assert "Using a Raspberry Pi we will learn Python" in message


def test_activity_search(es_feriennet_app):
    anon = Client(es_feriennet_app)

    admin = Client(es_feriennet_app)
    admin.login_admin()

    editor = Client(es_feriennet_app)
    editor.login_editor()

    new = editor.get('/angebote').click("Angebot erfassen")
    new.form['title'] = "Learn How to Program"
    new.form['lead'] = "Using a Raspberry Pi we will learn Python"
    new.form.submit()

    url = '/angebot/learn-how-to-program'

    # in preview, activities can't be found
    es_feriennet_app.es_client.indices.refresh(index='_all')
    assert 'search-result-vacation' not in admin.get('/suche?q=Learn')
    assert 'search-result-vacation' not in editor.get('/suche?q=Learn')
    assert 'search-result-vacation' not in anon.get('/suche?q=Learn')

    editor.post(get_post_url(editor.get(url), 'request-publication'))

    # once proposed, activities can be found by the admin only
    es_feriennet_app.es_client.indices.refresh(index='_all')
    assert 'search-result-vacation' in admin.get('/suche?q=Learn')
    assert 'search-result-vacation' not in editor.get('/suche?q=Learn')
    assert 'search-result-vacation' not in anon.get('/suche?q=Learn')

    ticket = admin.get('/tickets/ALL/open').click("Annehmen").follow()
    admin.post(get_post_url(ticket, 'accept-activity'))

    # once accepted, activities can be found by anyone
    es_feriennet_app.es_client.indices.refresh(index='_all')
    assert 'search-result-vacation' in admin.get('/suche?q=Learn')
    assert 'search-result-vacation' in editor.get('/suche?q=Learn')
    assert 'search-result-vacation' in anon.get('/suche?q=Learn')

    ticket = admin.get(ticket.request.url)
    admin.post(get_post_url(ticket, 'archive-activity'))

    # archived the search will fail again, except for admins
    es_feriennet_app.es_client.indices.refresh(index='_all')
    assert 'search-result-vacation' in admin.get('/suche?q=Learn')
    assert 'search-result-vacation' not in editor.get('/suche?q=Learn')
    assert 'search-result-vacation' not in anon.get('/suche?q=Learn')


def test_activity_filter_tags(feriennet_app):

    periods = PeriodCollection(feriennet_app.session())
    activities = ActivityCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())

    anon = Client(feriennet_app)

    editor = Client(feriennet_app)
    editor.login_editor()

    admin = Client(feriennet_app)
    admin.login_admin()

    new = editor.get('/angebote').click("Angebot erfassen")
    new.form['title'] = "Learn How to Program"
    new.form['lead'] = "Using a Raspberry Pi we will learn Python"

    select_checkbox(new, "tags", "Computer")
    select_checkbox(new, "tags", "Wissenschaft")

    new.form.submit()

    new = editor.get('/angebote').click("Angebot erfassen")
    new.form['title'] = "Learn How to Cook"
    new.form['lead'] = "Using a Stove we will cook a Python"

    select_checkbox(new, "tags", "Kochen")
    select_checkbox(new, "tags", "Wissenschaft")

    new.form.submit()

    for activity in ActivityCollection(feriennet_app.session()).query().all():
        activity.propose().accept()

    transaction.commit()

    page = anon.get('/angebote')
    assert "Keine Angebote" in page

    # only show activites to anonymous if there's an active period..
    periods.add(
        title="2016",
        prebooking=(datetime(2015, 1, 1), datetime(2015, 12, 31)),
        execution=(datetime(2016, 1, 1), datetime(2016, 12, 31)),
        active=True
    )
    transaction.commit()

    page = anon.get('/angebote')
    assert "Keine Angebote" in page

    # ..and if there are any occasions for those activities
    period = periods.active()

    for activity in activities.query():
        occasions.add(
            activity, period,
            datetime(2016, 1, 1, 10),
            datetime(2016, 1, 1, 18),
            'Europe/Zurich'
        )

    transaction.commit()

    page = anon.get('/angebote')
    assert "Learn How to Cook" in page
    assert "Learn How to Program" in page

    page = page.click('Computer')
    assert "Learn How to Cook" not in page
    assert "Learn How to Program" in page

    page = page.click('Computer')
    assert "Learn How to Cook" in page
    assert "Learn How to Program" in page

    page = page.click('Kochen')
    assert "Learn How to Cook" in page
    assert "Learn How to Program" not in page

    page = page.click('Computer')
    assert "Learn How to Cook" in page
    assert "Learn How to Program" in page

    page = page.click('Computer')
    page = page.click('Kochen')
    page = page.click('Wissenschaft')
    assert "Learn How to Cook" in page
    assert "Learn How to Program" in page

    # the state filter works for editors
    new = editor.get('/angebote').click("Angebot erfassen")
    new.form['title'] = "Learn How to Dance"
    new.form['lead'] = "We will dance with a Python"
    new.form.submit()

    # editors see the state as a filter
    assert "Vorschau" in editor.get('/angebote')

    # anonymous does not
    assert "Vorschau" not in anon.get('/angebote')

    page = editor.get('/angebote').click('Vorschau')
    assert "Learn How to Cook" not in page
    assert "Learn How to Program" not in page
    assert "Learn How to Dance" in page

    # anyone can filter by week
    page = editor.get('/angebote').click('2. Woche', index=0)
    assert "Keine Angebote" in page

    page = editor.get('/angebote').click('1. Woche', index=0)
    assert "Learn How to Cook" in page


def test_activity_filter_duration(feriennet_app):
    activities = ActivityCollection(feriennet_app.session(), type='vacation')
    periods = PeriodCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())

    retreat = activities.add("Retreat", username='admin@example.org')
    meeting = activities.add("Meeting", username='admin@example.org')

    period = periods.add(
        title="2016",
        prebooking=(datetime(2015, 1, 1), datetime(2015, 12, 31)),
        execution=(datetime(2016, 1, 1), datetime(2016, 12, 31)),
        active=True
    )

    retreat.propose().accept()
    meeting.propose().accept()

    # the retreat lasts a weekend
    reatreat_occasion_id = occasions.add(
        start=datetime(2016, 10, 8, 8),
        end=datetime(2016, 10, 9, 16),
        timezone="Europe/Zurich",
        activity=retreat,
        period=period
    ).id

    # the meeting lasts half a day
    occasions.add(
        start=datetime(2016, 10, 10, 8),
        end=datetime(2016, 10, 10, 12),
        timezone="Europe/Zurich",
        activity=meeting,
        period=period
    )

    transaction.commit()

    client = Client(feriennet_app)

    half_day = client.get('/angebote').click('Halbtägig')
    many_day = client.get('/angebote').click('Mehrtägig')

    assert "Meeting" in half_day
    assert "Retreat" not in half_day

    assert "Meeting" not in many_day
    assert "Retreat" in many_day

    # shorten the retreat
    occasions.by_id(reatreat_occasion_id).dates[0].end -= timedelta(days=1)

    transaction.commit()

    full_day = client.get('/angebote').click('Ganztägig')
    many_day = client.get('/angebote').click('Mehrtägig')

    assert "Retreat" in full_day
    assert "Retreat" not in many_day


def test_activity_filter_age_ranges(feriennet_app):
    activities = ActivityCollection(feriennet_app.session(), type='vacation')
    periods = PeriodCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())

    retreat = activities.add("Retreat", username='admin@example.org')
    meeting = activities.add("Meeting", username='admin@example.org')

    period = periods.add(
        title="2016",
        prebooking=(datetime(2015, 1, 1), datetime(2015, 12, 31)),
        execution=(datetime(2016, 1, 1), datetime(2016, 12, 31)),
        active=True
    )

    retreat.propose().accept()
    meeting.propose().accept()

    # the retreat lasts a weekend
    occasions.add(
        start=datetime(2016, 10, 8, 8),
        end=datetime(2016, 10, 9, 16),
        age=(0, 10),
        timezone="Europe/Zurich",
        activity=retreat,
        period=period
    )

    # the meeting lasts half a day
    meeting_occasion_id = occasions.add(
        start=datetime(2016, 10, 8, 8),
        end=datetime(2016, 10, 9, 16),
        age=(5, 15),
        timezone="Europe/Zurich",
        activity=meeting,
        period=period
    ).id

    transaction.commit()

    client = Client(feriennet_app)

    preschool = client.get('/angebote').click('3 - 6 Jahre')
    highschool = client.get('/angebote').click('14 - 17 Jahre')

    assert "Retreat" in preschool
    assert "Meeting" in preschool

    assert "Retreat" not in highschool
    assert "Meeting" in highschool

    # change the meeting age
    occasions.by_id(meeting_occasion_id).age = NumericRange(15, 20)
    transaction.commit()

    preschool = client.get('/angebote').click('3 - 6 Jahre')

    assert "Retreat" in preschool
    assert "Meeting" not in preschool


def test_organiser_info(feriennet_app):

    admin = Client(feriennet_app)
    admin.login_admin()

    editor = Client(feriennet_app)
    editor.login_editor()

    new = editor.get('/angebote').click("Angebot erfassen")
    new.form['title'] = "Play with Legos"
    new.form['lead'] = "Like Minecraft, but in the real world"
    new.form.submit()

    new = admin.get('/angebote').click("Angebot erfassen")
    new.form['title'] = "Play with Playmobil"
    new.form['lead'] = "Like Second Life, but in the real world"
    new.form.submit()

    for activity in ActivityCollection(feriennet_app.session()).query().all():
        activity.propose().accept()

    transaction.commit()

    # by default the email address of the owner is shown
    assert 'editor@example.org' in admin.get('/angebot/play-with-legos')
    assert 'admin@example.org' in editor.get('/angebot/play-with-playmobil')

    # only the owner gets the change contact link
    assert "Kontakt ändern" in editor.get('/angebot/play-with-legos')
    assert "Kontakt ändern" not in editor.get('/angebot/play-with-playmobil')

    # admins get the change contact link as well
    assert "Kontakt ändern" in admin.get('/angebot/play-with-legos')
    assert "Kontakt ändern" in admin.get('/angebot/play-with-playmobil')

    # owner changes are reflected on the activity
    contact = editor.get('/angebot/play-with-legos').click('Kontakt ändern')
    contact.form['salutation'] = 'mr'
    contact.form['first_name'] = 'Ed'
    contact.form['last_name'] = 'Itor'
    contact.form['organisation'] = 'Editors Association'
    contact.form['address'] = 'K Street'
    contact.form['zip_code'] = '20001'
    contact.form['place'] = 'Washington'
    contact.form['email'] = 'editors-association@example.org'
    contact.form['phone'] = '+41 23 456 789'
    contact.form['website'] = 'https://www.example.org'
    contact.form['emergency'] = '+01 234 56 78 (Peter)'
    contact.form.submit()

    activity = editor.get('/angebot/play-with-legos')

    assert "Editors Association" in activity
    assert "Ed\u00A0Itor" in activity
    assert "Washington" in activity
    assert "20001" in activity
    assert "K Street" in activity
    assert "editors-association@example.org" in activity
    assert "+41 23 456 789" in activity
    assert "https://www.example.org" in activity

    # admin changes are reflected on the activity
    contact = admin.get('/angebot/play-with-legos').click('Kontakt ändern')
    contact.form['organisation'] = 'Admins Association'
    contact.form.submit()

    activity = editor.get('/angebot/play-with-legos')

    assert "Admins Association" in activity


def test_occasions_form(feriennet_app):

    editor = Client(feriennet_app)
    editor.login_editor()

    admin = Client(feriennet_app)
    admin.login_admin()

    new = editor.get('/angebote').click("Angebot erfassen")
    new.form['title'] = "Play with Legos"
    new.form['lead'] = "Like Minecraft, but in the real world"
    new.form.submit().follow()

    periods = admin.get('/angebote').click("Perioden")

    period = periods.click("Neue Periode")
    period.form['title'] = "Vacation Program 2016"
    period.form['prebooking_start'] = '2016-09-01'
    period.form['prebooking_end'] = '2016-09-30'
    period.form['execution_start'] = '2016-10-01'
    period.form['execution_end'] = '2016-10-31'
    period.form['deadline_date'] = '2016-10-01'
    period.form.submit()

    activity = editor.get('/angebote').click("Play with Legos")
    assert "keine Durchführungen" in activity

    occasion = activity.click("Neue Durchführung")
    occasion.form['dates'] = json.dumps({
        'values': [{
            'start': '2016-10-04 10:00:00',
            'end': '2016-10-04 12:00:00'
        }]
    })
    occasion.form['meeting_point'] = "Franz Karl Weber"
    occasion.form['note'] = "No griefers"
    occasion.form['min_age'] = 10
    occasion.form['max_age'] = 20
    occasion.form['min_spots'] = 30
    occasion.form['max_spots'] = 40
    activity = occasion.form.submit().follow()

    assert "keine Durchführungen" not in activity
    assert "4. Oktober 10:00 - 12:00" in activity
    assert "10 - 20 Jahre alt" in activity
    assert "30 - 40 Teilnehmer" in activity
    assert "Franz Karl Weber" in activity
    assert "No griefers" in activity

    occasion = activity.click("Bearbeiten", index=1)
    occasion.form['min_age'] = 15
    activity = occasion.form.submit().follow()
    assert "15 - 20 Jahre alt" in activity

    editor.delete(get_delete_link(activity, index=1))
    assert "keine Durchführungen" in editor.get('/angebot/play-with-legos')


def test_multiple_dates_occasion(feriennet_app):

    editor = Client(feriennet_app)
    editor.login_editor()

    admin = Client(feriennet_app)
    admin.login_admin()

    new = editor.get('/angebote').click("Angebot erfassen")
    new.form['title'] = "Play with Legos"
    new.form['lead'] = "Like Minecraft, but in the real world"
    new.form.submit().follow()

    periods = admin.get('/angebote').click("Perioden")

    period = periods.click("Neue Periode")
    period.form['title'] = "Vacation Program 2016"
    period.form['prebooking_start'] = '2016-09-01'
    period.form['prebooking_end'] = '2016-09-30'
    period.form['execution_start'] = '2016-10-01'
    period.form['execution_end'] = '2016-10-31'
    period.form['deadline_date'] = '2016-09-01'
    period.form.submit()

    activity = editor.get('/angebote').click("Play with Legos")
    assert "keine Durchführungen" in activity

    occasion = activity.click("Neue Durchführung")
    occasion.form['meeting_point'] = "Franz Karl Weber"
    occasion.form['note'] = "No griefers"
    occasion.form['min_age'] = 10
    occasion.form['max_age'] = 20
    occasion.form['min_spots'] = 30
    occasion.form['max_spots'] = 40

    occasion.form['dates'] = ""
    assert "mindestens ein Datum" in occasion.form.submit()

    occasion.form['dates'] = json.dumps({
        'values': [{
            'start': '2016-10-04 10:00:00',
            'end': '2016-10-04 12:00:00'
        }, {
            'start': '2016-10-04 10:00:00',
            'end': '2016-10-04 12:00:00'
        }]
    })
    assert "mit einem anderen Datum" in occasion.form.submit()

    occasion.form['dates'] = json.dumps({
        'values': [{
            'start': '2016-10-01 10:00:00',
            'end': '2016-10-01 12:00:00'
        }, {
            'start': '2016-10-02 10:00:00',
            'end': '2016-10-02 12:00:00'
        }]
    })

    activity = occasion.form.submit().follow()
    assert "1. Oktober 10:00" in activity
    assert "2. Oktober 10:00" in activity


def test_execution_period(feriennet_app):

    admin = Client(feriennet_app)
    admin.login_admin()

    new = admin.get('/angebote').click("Angebot erfassen")
    new.form['title'] = "Play with Legos"
    new.form['lead'] = "Like Minecraft, but in the real world"
    new.form.submit().follow()

    periods = admin.get('/angebote').click("Perioden")

    period = periods.click("Neue Periode")
    period.form['title'] = "Vacation Program 2016"
    period.form['prebooking_start'] = '2016-09-01'
    period.form['prebooking_end'] = '2016-09-30'
    period.form['execution_start'] = '2016-10-01'
    period.form['execution_end'] = '2016-10-01'
    period.form['deadline_date'] = '2016-09-01'
    period.form.submit()

    occasion = admin.get('/angebot/play-with-legos').click("Neue Durchführung")
    occasion.form['min_age'] = 10
    occasion.form['max_age'] = 20
    occasion.form['min_spots'] = 30
    occasion.form['max_spots'] = 40

    occasion.form['dates'] = json.dumps({
        'values': [{
            'start': '2016-10-01 00:00:00',
            'end': '2016-10-02 23:59:59'
        }]
    })
    assert "Datum liegt ausserhalb" in occasion.form.submit()

    occasion.form['dates'] = json.dumps({
        'values': [{
            'start': '2016-09-30 00:00:00',
            'end': '2016-10-01 23:59:59'
        }]
    })
    assert "Datum liegt ausserhalb" in occasion.form.submit()

    occasion.form['dates'] = json.dumps({
        'values': [{
            'start': '2016-10-01 00:00:00',
            'end': '2016-10-01 23:59:59'
        }]
    })
    assert "Änderungen wurden gespeichert" in occasion.form.submit().follow()

    period = admin.get('/perioden').click("Bearbeiten")
    period.form['execution_start'] = '2016-10-02'
    period.form['execution_end'] = '2016-10-02'
    period = period.form.submit()

    assert "in Konflikt" in period
    assert "Play with Legos" in period

    period.form['execution_start'] = '2016-10-01'
    period.form['execution_end'] = '2016-10-01'
    periods = period.form.submit().follow()

    assert "gespeichert" in periods


def test_enroll_child(feriennet_app):
    activities = ActivityCollection(feriennet_app.session(), type='vacation')
    periods = PeriodCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())

    retreat = activities.add("Retreat", username='admin@example.org')
    retreat.propose().accept()

    prebooking = tuple(d.date() for d in (
        datetime.now() - timedelta(days=1),
        datetime.now() + timedelta(days=1)
    ))

    execution = tuple(d.date() for d in (
        datetime.now() + timedelta(days=10),
        datetime.now() + timedelta(days=12)
    ))

    occasions.add(
        start=datetime(2016, 10, 8, 8),
        end=datetime(2016, 10, 9, 16),
        age=(0, 10),
        timezone="Europe/Zurich",
        activity=retreat,
        period=periods.add(
            title="2016",
            prebooking=prebooking,
            execution=execution,
            active=True,
            deadline_date=(datetime.utcnow() + timedelta(days=1)).date()
        )
    )

    UserCollection(feriennet_app.session()).add(
        'member@example.org', 'hunter2', 'member')

    transaction.commit()

    client = Client(feriennet_app)

    activity = client.get('/angebot/retreat')

    login = activity.click("Anmelden")
    assert "Login" in login

    login.form['username'] = 'member@example.org'
    login.form['password'] = 'hunter2'
    enroll = login.form.submit().follow()
    assert "Teilnehmer Anmelden" in enroll

    # now that we're logged in, the login link automatically skips ahead
    enroll = activity.click("Anmelden").follow()
    assert "Teilnehmer Anmelden" in enroll

    # the link changes, but the result stays the same
    enroll = client.get('/angebot/retreat').click("Anmelden")
    assert "Teilnehmer Anmelden" in enroll

    enroll.form['first_name'] = "Tom"
    enroll.form['last_name'] = "Sawyer"
    enroll.form['birth_date'] = "2012-01-01"
    enroll.form['gender'] = 'male'
    activity = enroll.form.submit().follow()

    assert "zu Tom\u00A0Sawyer's Wunschliste hinzugefügt" in activity

    # prevent double-subscriptions
    enroll = activity.click("Anmelden")
    assert "Tom\u00A0Sawyer hat sich bereits für diese Durchführung"\
        in enroll.form.submit()

    enroll.form['attendee'] = 'other'
    enroll.form['first_name'] = "Tom"
    enroll.form['last_name'] = "Sawyer"
    enroll.form['birth_date'] = "2011-01-01"
    enroll.form['gender'] = 'male'

    # prevent adding two kids with the same name
    assert "Sie haben bereits ein Kind mit diesem Namen eingegeben"\
        in enroll.form.submit()

    # prevent enrollment for inactive periods
    periods.query().first().active = False
    transaction.commit()

    enroll.form['first_name'] = "Huckleberry"
    enroll.form['last_name'] = "Finn"
    assert "Diese Durchführung liegt ausserhalb der aktiven Periode"\
        in enroll.form.submit()

    # prevent enrollment outside of prebooking
    period = periods.query().first()
    period.active = True
    period.prebooking_start -= timedelta(days=10)
    period.prebooking_end -= timedelta(days=10)

    transaction.commit()

    assert "nur während der Wunschphase" in enroll.form.submit()

    # set the record straight again
    period = periods.query().first()
    period.prebooking_start += timedelta(days=10)
    period.prebooking_end += timedelta(days=10)

    transaction.commit()

    enroll.form['first_name'] = "Huckleberry"
    enroll.form['last_name'] = "Finn"
    activity = enroll.form.submit().follow()

    assert "zu Huckleberry\u00A0Finn's Wunschliste hinzugefügt" in activity

    # prevent booking over the limit
    period = periods.query().first()
    period.all_inclusive = True
    period.max_bookings_per_attendee = 1
    period.confirmed = True

    retreat = activities.add("Another Retreat", username='admin@example.org')
    retreat.propose().accept()
    occasions.add(
        start=datetime(2016, 10, 8, 8),
        end=datetime(2016, 10, 9, 16),
        age=(0, 10),
        timezone="Europe/Zurich",
        activity=retreat,
        period=period
    )

    transaction.commit()

    enroll = client.get('/angebot/another-retreat').click("Anmelden")
    enroll.form.submit()

    assert "maximale Anzahl von 1 Buchungen" in enroll.form.submit()

    # prevent booking one activity more than once
    period = periods.query().first()
    period.all_inclusive = False
    period.max_bookings_per_attendee = None
    period.confirmed = False

    occasions.add(
        start=datetime(2016, 10, 8, 18),
        end=datetime(2016, 10, 9, 20),
        age=(0, 10),
        timezone="Europe/Zurich",
        activity=activities.by_name('another-retreat'),
        period=period
    )

    transaction.commit()

    enroll = client.get('/angebot/another-retreat').click("Anmelden", index=0)
    enroll = enroll.form.submit()

    enroll = client.get('/angebot/another-retreat').click("Anmelden", index=1)
    enroll = enroll.form.submit()

    assert "bereits eine andere Durchführung dieses Angebots gebucht" in enroll


def test_enroll_age_mismatch(feriennet_app):
    activities = ActivityCollection(feriennet_app.session(), type='vacation')
    periods = PeriodCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())

    retreat = activities.add("Retreat", username='admin@example.org')
    retreat.propose().accept()

    prebooking = tuple(d.date() for d in (
        datetime.now() - timedelta(days=1),
        datetime.now() + timedelta(days=1)
    ))

    execution = tuple(d.date() for d in (
        datetime.now() + timedelta(days=10),
        datetime.now() + timedelta(days=12)
    ))

    occasions.add(
        start=datetime(2016, 10, 8, 8),
        end=datetime(2016, 10, 9, 16),
        age=(5, 10),
        timezone="Europe/Zurich",
        activity=retreat,
        period=periods.add(
            title="2016",
            prebooking=prebooking,
            execution=execution,
            active=True
        )
    )

    UserCollection(feriennet_app.session()).add(
        'member@example.org', 'hunter2', 'member')

    transaction.commit()

    admin = Client(feriennet_app)
    admin.login_admin()

    page = admin.get('/angebot/retreat').click("Anmelden")
    page.form['first_name'] = "Tom"
    page.form['last_name'] = "Sawyer"
    page.form['gender'] = 'male'

    page.form['birth_date'] = "1900-01-01"
    assert "zu alt" in page.form.submit()

    page.form['birth_date'] = "2015-01-01"
    assert "zu jung" in page.form.submit()

    page.form['ignore_age'] = True
    assert "Wunschliste hinzugefügt" in page.form.submit().follow()


def test_booking_view(feriennet_app):
    activities = ActivityCollection(feriennet_app.session(), type='vacation')
    attendees = AttendeeCollection(feriennet_app.session())
    bookings = BookingCollection(feriennet_app.session())
    periods = PeriodCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())
    users = UserCollection(feriennet_app.session())

    prebooking = tuple(d.date() for d in (
        datetime.now() - timedelta(days=1),
        datetime.now() + timedelta(days=1)
    ))

    execution = tuple(d.date() for d in (
        datetime.now() + timedelta(days=10),
        datetime.now() + timedelta(days=12)
    ))

    period = periods.add(
        title="2016",
        prebooking=prebooking,
        execution=execution,
        active=True
    )

    periods.add(
        title="2017",
        prebooking=prebooking,
        execution=execution,
        active=False
    )

    o = []

    for i in range(4):
        a = activities.add("A {}".format(i), username='admin@example.org')
        a.propose().accept()

        o.append(occasions.add(
            start=datetime(2016, 10, 8, 8),
            end=datetime(2016, 10, 9, 16),
            age=(0, 10),
            timezone="Europe/Zurich",
            activity=a,
            period=period
        ))

    m1 = users.add('m1@example.org', 'hunter2', 'member')
    m2 = users.add('m2@example.org', 'hunter2', 'member')

    a1 = attendees.add(m1, 'Dustin', date(2000, 1, 1), 'female')
    a2 = attendees.add(m2, 'Mike', date(2000, 1, 1), 'female')

    # hookup a1 with all courses
    bookings.add(m1, a1, o[0])
    bookings.add(m1, a1, o[1])
    bookings.add(m1, a1, o[2])
    bookings.add(m1, a1, o[3])

    # m2 only gets one for the permission check
    bookings.add(m2, a2, o[0])

    transaction.commit()

    c1 = Client(feriennet_app)
    c1.login('m1@example.org', 'hunter2')

    c2 = Client(feriennet_app)
    c2.login('m2@example.org', 'hunter2')

    # make sure the bookings count is correct
    assert 'data-count="4"' in c1.get('/')
    assert 'data-count="1"' in c2.get('/')

    # make sure the bookings show up under my view
    def count(page):
        return len(page.pyquery('.attendee-bookings > ul > li'))

    c1_bookings = c1.get('/').click('Wunschliste')
    c2_bookings = c2.get('/').click('Wunschliste')

    assert count(c1_bookings) == 4
    assert count(c2_bookings) == 1

    # make sure each user only has access to their own bookings
    def star_url(page, index):
        return page.pyquery(
            page.pyquery('a[ic-post-to]')[index]).attr['ic-post-to']

    assert c1.post(star_url(c2_bookings, 0), status=403)
    assert c2.post(star_url(c1_bookings, 0), status=403)

    # star three bookings - the last one should fail
    result = c1.post(star_url(c1_bookings, 0))
    assert result.headers.get('X-IC-Trigger') is None

    result = c1.post(star_url(c1_bookings, 1))
    assert result.headers.get('X-IC-Trigger') is None

    result = c1.post(star_url(c1_bookings, 2))
    assert result.headers.get('X-IC-Trigger') is None

    result = c1.post(star_url(c1_bookings, 3))
    assert result.headers.get('X-IC-Trigger') == 'show-alert'
    assert "maximal drei Favoriten" in result.headers.get('X-IC-Trigger-Data')

    # users may switch between other periods
    url = c1_bookings.pyquery('select option:last').val()
    assert "Noch keine Buchungen" in c1.get(url)

    # admins may switch between other users
    admin = Client(feriennet_app)
    admin.login_admin()

    page = admin.get('/').click('Wunschliste')
    url = page.pyquery('select:last option:nth-child(3)').val()

    m1_bookings = admin.get(url)

    assert count(m1_bookings) == 4


def test_matching_view(feriennet_app):
    activities = ActivityCollection(feriennet_app.session(), type='vacation')
    attendees = AttendeeCollection(feriennet_app.session())
    bookings = BookingCollection(feriennet_app.session())
    periods = PeriodCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())

    owner = Bunch(username='admin@example.org')

    prebooking = tuple(d.date() for d in (
        datetime.now() - timedelta(days=1),
        datetime.now() + timedelta(days=1)
    ))

    execution = tuple(d.date() for d in (
        datetime.now() + timedelta(days=10),
        datetime.now() + timedelta(days=12)
    ))

    period = periods.add(
        title="Ferienpass 2016",
        prebooking=prebooking,
        execution=execution,
        active=True
    )

    o = []

    for i in range(2):
        a = activities.add("A {}".format(i), username='admin@example.org')
        a.propose().accept()

        o.append(occasions.add(
            start=datetime(2016, 10, 8 + i, 8),
            end=datetime(2016, 10, 8 + i, 16),
            age=(0, 10),
            spots=(2, 4),
            timezone="Europe/Zurich",
            activity=a,
            period=period
        ))

    a1 = attendees.add(owner, 'Dustin', date(2000, 1, 1), 'female')
    a2 = attendees.add(owner, 'Mike', date(2000, 1, 1), 'female')

    # the first course has enough attendees
    bookings.add(owner, a1, o[0])
    bookings.add(owner, a2, o[0])

    # the second one does not
    bookings.add(owner, a1, o[1])

    transaction.commit()

    client = Client(feriennet_app)
    client.login_admin()

    matching = client.get('/angebote').click("Zuteilung")

    # check the initial state
    assert "Ferienpass 2016" in matching
    assert "Zufriedenheit liegt bei <strong>0%</strong>" in matching
    assert "<strong>0%</strong> aller Durchführungen haben genug" in matching
    assert "0 / 4" in matching
    assert "Dustin" in matching

    # run a matching
    matching = matching.form.submit()

    assert "Zufriedenheit liegt bei <strong>100%</strong>" in matching
    assert "<strong>50%</strong> aller Durchführungen haben genug" in matching
    assert "1 / 4" in matching
    assert "2 / 4" in matching

    # reset it again
    client.post(get_post_url(matching, 'reset-matching'))
    matching = client.get('/angebote').click("Zuteilung")

    assert "Zufriedenheit liegt bei <strong>0%</strong>" in matching
    assert "<strong>0%</strong> aller Durchführungen haben genug" in matching

    # confirm the matching
    matching.form['confirm'] = 'yes'
    matching.form['sure'] = 'yes'
    matching = matching.form.submit()

    assert "wurde bereits bestätigt" in matching
    assert "Abgeschlossen" in client.get('/angebote').click("Perioden")


def test_confirmed_booking_view(feriennet_app):
    activities = ActivityCollection(feriennet_app.session(), type='vacation')
    attendees = AttendeeCollection(feriennet_app.session())
    bookings = BookingCollection(feriennet_app.session())
    periods = PeriodCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())

    owner = Bunch(username='admin@example.org')

    prebooking = tuple(d.date() for d in (
        datetime.now() - timedelta(days=1),
        datetime.now() + timedelta(days=1)
    ))

    execution = tuple(d.date() for d in (
        datetime.now() + timedelta(days=10),
        datetime.now() + timedelta(days=12)
    ))

    period = periods.add(
        title="Ferienpass 2016",
        prebooking=prebooking,
        execution=execution,
        active=True
    )

    o = occasions.add(
        start=datetime(2016, 11, 25, 8),
        end=datetime(2016, 11, 25, 16),
        age=(0, 10),
        spots=(0, 10),
        timezone="Europe/Zurich",
        activity=activities.add("A", username='admin@example.org'),
        period=period
    )

    a = attendees.add(owner, 'Dustin', date(2000, 1, 1), 'female')
    bookings.add(owner, a, o)

    transaction.commit()

    client = Client(feriennet_app)
    client.login_admin()

    # When the period is unconfirmed, no storno is available, and the
    # state is always "open"
    periods.query().one().confirmed = False
    bookings.query().one().state = 'accepted'

    transaction.commit()

    page = client.get('/meine-buchungen')
    assert "Offen" in page
    assert "Stornieren" not in page
    assert "Entfernen" in page
    assert "Angenommen" not in page

    # When the period is confirmed, the state is shown
    periods.query().one().confirmed = True
    bookings.query().one().state = 'accepted'

    transaction.commit()

    page = client.get('/meine-buchungen')
    assert "Angenommen" in page
    assert "Stornieren" in page
    assert "Entfernen" not in page
    assert "nicht genügend Teilnehmer" not in page

    # Other states are shown too
    states = [
        ('cancelled', "Storniert"),
        ('denied', "Abgelehnt"),
        ('blocked', "Blockiert")
    ]

    for state, text in states:
        bookings.query().one().state = state
        transaction.commit()

        assert text in client.get('/meine-buchungen')

    # If there are not enough attendees, show a warning
    periods.query().one().confirmed = True
    bookings.query().one().state = 'accepted'
    occasions.query().one().spots = NumericRange(2, 5)

    transaction.commit()

    page = client.get('/meine-buchungen')
    assert "nicht genügend Teilnehmer" in page


def test_direct_booking_and_storno(feriennet_app):
    activities = ActivityCollection(feriennet_app.session(), type='vacation')
    attendees = AttendeeCollection(feriennet_app.session())
    periods = PeriodCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())

    owner = Bunch(username='admin@example.org')

    prebooking = tuple(d.date() for d in (
        datetime.now() - timedelta(days=1),
        datetime.now() + timedelta(days=1)
    ))

    execution = tuple(d.date() for d in (
        datetime.now() + timedelta(days=10),
        datetime.now() + timedelta(days=12)
    ))

    period = periods.add(
        title="Ferienpass 2016",
        prebooking=prebooking,
        execution=execution,
        active=True,
        deadline_date=(datetime.utcnow() + timedelta(days=1)).date()
    )

    member = UserCollection(feriennet_app.session()).add(
        'member@example.org', 'hunter2', 'member')

    period.confirmed = True

    foobar = activities.add("Foobar", username='admin@example.org')
    foobar.propose().accept()

    occasions.add(
        start=datetime(2016, 11, 25, 8),
        end=datetime(2016, 11, 25, 16),
        age=(0, 10),
        spots=(0, 1),
        timezone="Europe/Zurich",
        activity=foobar,
        period=period
    )

    attendees.add(owner, 'Dustin', date(2008, 1, 1), 'female')
    attendees.add(member, 'Mike', date(2008, 1, 1), 'female')

    transaction.commit()

    client = Client(feriennet_app)
    client.login_admin()

    member = Client(feriennet_app)
    member.login('member@example.org', 'hunter2')

    # in a confirmed period parents can book directly
    page = client.get('/angebot/foobar')
    assert "1 Plätze frei" in page

    other = member.get('/angebot/foobar').click('Anmelden')

    page = page.click('Anmelden')
    booked = page.form.submit().follow()
    assert "Ausgebucht" in booked
    assert "Dustin" in booked

    other = other.form.submit()
    assert "ist bereits ausgebucht" in other

    page = page.form.submit()
    assert "bereits für diese Durchführung angemeldet" in page

    # cancel the booking
    page = client.get('/meine-buchungen')
    client.post(get_post_url(page, 'confirm'))

    page = client.get('/angebot/foobar')
    assert "1 Plätze frei" in page

    # admins may do this for other members
    url = page.click('Anmelden').pyquery('select option:last').val()
    page = client.get(url)

    other_url = page.request.url
    assert "Mike" in page
    assert "Für <strong>member@example.org</strong>" in page

    # members may not (simply ignores the other user)
    page = member.get('/angebot/foobar').click('Anmelden')
    assert "admin@example.org" not in page

    page = member.get(other_url.replace('member@', 'admin@'))
    assert "Für <strong>admin@example.org</strong>" not in page
    assert "Mike" in page


def test_cancel_occasion(feriennet_app):
    activities = ActivityCollection(feriennet_app.session(), type='vacation')
    attendees = AttendeeCollection(feriennet_app.session())
    periods = PeriodCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())

    owner = Bunch(username='admin@example.org')

    prebooking = tuple(d.date() for d in (
        datetime.now() - timedelta(days=1),
        datetime.now() + timedelta(days=1)
    ))

    execution = tuple(d.date() for d in (
        datetime.now() + timedelta(days=10),
        datetime.now() + timedelta(days=12)
    ))

    period = periods.add(
        title="Ferienpass 2016",
        prebooking=prebooking,
        execution=execution,
        active=True
    )
    period.confirmed = True

    member = UserCollection(feriennet_app.session()).add(
        'member@example.org', 'hunter2', 'member')

    foobar = activities.add("Foobar", username='admin@example.org')
    foobar.propose().accept()

    occasions.add(
        start=datetime(2016, 11, 25, 8),
        end=datetime(2016, 11, 25, 16),
        age=(0, 10),
        spots=(0, 1),
        timezone="Europe/Zurich",
        activity=foobar,
        period=period
    )

    attendees.add(owner, 'Dustin', date(2008, 1, 1), 'female')
    attendees.add(member, 'Mike', date(2008, 1, 1), 'female')

    transaction.commit()

    client = Client(feriennet_app)
    client.login_admin()

    page = client.get('/angebot/foobar')
    assert "L&#246;schen" in page
    assert "Absagen" not in page
    assert "Reaktivieren" not in page

    page.click('Anmelden').form.submit()
    assert "Angenommen" in client.get('/meine-buchungen')

    page = client.get('/angebot/foobar')
    assert "L&#246;schen" not in page
    assert "Absagen" in page
    assert "Reaktivieren" not in page

    client.post(get_post_url(page, 'confirm'))
    assert "Storniert" in client.get('/meine-buchungen')

    page = client.get('/angebot/foobar')
    assert "L&#246;schen" not in page
    assert "Absagen" not in page
    assert "Reaktivieren" in page

    client.post(get_post_url(page, 'confirm'))
    assert "Storniert" in client.get('/meine-buchungen')

    page = client.get('/angebot/foobar')
    assert "L&#246;schen" not in page
    assert "Absagen" in page
    assert "Reaktivieren" not in page

    client.delete(get_delete_link(client.get('/meine-buchungen')))
    page = client.get('/angebot/foobar')
    assert "L&#246;schen" in page
    assert "Absagen" not in page
    assert "Reaktivieren" not in page

    client.delete(get_delete_link(page))


def test_billing(feriennet_app):

    activities = ActivityCollection(feriennet_app.session(), type='vacation')
    attendees = AttendeeCollection(feriennet_app.session())
    periods = PeriodCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())
    bookings = BookingCollection(feriennet_app.session())

    owner = Bunch(username='admin@example.org')

    prebooking = tuple(d.date() for d in (
        datetime.now() - timedelta(days=1),
        datetime.now() + timedelta(days=1)
    ))

    execution = tuple(d.date() for d in (
        datetime.now() + timedelta(days=10),
        datetime.now() + timedelta(days=12)
    ))

    period = periods.add(
        title="Ferienpass 2016",
        prebooking=prebooking,
        execution=execution,
        active=True
    )
    period.confirmed = True

    member = UserCollection(feriennet_app.session()).add(
        'member@example.org', 'hunter2', 'member')

    foobar = activities.add("Foobar", username='admin@example.org')
    foobar.propose().accept()

    o1 = occasions.add(
        start=datetime(2016, 11, 25, 8),
        end=datetime(2016, 11, 25, 16),
        age=(0, 10),
        spots=(0, 2),
        timezone="Europe/Zurich",
        activity=foobar,
        period=period,
        cost=100,
    )

    o2 = occasions.add(
        start=datetime(2016, 11, 25, 17),
        end=datetime(2016, 11, 25, 20),
        age=(0, 10),
        spots=(0, 2),
        timezone="Europe/Zurich",
        activity=foobar,
        period=period,
        cost=1000,
    )

    a1 = attendees.add(owner, 'Dustin', date(2000, 1, 1), 'female')
    a2 = attendees.add(member, 'Mike', date(2000, 1, 1), 'female')

    b1 = bookings.add(owner, a1, o1)
    b2 = bookings.add(owner, a1, o2)
    b3 = bookings.add(member, a2, o1)
    b4 = bookings.add(member, a2, o2)

    b1.state = 'accepted'
    b2.state = 'cancelled'
    b3.state = 'accepted'
    b4.state = 'accepted'

    b1.cost = 100
    b2.cost = 1000
    b3.cost = 100
    b4.cost = 1000

    transaction.commit()

    admin = Client(feriennet_app)
    admin.login_admin()

    member = Client(feriennet_app)
    member.login('member@example.org', 'hunter2')

    page = admin.get('/angebote').click('Fakturierung')
    assert "noch keine Rechnungen" in page

    page = page.form.submit()
    assert "member@example.org" in page
    assert "admin@example.org" in page

    # as long as the period is not finalized, there's no way to pay
    page = admin.get('/rechnungen?username=admin@example.org')
    assert page.pyquery('.outstanding').text() == '100.00 Ausstehend'

    page = admin.get('/rechnungen?username=member@example.org')
    assert page.pyquery('.outstanding').text() == '1100.00 Ausstehend'

    assert 'mark-paid' not in page

    # as long as the period is not finalized, there are no invoices
    assert member.get('/').pyquery('.invoices-count').attr['data-count'] == '0'
    assert admin.get('/').pyquery('.invoices-count').attr['data-count'] == '0'
    assert "noch keine Rechnungen" in member.get('/meine-rechnungen')
    assert "noch keine Rechnungen" in admin.get('/meine-rechnungen')

    # once the period is finalized, the invoices become public and they
    # may be marked as paid
    page = admin.get('/angebote').click('Fakturierung')
    page.form['confirm'] = 'yes'
    page.form['sure'] = 'yes'
    page = page.form.submit()

    assert member.get('/').pyquery('.invoices-count').attr['data-count'] == '1'
    assert admin.get('/').pyquery('.invoices-count').attr['data-count'] == '1'
    assert "noch keine Rechnungen" not in member.get('/meine-rechnungen')
    assert "noch keine Rechnungen" not in admin.get('/meine-rechnungen')
    assert "Ferienpass 2016" in member.get('/meine-rechnungen')
    assert "Ferienpass 2016" in admin.get('/meine-rechnungen')

    page = admin.get('/rechnungen?username=member@example.org')
    assert '1100.00 Ausstehend' in page.pyquery('.outstanding').text()

    admin.post(get_post_url(page, 'mark-paid:last'))

    page = admin.get('/rechnungen?username=member@example.org')

    # occsaions with the same title (here the same activity) is not defined
    assert '1000.00 Ausstehend' in page.pyquery('.outstanding').text() or\
        '100.00 Ausstehend' in page.pyquery('.outstanding').text()

    admin.post(get_post_url(page, 'mark-unpaid'))

    page = admin.get('/rechnungen?username=member@example.org')
    assert '1100.00 Ausstehend' in page.pyquery('.outstanding').text()

    admin.post(get_post_url(page, 'mark-paid:first'))

    page = admin.get('/rechnungen?username=member@example.org')
    assert 'Bezahlt' in page.pyquery('.outstanding').text()

    assert member.get('/').pyquery('.invoices-count').attr['data-count'] == '0'


def test_reactivate_cancelled_booking(feriennet_app):

    activities = ActivityCollection(feriennet_app.session(), type='vacation')
    attendees = AttendeeCollection(feriennet_app.session())
    periods = PeriodCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())
    bookings = BookingCollection(feriennet_app.session())

    owner = Bunch(username='admin@example.org')

    prebooking = tuple(d.date() for d in (
        datetime.now() - timedelta(days=1),
        datetime.now() + timedelta(days=1)
    ))

    execution = tuple(d.date() for d in (
        datetime.now() + timedelta(days=10),
        datetime.now() + timedelta(days=12)
    ))

    period = periods.add(
        title="Ferienpass 2016",
        prebooking=prebooking,
        execution=execution,
        active=True
    )

    foobar = activities.add("Foobar", username='admin@example.org')
    foobar.propose().accept()

    occasions.add(
        start=datetime(2016, 11, 25, 8),
        end=datetime(2016, 11, 25, 16),
        age=(0, 10),
        spots=(0, 2),
        timezone="Europe/Zurich",
        activity=foobar,
        period=period,
        cost=100,
    )

    occasions.add(
        start=datetime(2016, 11, 25, 17),
        end=datetime(2016, 11, 25, 20),
        age=(0, 10),
        spots=(0, 2),
        timezone="Europe/Zurich",
        activity=foobar,
        period=period,
        cost=1000,
    )

    attendees.add(owner, 'Dustin', date(2008, 1, 1), 'female')

    transaction.commit()

    client = Client(feriennet_app)
    client.login_admin()

    # by default we block conflicting bookings
    page = client.get('/angebot/foobar').click('Anmelden', index=0)
    page = page.form.submit().follow()

    assert "Wunschliste hinzugefügt" in page

    page = client.get('/angebot/foobar').click('Anmelden', index=0)
    assert "bereits für diese Durchführung angemeldet" in page.form.submit()

    page = client.get('/angebot/foobar').click('Anmelden', index=1)
    assert "eine andere Durchführung" in page.form.submit()

    # unless they are cancelled
    bookings.query().first().state = 'cancelled'
    transaction.commit()  # can be done by cancelling the whole event in UI

    page = client.get('/angebot/foobar').click('Anmelden', index=0)
    assert "Wunschliste hinzugefügt" in page.form.submit().follow()

    # this also works between multiple occasions of the same activity
    bookings.query().first().state = 'cancelled'
    transaction.commit()  # can be done by cancelling the whole event in UI

    page = client.get('/angebot/foobar').click('Anmelden', index=1)
    assert "Wunschliste hinzugefügt" in page.form.submit().follow()

    # and even if we confirm the period
    page = client.get('/angebote').click('Zuteilung')
    page.form['confirm'] = 'yes'
    page.form['sure'] = 'yes'
    page.form.submit()

    page = client.get('/meine-buchungen')
    client.post(get_post_url(page, 'confirm'))  # cancel the booking

    page = client.get('/angebot/foobar').click('Anmelden', index=0)
    assert "war erfolgreic" in page.form.submit().follow()

    page = client.get('/meine-buchungen')
    client.post(get_post_url(page, 'confirm'))  # cancel the booking

    page = client.get('/angebot/foobar').click('Anmelden', index=1)
    assert "war erfolgreich" in page.form.submit().follow()


def test_occasion_attendance_collection(feriennet_app):

    activities = ActivityCollection(feriennet_app.session(), type='vacation')
    attendees = AttendeeCollection(feriennet_app.session())
    periods = PeriodCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())
    bookings = BookingCollection(feriennet_app.session())

    owner = Bunch(username='admin@example.org')

    prebooking = tuple(d.date() for d in (
        datetime.now() - timedelta(days=1),
        datetime.now() + timedelta(days=1)
    ))

    execution = tuple(d.date() for d in (
        datetime.now() + timedelta(days=10),
        datetime.now() + timedelta(days=12)
    ))

    period = periods.add(
        title="Ferienpass 2016",
        prebooking=prebooking,
        execution=execution,
        active=True
    )

    foo = activities.add("Foo", username='admin@example.org')
    foo.propose().accept()

    bar = activities.add("Bar", username='editor@example.org')
    bar.propose().accept()

    o1 = occasions.add(
        start=datetime(2016, 11, 25, 8),
        end=datetime(2016, 11, 25, 16),
        age=(0, 10),
        spots=(0, 2),
        timezone="Europe/Zurich",
        activity=foo,
        period=period,
    )

    o2 = occasions.add(
        start=datetime(2016, 11, 25, 17),
        end=datetime(2016, 11, 25, 20),
        age=(0, 10),
        spots=(0, 2),
        timezone="Europe/Zurich",
        activity=bar,
        period=period,
    )

    a1 = attendees.add(owner, 'Dustin', date(2000, 1, 1), 'female')
    a2 = attendees.add(owner, 'Mike', date(2000, 1, 1), 'female')

    bookings.add(owner, a1, o1).state = 'accepted'
    bookings.add(owner, a2, o2).state = 'accepted'

    transaction.commit()

    # anonymous has no access
    anon = Client(feriennet_app)
    assert anon.get('/teilnehmer', status=403)

    # if the period is unconfirmed the attendees are not shown
    admin = Client(feriennet_app)
    admin.login_admin()

    page = admin.get('/teilnehmer')
    assert "noch keine Zuteilung" in page
    assert "Dustin" not in page

    # organisers only see their own occasions
    periods.active().confirmed = True
    transaction.commit()

    editor = Client(feriennet_app)
    editor.login_editor()

    page = editor.get('/teilnehmer')
    assert "Dustin" not in page
    assert "Mike" in page

    # admins seel all the occasions
    page = admin.get('/teilnehmer')
    assert "Dustin" in page
    assert "Mike" in page

    # if the emergency info is given, it is shown
    page = admin.get('/benutzerprofil')
    page.form['salutation'] = 'mr'
    page.form['first_name'] = 'foo'
    page.form['last_name'] = 'bar'
    page.form['zip_code'] = '123'
    page.form['place'] = 'abc'
    page.form['emergency'] = '123456789 Admin'
    page.form.submit()

    assert "123456789 Admin" in admin.get('/teilnehmer')


def test_send_email(feriennet_app):

    client = Client(feriennet_app)
    client.login_admin()

    prebooking = tuple(d.date() for d in (
        datetime.now() - timedelta(days=1),
        datetime.now() + timedelta(days=1)
    ))

    execution = tuple(d.date() for d in (
        datetime.now() + timedelta(days=10),
        datetime.now() + timedelta(days=12)
    ))

    periods = PeriodCollection(feriennet_app.session())
    periods.add(
        title="Ferienpass 2016",
        prebooking=prebooking,
        execution=execution,
        active=True
    )

    transaction.commit()

    page = client.get('/mitteilungen').click('Neue Mitteilungs-Vorlage')
    page.form['subject'] = '[Periode] subject'
    page.form['text'] = '[Periode] body'
    page = page.form.submit().follow()

    page = page.click('Versand')
    assert "Ferienpass 2016 subject" in page
    assert "Ferienpass 2016 body" in page
    assert "keine Empfänger gefunden" in page.form.submit()

    page.form['roles'] = ['admin', 'editor']
    assert "an 2 Empfänger gesendet" in page.form.submit().follow()
    assert len(feriennet_app.smtp.outbox) == 2

    message = get_message(feriennet_app, 0)
    assert "Ferienpass 2016 subject" in feriennet_app.smtp.outbox[0]['subject']
    assert "Ferienpass 2016 body" in message


def test_import_account_statement(feriennet_app):
    activities = ActivityCollection(feriennet_app.session(), type='vacation')
    attendees = AttendeeCollection(feriennet_app.session())
    periods = PeriodCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())
    bookings = BookingCollection(feriennet_app.session())

    owner = Bunch(username='admin@example.org')

    prebooking = tuple(d.date() for d in (
        datetime.now() - timedelta(days=1),
        datetime.now() + timedelta(days=1)
    ))

    execution = tuple(d.date() for d in (
        datetime.now() + timedelta(days=10),
        datetime.now() + timedelta(days=12)
    ))

    period = periods.add(
        title="Ferienpass 2016",
        prebooking=prebooking,
        execution=execution,
        active=True
    )
    period.confirmed = True

    foobar = activities.add("Foobar", username='admin@example.org')
    foobar.propose().accept()

    o = occasions.add(
        start=datetime(2016, 11, 25, 8),
        end=datetime(2016, 11, 25, 16),
        age=(0, 10),
        spots=(0, 2),
        timezone="Europe/Zurich",
        activity=foobar,
        period=period,
        cost=100,
    )

    a = attendees.add(owner, 'Dustin', date(2000, 1, 1), 'female')
    b = bookings.add(owner, a, o)
    b.state = 'accepted'
    b.cost = 100

    transaction.commit()

    admin = Client(feriennet_app)
    admin.login_admin()

    page = admin.get('/').click('Fakturierung')
    page.form['confirm'] = 'yes'
    page.form['sure'] = 'yes'
    page = page.form.submit()

    page = page.click('Kontoauszug Importieren')
    assert "kein Bankkonto" in page

    settings = page.click('Einstellungen', index=1)
    settings.form['bank_account'] = 'CH6309000000250097798'
    settings = settings.form.submit()

    page = page.click('Rechnungen')
    code = page.pyquery('.invoice-items-payment li:last').text()

    page = page.click('Fakturierung').click('Kontoauszug Importieren')
    assert "kein Bankkonto" not in page

    xml = generate_xml([
        dict(amount='100.00 CHF', note=code)
    ])

    page.form['xml'] = Upload(
        'account.xml',
        xml.encode('utf-8'),
        'application/xml'
    )

    page = page.form.submit()

    assert "1 Zahlungen importieren" in page
    admin.post(get_post_url(page, 'button'))

    page = admin.get('/meine-rechnungen')
    assert "1 Zahlungen wurden importiert" in page
    assert "unpaid" not in page

    page = page.click('Fakturierung').click('Kontoauszug Importieren')
    page.form['xml'] = Upload(
        'account.xml',
        xml.encode('utf-8'),
        'application/xml'
    )
    page = page.form.submit()

    assert "0 Zahlungen importieren" in page


def test_deadline(feriennet_app):

    activities = ActivityCollection(feriennet_app.session(), type='vacation')
    periods = PeriodCollection(feriennet_app.session())
    occasions = OccasionCollection(feriennet_app.session())

    prebooking = tuple(d.date() for d in (
        datetime.now() - timedelta(days=1),
        datetime.now() + timedelta(days=1)
    ))

    execution = tuple(d.date() for d in (
        datetime.now() + timedelta(days=10),
        datetime.now() + timedelta(days=12)
    ))

    period = periods.add(
        title="Ferienpass 2016",
        prebooking=prebooking,
        execution=execution,
        active=True
    )

    foo = activities.add("Foo", username='admin@example.org')
    foo.propose().accept()

    occasions.add(
        start=datetime(2016, 11, 25, 8),
        end=datetime(2016, 11, 25, 16),
        age=(0, 10),
        spots=(0, 2),
        timezone="Europe/Zurich",
        activity=foo,
        period=period,
    )

    transaction.commit()

    # show no 'enroll' for ordinary users past the deadline
    period = periods.active()
    period.deadline_date = datetime.utcnow().date() - timedelta(days=1)

    transaction.commit()

    anonymous = Client(feriennet_app)
    assert "Anmelden" not in anonymous.get('/angebot/foo')

    # do show it for admins though and allow signups
    admin = Client(feriennet_app)
    admin.login_admin()

    assert "Anmelden" in admin.get('/angebot/foo')

    page = admin.get('/angebot/foo').click("Anmelden")
    assert "Der Anmeldeschluss wurde erreicht" not in page.form.submit()

    # stop others, even if they get to the form
    editor = Client(feriennet_app)
    editor.login_editor()

    page = editor.get(page.request.url.replace('http://localhost', ''))
    assert "Der Anmeldeschluss wurde erreicht" in page.form.submit()
