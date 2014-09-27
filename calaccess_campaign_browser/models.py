from django.db import models
from django.db.models import Sum
from hurry.filesize import size
from django.utils.text import slugify
from django.core.urlresolvers import reverse
from django.utils.datastructures import SortedDict
from .utils.models import AllCapsNameMixin, BaseModel


class Filer(AllCapsNameMixin):
    """
    An entity that files campaign finance disclosure documents.

    That includes candidates for public office that have committees raising
    money on their behalf (i.e. Jerry Brown) as well as Political Action
    Committees (PACs) that contribute money to numerous candidates for office.
    """
    # straight out of the filer table
    filer_id = models.IntegerField(db_index=True)
    STATUS_CHOICES = (
        ('A', 'A'),
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('R', 'R'),
        ('S', 'S'),
        ('TERMINATED', 'Terminated'),
        ('W', 'W'),
    )
    status = models.CharField(
        max_length=255,
        null=True,
        choices=STATUS_CHOICES
    )
    FILER_TYPE_OPTIONS = (
        ('pac', 'PAC'),
        ('cand', 'Candidate'),
    )
    filer_type = models.CharField(
        max_length=10,
        choices=FILER_TYPE_OPTIONS,
        db_index=True,
    )
    name = models.CharField(max_length=255, null=True)
    effective_date = models.DateField(null=True)
    xref_filer_id = models.CharField(
        max_length=32,
        null=True,
        db_index=True
    )

    class Meta:
        ordering = ("name",)

    @models.permalink
    def get_absolute_url(self):
        return ('filer_detail', [str(self.pk)])

    @property
    def slug(self):
        return slugify(self.name)

    @property
    def real_filings(self):
        return Filing.objects.filter(
            committee__filer=self,
            is_duplicate=False
        )

    @property
    def total_contributions(self):
        summaries = [f.summary for f in self.real_filings]
        summaries = [s for s in summaries if s]
        return sum([
            s.total_contributions for s in summaries if s.total_contributions
        ])


class Committee(AllCapsNameMixin):
    """
    If a Candidate controls the committee, the filer is associated with the
    Candidate Filer record, not the committee Filer record
    But the committee Filer record can still be accessed using filer_id_raw
    So candidate filers potentially link to multiple committes,
    and committee filers that are not candidate controlled
    link back to one, committee filer
    If there's a better way I'm open to suggestions
    """
    filer = models.ForeignKey(Filer)
    filer_id_raw = models.IntegerField(db_index=True)
    xref_filer_id = models.CharField(
        max_length=32,
        null=True,
        db_index=True
    )
    name = models.CharField(max_length=255, null=True)
    CMTE_TYPE_OPTIONS = (
        ('cand', 'Candidate'),
        ('pac', 'PAC'),
        ('linked-pac', 'Non-Candidate Committee, linked to other committees'),
    )
    committee_type = models.CharField(
        max_length=50,
        choices=CMTE_TYPE_OPTIONS,
        db_index=True,
    )

    class Meta:
        ordering = ("name",)

    def get_absolute_url(self):
        return reverse('committee_detail', args=[str(self.pk)])

    def get_calaccess_url(self):
        url = "http://cal-access.ss.ca.gov/Campaign/Committees/Detail.aspx?id="
        return url + str(self.filer_id_raw) 

    @property
    def real_filings(self):
        return Filing.objects.filter(
            committee=self,
            is_duplicate=False
        ).select_related("cycle")

    @property
    def total_contributions(self):
        summaries = [f.summary for f in self.real_filings]
        summaries = [s for s in summaries if s]
        return sum([
            s.total_contributions for s in summaries if s.total_contributions
        ])

    @property
    def total_expenditures(self):
        summaries = [f.summary for f in self.real_filings]
        summaries = [s for s in summaries if s]
        return sum([
            s.total_expenditures for s in summaries if s.total_expenditures
        ])


class Cycle(BaseModel):
    name = models.IntegerField(db_index=True)

    class Meta:
        ordering = ("-name",)

    def __unicode__(self):
        return unicode(self.name)


class FilingPeriod(BaseModel):
    """
    A required quarterly reporting period for committees.
    """
    period_id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=25, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    deadline = models.DateField()

    class Meta:
        ordering = ("-end_date",)

    def __unicode__(self):
        return "%s - %s" % (self.start_date, self.end_date)


