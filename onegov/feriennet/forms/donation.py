from onegov.feriennet import _
from onegov.form import Form
from onegov.feriennet.const import DEFAULT_DONATION_AMOUNTS
from onegov.feriennet.utils import format_donation_amounts
from wtforms.fields import RadioField
from wtforms.validators import InputRequired


class DonationForm(Form):

    amount = RadioField(
        label=_("My donation"),
        choices=[],
        validators=[InputRequired()]
    )

    def on_request(self):
        amounts = self.request.app.org.meta.get(
            'donation_amounts', DEFAULT_DONATION_AMOUNTS)

        strings = format_donation_amounts(amounts).split('\n')

        self.amount.choices = tuple(zip(amounts, strings))
