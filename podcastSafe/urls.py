from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('podcasts/', views.podcasts, name='podcasts'),
    path('videos/', views.videos, name='videos'),
    path('videos/<int:pk>/', views.video_detail, name='video_detail'),
    path('podcasts/<int:pk>/', views.podcast_detail, name='podcast_detail'),
    path('episodes/<int:pk>/download/', views.download_episode, name='episode_download'),
    path('episodes/<int:pk>/comment/', views.add_comment, name='episode_comment'),
    path('podcasts/import/', views.import_podcast, name='import_podcast'),
    path('episodes/<int:pk>/like/', views.toggle_like, name='episode_like'),
    path('live/', views.live, name='live'),
    path('publish/', views.publish_episode, name='publish_episode'),
    path('manage-live-streams/', views.manage_live_streams, name='manage_live_streams'),

    # Public registration disabled
    path('apropos/', views.about, name='about'),
    path('dons/', views.dons, name='dons'),
    path('contact/', views.contact, name='contact'),
    path('access-denied/', views.access_denied, name='access_denied'),
    path('loading/', views.loading, name='loading'),
    path('studio/', views.studio_live, name='studio_live'),
    path('evenements/', views.evenements, name='evenements'),
    path('messages/', views.messages_inbox, name='messages_inbox'),
    path('messages/<int:pk>/toggle-read/', views.message_toggle_read, name='message_toggle_read'),
    path('messages/<int:pk>/delete/', views.message_delete_view, name='message_delete_view'),
    path('messages/mark-all-read/', views.messages_mark_all_read, name='messages_mark_all_read'),
]