class Filing(models.Model):
    cycle = models.ForeignKey(Cycle)
    committee = models.ForeignKey(Committee)
    filing_id_raw = models.IntegerField('filing ID', db_index=True)
    amend_id = models.IntegerField('amendment', db_index=True)
    FORM_TYPE_CHOICES = (
        ('F460', 'F460: Quarterly'),
        ('F450', 'F450: Quarterly (Short)'),
    )
    form_type = models.CharField(
        max_length=7,
        db_index=True,
        choices=FORM_TYPE_CHOICES
    )
    period = models.ForeignKey(FilingPeriod, null=True)
    start_date = models.DateField(null=True)
    end_date = models.DateField(null=True)
    date_received = models.DateField(null=True)
    date_filed = models.DateField(null=True)
    is_duplicate = models.BooleanField(
        default=False,
        db_index=True,
        help_text="A record that has either been superceded by an amendment \
or was filed unnecessarily. Should be excluded from most analysis."
    )

    def __unicode__(self):
        return unicode(self.filing_id_raw)

    def get_absolute_url(self):
        return reverse('filing_detail', args=[str(self.pk)])

    def get_calaccess_pdf_url(self):
        url = "http://cal-access.ss.ca.gov/PDFGen/pdfgen.prg"
        qs = "filingid=%s&amendid=%s" % (
            self.filing_id_raw,
            self.amend_id
        )
        return "%s?%s" % (url, qs)

    def committee_short_name(self):
        return self.committee.short_name
    committee_short_name.short_description = "committee"

    @property
    def summary(self):
        try:
            return Summary.objects.get(
                filing_id_raw=self.filing_id_raw,
                amend_id=self.amend_id
            )
        except Summary.DoesNotExist:
            return None

    def is_amendment(self):
        return self.amend_id > 0


class Summary(BaseModel):
    filing_id_raw = models.IntegerField(db_index=True)
    amend_id = models.IntegerField(db_index=True)
    itemized_monetary_contributions = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        default=None,
    )
    unitemized_monetary_contributions = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        default=None,
    )
    total_monetary_contributions = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        default=None,
    )
    non_monetary_contributions = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        default=None,
    )
    total_contributions = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        default=None,
    )
    itemized_expenditures = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        default=None,
    )
    unitemized_expenditures = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        default=None,
    )
    total_expenditures = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        default=None,
    )
    ending_cash_balance = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        default=None,
    )
    outstanding_debts = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        default=None,
    )

    class Meta:
        verbose_name_plural = "summaries"

    def __unicode__(self):
        return unicode(self.filing_id_raw)

    @property
    def cycle(self):
        try:
            return self.filing.cycle
        except:
            return None

    @property
    def committee(self):
        try:
            return self.filing.committee
        except:
            return None

    @property
    def filing(self):
        try:
            return Filing.objects.get(
                filing_id_raw=self.filing_id_raw,
                amend_id=self.amend_id
            )
        except Filing.DoesNotExist:
            return None


