from django.urls import path
from . import views

# app的名字
app_name = 'users'

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),   # 将这条路由命名为index
    path('login/',views.LoginView.as_view(),name='login'),
    path('logout/',views.LogoutView.as_view(),name='logout'),
    path('retrieve/',views.RetrieveView.as_view(),name='retrieve'),


]














