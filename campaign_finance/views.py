# Create your views here.
import csv
import json
from django.views import generic
from django.db.models import Sum, Count
from django.core.urlresolvers import reverse
from django.http import Http404, HttpResponse
from campaign_finance.models import Filer, Committee, Filing, Expenditure, Contribution
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from django.utils.encoding import smart_text


class IndexView(generic.ListView):
    model = Filer
    template = 'templates/home/index.html'
    context_object_name = 'filers'


class FilerListView(generic.ListView):
    model = Filer
    template = 'templates/filer/list.html'
    context_object_name = 'filers'
    allow_empty = False
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super(FilerListView, self).get_context_data(**kwargs)
        context['base_url'] = '/explore/'
        return context


class FilerDetailView(generic.DetailView):
    model = Filer
    template = 'templates/filer/detail.html'


class CommitteeDetailView(generic.DetailView):
    model = Committee


class CommitteeContributionView(generic.ListView):
    model = Committee
    context_object_name = 'committee_contributions'
    allow_empty = False
    paginate_by = 25

    def get_queryset(self):
        """
        Returns the contributions related to this committee.
        """
        committee = Committee.objects.get(pk=self.kwargs['pk'])
        self.committee = committee
        return committee.contribution_set.all()

    def get_context_data(self, **kwargs):
        context = super(CommitteeContributionView, self).get_context_data(**kwargs)
        context['committee'] = self.committee
        context['base_url'] = "/committee/%s/contributions/" % self.committee.pk

        return context


    def render_to_response(self, context, **kwargs):
        """
        Return a normal response, or CSV or JSON depending
        on a URL param from the user.
        """
        # See if the user has requested a special format
        format = self.request.GET.get('format', '')
        # For either CSV or JSON we'll need to format the data specially
        if 'csv' in format or 'json' in format:
            field_names = Contribution._meta.get_all_field_names()
            values = context['committee'].contribution_set.values_list(*field_names)
            data_list = []
            for i in values:
                d = {field_names[index]:val for index, val in enumerate(i)}
                data_list.append(d)

        # If it's a CSV
        if 'csv' in format:
            response = HttpResponse(mimetype='text/csv')
            response['Content-Disposition'] = 'attachment; filename=contributions.csv'
            writer = csv.DictWriter(response, fieldnames=field_names)
            writer.writeheader()
            [writer.writerow(i) for i in data_list]
            return response

        # If it's JSON
        if 'json' in format:
            return HttpResponse(json.dumps(data_list, default=smart_text), content_type="application/json")

        # And if it's none of the above return something normal
        return super(CommitteeContributionView, self).render_to_response(context, **kwargs)


class CommitteeExpenditureView(generic.ListView):
    model = Expenditure
    context_object_name = 'committee_expenditures'
    allow_empty = False
    paginate_by = 25

    def get_queryset(self):
        """
        Returns the expends related to this committee.
        """
        committee = Committee.objects.get(pk=self.kwargs['pk'])
        self.committee = committee
        return committee.expenditure_set.all()

    def get_context_data(self, **kwargs):
        context = super(CommitteeExpenditureView, self).get_context_data(**kwargs)
        context['committee'] = self.committee
        context['base_url'] = "/committee/%s/expenditures/" % self.committee.pk
        return context


class FilingDetailView(generic.DetailView):
    model = Filing
    template = 'templates/filing/detail.html'