class Expenditure(BaseModel):
    """
    Who got paid and how much.
    """
    EXPENDITURE_CODE_CHOICES = (
        ('CMP', 'campaign paraphernalia/misc.'),
        ('CNS', 'campaign consultants'),
        ('CTB', 'contribution (explain nonmonetary)*'),
        ('CVC', 'civic donations'),
        ('FIL', 'candidate filing/ballot fees'),
        ('FND', 'fundraising events'),
        ('IND',
         'independent expenditure supporting/opposing others (explain)*'),
        ('LEG', 'legal defense'),
        ('LIT', 'campaign literature and mailings'),
        ('MBR', 'member communications'),
        ('MTG', 'meetings and appearances'),
        ('OFC', 'office expenses'),
        ('PET', 'petition circulating'),
        ('PHO', 'phone banks'),
        ('POL', 'polling and survey research'),
        ('POS', 'postage, delivery and messenger services'),
        ('PRO', 'professional services (legal, accounting)'),
        ('PRT', 'print ads'),
        ('RAD', 'radio airtime and production costs'),
        ('RFD', 'returned contributions'),
        ('SAL', "campaign workers' salaries"),
        ('TEL', 't.v. or cable airtime and production costs'),
        ('TRC', 'candidate travel, lodging, and meals'),
        ('TRS', 'staff/spouse travel, lodging, and meals'),
        ('TSF', 'transfer between committees of the same candidate/sponsor'),
        ('VOT', 'voter registration'),
        ('WEB', 'information technology costs (internet, e-mail)'),
    )
    cycle = models.ForeignKey(Cycle)
    committee = models.ForeignKey(Committee)
    filing = models.ForeignKey(Filing)

    # Raw data fields
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    bakref_tid = models.CharField(max_length=50L, blank=True)
    cmte_id = models.CharField(max_length=9L, blank=True)
    cum_ytd = models.DecimalField(max_digits=16, decimal_places=2, null=True)
    entity_cd = models.CharField(max_length=5L, blank=True)
    expn_chkno = models.CharField(max_length=20L, blank=True)
    expn_code = models.CharField(
        max_length=3L, blank=True,
        choices=EXPENDITURE_CODE_CHOICES
    )
    expn_date = models.DateField(null=True)
    expn_dscr = models.CharField(max_length=400L, blank=True)
    form_type = models.CharField(max_length=6L, blank=True)
    # back reference from Form 460 Schedule G to Schedule E or F
    g_from_e_f = models.CharField(max_length=1L, blank=True)
    line_item = models.IntegerField()
    memo_code = models.CharField(max_length=1L, blank=True)
    memo_refno = models.CharField(max_length=20L, blank=True)
    payee_adr1 = models.CharField(max_length=55L, blank=True)
    payee_adr2 = models.CharField(max_length=55L, blank=True)
    payee_city = models.CharField(max_length=30L, blank=True)
    payee_namf = models.CharField(max_length=255L, blank=True)
    payee_naml = models.CharField(max_length=200L, blank=True)
    payee_nams = models.CharField(max_length=10L, blank=True)
    payee_namt = models.CharField(max_length=10L, blank=True)
    payee_st = models.CharField(max_length=2L, blank=True)
    payee_zip4 = models.CharField(max_length=10L, blank=True)
    tran_id = models.CharField(max_length=20L, blank=True)
    # a related item on other schedule has the same transaction identifier.
    # "X" indicates this condition is true
    xref_match = models.CharField(max_length=1L, blank=True)
    # Related record is included on Form 460 Schedules B2 or F
    xref_schnm = models.CharField(max_length=2L, blank=True)

    # Derived fields
    name = models.CharField(max_length=255)
    raw_org_name = models.CharField(max_length=255)
    person_flag = models.BooleanField(default=False)
    org_id = models.IntegerField(null=True)
    individual_id = models.IntegerField(null=True)

    dupe = models.BooleanField(default=False)

    @property
    def raw(self):
        from calaccess_raw.models import ExpnCd
        return ExpnCd.objects.get(
            amend_id=self.amend_id,
            filing_id=self.filing_id,
            tran_id=self.tran_id,
            bakref_tid=self.bakref_tid
        )

    def get_absolute_url(self):
        return reverse('expenditure_detail', args=[str(self.pk)])


