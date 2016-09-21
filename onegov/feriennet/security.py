from morepath.authentication import NO_IDENTITY
from onegov.activity import Activity
from onegov.core.security import Public
from onegov.feriennet import FeriennetApp
from sqlalchemy import or_


#: Describes the states which are visible to the given role (not taking
# ownership in account!)
VISIBLE_ACTIVITY_STATES = {
    'admin': (
        'proposed',
        'accepted',
        'denied',
        'archived'
    ),
    'editor': (
        'accepted',
    ),
    'member': (
        'accepted',
    ),
    'anonymous': (
        'accepted',
    )
}


def is_owner(username, activity):
    """ Returns true if the given username is the owner of the given
    activity.

    """
    if not username:
        return False

    return username == activity.username


class ActivityQueryPolicy(object):
    """ Limits activity queries depending on the current user. """

    def __init__(self, username, role):
        self.username = username
        self.role = role

    @classmethod
    def for_identity(cls, identity):
        if identity is None or identity is NO_IDENTITY:
            return cls(None, None)
        else:
            return cls(identity.userid, identity.role)

    def granted_subset(self, query):
        """ Limits the given activites query for the given user. """

        if self.username is None or self.role not in ('admin', 'editor'):
            return self.public_subset(query)
        else:
            return self.private_subset(query)

    def public_subset(self, query):
        """ Limits the given query to activites meant for the public. """
        return query.filter(
            Activity.state.in_(VISIBLE_ACTIVITY_STATES['anonymous'])
        )

    def private_subset(self, query):
        """ Limits the given query to activites meant for admins/owners.

        Admins see all states (except for previews) and everyone sees all the
        states if they own the activity.
        """

        assert self.role and self.username

        return query.filter(or_(
            Activity.state.in_(VISIBLE_ACTIVITY_STATES[self.role]),
            Activity.username == self.username
        ))


@FeriennetApp.permission_rule(model=Activity, permission=Public, identity=None)
def has_public_permission_not_logged_in(identity, model, permission):
    """ Overrides the public permission rule of activites for anonymous users.
    """
    assert permission is Public

    return model.state in VISIBLE_ACTIVITY_STATES['anonymous']


@FeriennetApp.permission_rule(model=Activity, permission=Public)
def has_public_permission_logged_in(identity, model, permission):
    """ Overrides the public permission rule of activites for logged-in users.
    """

    # roles other than admin/editor are basically treated as anonymous,
    # so fallback in this case
    if identity.role not in ('admin', 'editor'):
        return has_public_permission_not_logged_in(None, model, permission)

    return is_owner(identity.userid, model) \
        or model.state in VISIBLE_ACTIVITY_STATES[identity.role]