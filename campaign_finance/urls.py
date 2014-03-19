from django.conf.urls import patterns, include, url
from campaign_finance import views


urlpatterns = patterns('campaign_finance.views',

    # Campaign Finance URLs
    url(r'^$', views.FilerListView.as_view(template_name='filer/list.html'), name='filer_list'),
    url(r'^filer/(?P<pk>\d+)/$', views.FilerDetailView.as_view(template_name='filer/detail.html'), name='filer_detail'),
    url(r'^committee/(?P<pk>\d+)/$', views.CommitteeDetailView.as_view(template_name='committee/detail.html'), name='committee_detail'),
    url(r'^filing/(?P<pk>\d+)/$', views.FilingDetailView.as_view(template_name='filing/detail.html'), name='filing_detail'),
)
