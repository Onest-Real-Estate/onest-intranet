from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login", views.login_page, name="login"),
    path("dashboard", views.dashboard, name="dashboard"),
    path("logout", views.logout, name="logout"),
]