class Contribution(BaseModel):
    """
    Who gave and how much.
    """
    cycle = models.ForeignKey(Cycle)
    committee = models.ForeignKey(Committee, related_name="contributions_to")
    filing = models.ForeignKey(Filing)

    # CAL-ACCESS ids
    filing_id_raw = models.IntegerField(db_index=True)
    transaction_id = models.CharField(
        'transaction ID',
        max_length=20,
        db_index=True
    )
    amend_id = models.IntegerField('amendment', db_index=True)
    backreference_transaction_id = models.CharField(
        'backreference transaction ID',
        max_length=20,
        db_index=True
    )
    is_crossreference = models.CharField(max_length=1, blank=True)
    crossreference_schedule = models.CharField(max_length=2, blank=True)

    # Basics about the contrib
    is_duplicate = models.BooleanField(default=False)
    transaction_type = models.CharField(max_length=1, blank=True)
    date_received = models.DateField(null=True)
    contribution_description = models.CharField(max_length=90, blank=True)
    amount = models.DecimalField(decimal_places=2, max_digits=14)

    # About the contributor
    contributor_full_name = models.CharField(max_length=255)
    contributor_is_person = models.BooleanField(default=False)
    contributor_committee = models.ForeignKey(
        Committee,
        null=True,
        related_name="contributions_from"
    )
    contributor_prefix = models.CharField(max_length=10, blank=True)
    contributor_first_name = models.CharField(max_length=255, blank=True)
    contributor_last_name = models.CharField(max_length=200, blank=True)
    contributor_suffix = models.CharField(max_length=10, blank=True)
    contributor_address_1 = models.CharField(max_length=55, blank=True)
    contributor_address_2 = models.CharField(max_length=55, blank=True)
    contributor_city = models.CharField(max_length=30, blank=True)
    contributor_state = models.CharField(max_length=2, blank=True)
    contributor_zipcode = models.CharField(max_length=10, blank=True)
    contributor_occupation = models.CharField(max_length=60, blank=True)
    contributor_employer = models.CharField(max_length=200, blank=True)
    contributor_selfemployed = models.CharField(max_length=1, blank=True)
    ENTITY_CODE_CHOICES = (
        ("", "None"),
        ("0", "0"),
        ("BNM", "BNM"),
        ("COM", "Recipient committee"),
        ("IND", "Individual"),
        ("OFF", "OFF"),
        ("OTH", "Other"),
        ("PTY", "Political party"),
        ("RCP", "RCP"),
        ("SCC", "Small contributor committee"),
    )
    contributor_entity_type = models.CharField(
        max_length=3,
        blank=True,
        help_text="The type of entity that made that contribution",
        choices=ENTITY_CODE_CHOICES
    )

    # About the intermediary
    intermediary_prefix = models.CharField(max_length=10, blank=True)
    intermediary_first_name = models.CharField(max_length=255, blank=True)
    intermediary_last_name = models.CharField(max_length=200, blank=True)
    intermediary_suffix = models.CharField(max_length=10, blank=True)
    intermediary_address_1 = models.CharField(max_length=55, blank=True)
    intermediary_address_2 = models.CharField(max_length=55, blank=True)
    intermediary_city = models.CharField(max_length=30, blank=True)
    intermediary_state = models.CharField(max_length=2, blank=True)
    intermediary_zipcode = models.CharField(max_length=10, blank=True)
    intermediary_occupation = models.CharField(max_length=60, blank=True)
    intermediary_employer = models.CharField(max_length=200, blank=True)
    intermediary_selfemployed = models.CharField(max_length=1, blank=True)
    intermediary_committee_id = models.CharField(max_length=9, blank=True)

    @property
    def raw(self):
        from calaccess_raw.models import RcptCd
        return RcptCd.objects.get(
            amend_id=self.amend_id,
            filing_id=self.filing.filing_id_raw,
            tran_id=self.transaction_id,
            bakref_tid=self.backreference_transaction_id
        )

    @property
    def contributor_dict(self):
        d = SortedDict({})
        for k, v in self.to_dict().items():
            if k.startswith("contributor"):
                d[k.replace("contributor ", "")] = v
        return d

    @property
    def intermediary_dict(self):
        d = SortedDict({})
        for k, v in self.to_dict().items():
            if k.startswith("intermediary"):
                d[k.replace("intermediary ", "")] = v
        return d

    def get_absolute_url(self):
        return reverse('contribution_detail', args=[str(self.pk)])


class Stats(models.Model):
    '''
        Flexible model for housing aggregate stats
        Should be able to add any stat you like for
        a filer_type in the options list
        And record any notes about how it was calculated and why
        Should allow for speedier display of aggregate data
        If it end up not working, we can blow it up and try something else
    '''
    FILER_TYPE_CHOICES = (
        ('cand', 'Candidate'),
        ('pac', 'Political Action Committee'),
    )
    STAT_TYPE_CHOICES = (
        ('itemized_monetary_contributions', 'Itemized Monetary Contributions'),
        (
            'unitemized_monetary_contributions',
            'Unitemized Monetary Contributions'
        ),
        ('total_contributions', 'Total Contributions'),
        ('total_expenditures', 'Total Expenditures'),
        ('outstanding_debts', 'Outstanding Debt'),

    )
    filer_type = models.CharField(max_length=10, choices=FILER_TYPE_CHOICES)
    filer = models.ForeignKey(Filer)
    stat_type = models.CharField(max_length=50, choices=STAT_TYPE_CHOICES)
    notes = models.TextField(null=True, blank=True)
    int_year_span = models.IntegerField()  # years in operation eg. 10
    # string description eg. 2000 - 2010
    str_year_span = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=16, decimal_places=2)

    def __unicode__(self):
        return '%s-%s' % (self.filer_type, self.stat_type)


class FlatFile(models.Model):
    file_name = models.CharField(max_length=255)
    s3_file = models.FileField(upload_to='files')
    description = models.TextField()
    created_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)

    def _get_file_size(self):
        return size(self.s3_file.size)
    size = property(_get_file_size)

    def __unicode__(self):
        return self.file_name
