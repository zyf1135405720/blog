from django.urls import path
from . import views

# app的名字
app_name = 'doc'

urlpatterns = [
    path('',views.doc_index,name='index'),
    path('<int:doc_id>/',views.DocDownload.as_view(),name='doc_download'),

]














