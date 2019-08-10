from django.urls import path
from . import views

# app的名字
app_name = 'course'

urlpatterns = [
    path('',views.course_list,name='course_list'),
    path('<int:course_id>/',views.CourseDetailView.as_view(),name='course_detail'),

]














