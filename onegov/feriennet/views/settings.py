from onegov.core.security import Secret
from onegov.feriennet import _
from onegov.feriennet.app import FeriennetApp
from onegov.feriennet.const import DEFAULT_DONATION_AMOUNTS
from onegov.feriennet.utils import format_donation_amounts
from onegov.feriennet.utils import parse_donation_amounts
from onegov.form import Form
from onegov.form.fields import MultiCheckboxField
from onegov.form.validators import Stdnum
from onegov.org.forms.fields import HtmlField
from onegov.org.models import Organisation
from onegov.org.views.settings import handle_generic_settings
from wtforms.fields import BooleanField, StringField, RadioField, TextAreaField
from wtforms.fields.html5 import URLField
from wtforms.validators import InputRequired


class FeriennetSettingsForm(Form):

    bank_account = StringField(
        label=_("Bank Account (IBAN)"),
        fieldset=_("Payment"),
        validators=[Stdnum(format='iban')]
    )

    bank_beneficiary = StringField(
        label=_("Beneficiary"),
        fieldset=_("Payment"),
    )

    bank_reference_schema = RadioField(
        label=_("Payment Order"),
        fieldset=_("Payment"),
        choices=[
            ('feriennet-v1', _("Basic")),
            ('esr-v1', _("ESR (General)")),
            ('raiffeisen-v1', _("ESR (Raiffeisen)"))
        ],
        default='feriennet-v1'
    )

    bank_esr_participant_number = StringField(
        label=_("ESR participant number"),
        fieldset=_("Payment"),
        validators=[InputRequired()],
        depends_on=('bank_reference_schema', '!feriennet-v1')
    )

    bank_esr_identification_number = StringField(
        label=_("ESR identification number"),
        fieldset=_("Payment"),
        validators=[InputRequired()],
        depends_on=('bank_reference_schema', 'raiffeisen-v1')
    )

    show_political_municipality = BooleanField(
        label=_("Require the political municipality in the userprofile"),
        fieldset=_("Userprofile"))

    show_related_contacts = BooleanField(
        label=_(
            "Parents can see the contacts of other parents in "
            "the same activity"
        ),
        fieldset=_("Privacy")
    )

    public_organiser_data = MultiCheckboxField(
        label=_("Public organiser data"),
        choices=(
            ('name', _("Name")),
            ('address', _("Address")),
            ('email', _("E-Mail")),
            ('phone', _("Phone")),
            ('website', _("Website"))
        ),
        fieldset=_("Organiser")
    )

    tos_url = URLField(
        label=_("Link to the TOS"),
        description=_("Require users to accept the TOS before booking"),
        fieldset=_("TOS")
    )

    donation = BooleanField(
        label=_("Donations"),
        description=_("Show a donation button in the invoice view"),
        default=True,
        fieldset=_("Donation"))

    donation_amounts = TextAreaField(
        label=_("Donation Amounts"),
        description=_("One amount per line"),
        depends_on=('donation', 'y'),
        render_kw={'rows': 3},
        fieldset=_("Donation"))

    donation_description = HtmlField(
        label=_("Description"),
        depends_on=('donation', 'y'),
        fieldset=_("Donation"),
        render_kw={'rows': 10})

    def ensure_beneificary_if_bank_account(self):
        if self.bank_account.data and not self.bank_beneficiary.data:
            self.bank_beneficiary.errors.append(_(
                "A beneficiary is required if a bank account is given."
            ))
            return False

    def ensure_valid_esr_identification_number(self):
        if self.bank_reference_schema.data == 'raiffeisen-v1':
            ident = self.bank_esr_identification_number.data

            if not 3 <= len(ident.replace('-', ' ').strip()) <= 6:
                self.bank_esr_identification_number.errors.append(_(
                    "The ESR identification number must be 3-6 characters long"
                ))
                return False

    def process_obj(self, obj):
        super().process_obj(obj)

        attributes = (
            ('show_political_municipality', False),
            ('show_related_contacts', False),
            ('public_organiser_data', self.request.app.public_organiser_data),
            ('bank_account', ''),
            ('bank_beneficiary', ''),
            ('bank_reference_schema', 'feriennet-v1'),
            ('bank_esr_participant_number', ''),
            ('bank_esr_identification_number', ''),
            ('tos_url', ''),
            ('donation', True),
            ('donation_amounts', DEFAULT_DONATION_AMOUNTS),
            ('donation_description', ''),
        )

        for attr, default in attributes:
            value = obj.meta.get(attr, default)

            if attr == 'donation_amounts':
                value = format_donation_amounts(value)

            getattr(self, attr).data = value

    def populate_obj(self, obj, *args, **kwargs):
        super().populate_obj(obj, *args, **kwargs)

        attributes = (
            'show_political_municipality',
            'show_related_contacts',
            'public_organiser_data',
            'bank_account',
            'bank_beneficiary',
            'bank_reference_schema',
            'bank_esr_participant_number',
            'bank_esr_identification_number',
            'tos_url',
            'donation',
            'donation_amounts',
            'donation_description',
        )

        for attr in attributes:
            value = getattr(self, attr).data

            if attr == 'donation_amounts':
                value = parse_donation_amounts(value)

            obj.meta[attr] = value


@FeriennetApp.form(model=Organisation, name='feriennet-settings',
                   template='form.pt', permission=Secret,
                   form=FeriennetSettingsForm, setting=_("Feriennet"),
                   icon='fa-child')
def custom_handle_settings(self, request, form):
    return handle_generic_settings(self, request, form, _("Feriennet"))
