from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_page, never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.vary import vary_on_cookie
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import Sum
from django.conf import settings
from django.utils.text import slugify
from django.contrib.auth import get_user_model, login
from django.db import OperationalError, ProgrammingError
import logging
import os
import json

from .models import Episode, LiveStream, Category, Subscription, ContactMessage, Comment, Event, Like
from .auth import owner_required, subscriber_required


User = get_user_model()
logger = logging.getLogger(__name__)

from django.http import Http404, HttpResponse
import mimetypes
from urllib.parse import urlparse


# ── Durées de cache ─────────────────────────────────────────────────────────────
CACHE_HOME    = 60 * 5    # 5 min  — page d'accueil
CACHE_LIST    = 60 * 10   # 10 min — listes podcasts/vidéos
CACHE_DETAIL  = 60 * 15   # 15 min — détail épisode
CACHE_EVENTS  = 60 * 5    # 5 min  — événements
CACHE_LIVE    = 60 * 1    # 1 min  — live streams (données fraîches)


@cache_page(CACHE_HOME)
def home(request):
    try:
        published = Episode.objects.filter(is_published=True).select_related('category')
        latest_episodes = list(published.filter(episode_type='podcast')[:6])
        latest_videos   = list(published.filter(episode_type='video')[:4])
        live_streams    = list(LiveStream.objects.filter(status='live')[:4])
        featured        = published.first()
        categories      = list(Category.objects.all())
        category_ids_by_slug = {slugify(cat.name): str(cat.id) for cat in categories}
    except (OperationalError, ProgrammingError) as e:
        logger.error('home: DB error: %s', e)
        latest_episodes = []
        latest_videos   = []
        live_streams    = []
        featured        = None
        categories      = []
        category_ids_by_slug = {}

    context = {
        'latest_episodes':     latest_episodes,
        'latest_videos':       latest_videos,
        'live_streams':        live_streams,
        'featured':            featured,
        'categories':          categories,
        'category_ids_by_slug': category_ids_by_slug,
        'wave_number':   settings.DONATION_WAVE_NUMBER,
        'wave_name':     settings.DONATION_WAVE_NAME,
        'orange_number': settings.DONATION_ORANGE_NUMBER,
        'orange_name':   settings.DONATION_ORANGE_NAME,
    }
    return render(request, 'Accueil.html', context)


def _filter_by_category(episodes, selected_cat):
    """Filtre un queryset d'épisodes par catégorie (ID ou slug)."""
    if not selected_cat:
        return episodes
    if str(selected_cat).isdigit():
        return episodes.filter(category__id=selected_cat)
    slug = slugify(str(selected_cat).replace('_', '-'))
    cat_ids = list(
        Category.objects.filter(name__icontains=slug.replace('-', ' ')).values_list('id', flat=True)
    )
    return episodes.filter(category_id__in=cat_ids) if cat_ids else episodes.none()


@cache_page(CACHE_LIST)
def podcasts(request):
    episodes     = Episode.objects.filter(is_published=True, episode_type='podcast').select_related('category')
    categories   = Category.objects.filter(for_type__in=['podcast', 'all'])
    selected_cat = request.GET.get('categorie')
    context = {
        'episodes':     _filter_by_category(episodes, selected_cat),
        'categories':   categories,
        'selected_cat': selected_cat,
    }
    return render(request, 'podcasts.html', context)


@cache_page(CACHE_LIST)
def videos(request):
    episodes     = Episode.objects.filter(is_published=True, episode_type='video').select_related('category')
    categories   = Category.objects.filter(for_type__in=['video', 'all'])
    selected_cat = request.GET.get('categorie')
    context = {
        'episodes':     _filter_by_category(episodes, selected_cat),
        'categories':   categories,
        'selected_cat': selected_cat,
    }
    return render(request, 'videos.html', context)


@cache_page(CACHE_DETAIL)
def podcast_detail(request, pk):
    episode  = get_object_or_404(
        Episode.objects.select_related('category'),
        pk=pk, is_published=True, episode_type='podcast',
    )
    similar  = (
        Episode.objects
        .filter(is_published=True, episode_type='podcast', category=episode.category)
        .exclude(pk=pk)
        .select_related('category')[:3]
    )
    comments      = episode.comments.filter(is_approved=True)
    comment_list  = list(comments)
    context = {
        'episode':          episode,
        'similar_episodes': similar,
        'youtube_embed_url': episode.get_youtube_embed_url(),
        'comments':         comment_list,
        'comment_count':    len(comment_list),
    }
    return render(request, 'podcast_detail.html', context)


@cache_page(CACHE_DETAIL)
def video_detail(request, pk):
    episode  = get_object_or_404(
        Episode.objects.select_related('category'),
        pk=pk, is_published=True, episode_type='video',
    )
    similar  = (
        Episode.objects
        .filter(is_published=True, episode_type='video', category=episode.category)
        .exclude(pk=pk)
        .select_related('category')[:3]
    )
    comments     = episode.comments.filter(is_approved=True)
    comment_list = list(comments)

    file_exists = False
    if episode.video_file:
        try:
            file_exists = os.path.exists(episode.video_file.path)
        except Exception:
            pass
    has_downloadable = file_exists or bool((episode.video_url or '').strip())

    context = {
        'episode':           episode,
        'similar_episodes':  similar,
        'youtube_embed_url': episode.get_youtube_embed_url(),
        'youtube_watch_url': episode.get_youtube_watch_url(),
        'youtube_video_id':  episode.get_youtube_video_id(),
        'comments':          comment_list,
        'comment_count':     len(comment_list),
        'has_downloadable':  has_downloadable,
    }
    return render(request, 'video_detail.html', context)


@cache_page(CACHE_LIVE)
def live(request):
    streams   = LiveStream.objects.filter(status='live')
    scheduled = LiveStream.objects.filter(status='scheduled')
    context   = {'streams': streams, 'scheduled': scheduled}
    return render(request, 'live.html', context)


@never_cache
@owner_required
def dashboard(request):
    episodes         = Episode.objects.all()[:10]
    total_episodes   = Episode.objects.count()
    # aggregate évite de charger tous les épisodes en mémoire
    total_views      = Episode.objects.aggregate(total=Sum('views_count'))['total'] or 0
    total_subscribers = Subscription.objects.filter(is_active=True).count()
    recent_subscribers = Subscription.objects.filter(is_active=True).order_by('-created_at')[:5]

    context = {
        'episodes':           episodes,
        'total_episodes':     total_episodes,
        'total_views':        total_views,
        'total_subscribers':  total_subscribers,
        'recent_subscribers': recent_subscribers,
    }
    return render(request, 'dashboard.html', context)


@never_cache
@owner_required
def publish_episode(request):
    if request.method == 'POST':
        try:
            title        = (request.POST.get('title') or '').strip()
            description  = (request.POST.get('description') or '').strip()
            episode_type = request.POST.get('episode_type', 'podcast')
            if episode_type not in ('podcast', 'video'):
                episode_type = 'podcast'
            category_id = request.POST.get('category')
            audio_url   = (request.POST.get('audio_url') or '').strip()
            video_url   = (request.POST.get('video_url') or '').strip()
            duration    = (request.POST.get('duration') or '').strip()
            cover_color = request.POST.get('cover_color', '#00261b') or '#00261b'

            if not title or not description:
                raise ValueError('Le titre et la description sont obligatoires.')
            if episode_type == 'podcast' and not audio_url:
                raise ValueError('Pour un podcast, renseignez une URL audio (fichier MP3 ou hébergeur).')
            if episode_type == 'video' and not video_url:
                raise ValueError('Pour une vidéo, renseignez une URL (YouTube, lien direct, etc.).')

            category = Category.objects.get(id=category_id) if category_id else None

            episode = Episode(
                title=title,
                description=description,
                episode_type=episode_type,
                category=category,
                audio_url=audio_url,
                video_url=video_url,
                duration=duration,
                cover_color=cover_color,
                is_published=True,
            )
            episode.save()

            # Invalider les caches de liste après publication
            cache.delete_pattern('safeplace:*home*')
            cache.delete_pattern('safeplace:*podcasts*')
            cache.delete_pattern('safeplace:*videos*')

            if episode.episode_type == 'video':
                return redirect('video_detail', pk=episode.id)
            return redirect('podcast_detail', pk=episode.id)

        except Exception as e:
            context = {'error': str(e), 'categories': Category.objects.all()}
            return render(request, 'publish_episode.html', context)

    categories = Category.objects.all()
    context    = {'categories': categories}
    return render(request, 'publish_episode.html', context)


def _parse_post_or_json(request):
    ct = (request.META.get('CONTENT_TYPE') or '').lower()
    if 'application/json' in ct and request.body:
        try:
            return json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
    return request.POST


@never_cache
@owner_required
def manage_live_streams(request):
    if request.method == 'POST':
        try:
            data        = _parse_post_or_json(request)
            title       = (data.get('title') or '').strip()
            description = (data.get('description') or '').strip()
            platform    = (data.get('platform') or '').strip()
            stream_url  = (data.get('stream_url') or '').strip()
            embed_url   = (data.get('embed_url') or '').strip()
            status      = (data.get('status') or 'scheduled').strip()

            if not title:
                return JsonResponse({'success': False, 'error': 'Le titre est obligatoire.'})
            if not platform:
                return JsonResponse({'success': False, 'error': 'Choisissez une plateforme.'})

            live_stream = LiveStream(
                title=title, description=description, platform=platform,
                stream_url=stream_url, embed_url=embed_url, status=status,
            )
            live_stream.save()
            return JsonResponse({'success': True, 'message': 'Live Stream créé avec succès'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    live_streams = LiveStream.objects.all()
    context = {
        'live_streams': live_streams,
        'platforms':    LiveStream._meta.get_field('platform').choices,
        'statuses':     LiveStream._meta.get_field('status').choices,
    }
    return render(request, 'manage_live_streams.html', context)


def _parse_bool(value):
    return str(value).lower() in ('true', '1', 'yes', 'on', 'checked')


def register(request):
    return redirect('home')


def about(request):
    return render(request, 'about.html')


def dons(request):
    wave_num    = settings.DONATION_WAVE_NUMBER or 'voir ci-dessus'
    orange_num  = settings.DONATION_ORANGE_NUMBER or 'voir ci-dessus'
    don_msg     = settings.DONATION_MESSAGE or 'Don SafePlace'
    context = {
        'wave_number':   settings.DONATION_WAVE_NUMBER,
        'wave_name':     settings.DONATION_WAVE_NAME,
        'orange_number': settings.DONATION_ORANGE_NUMBER,
        'orange_name':   settings.DONATION_ORANGE_NAME,
        'don_message':   don_msg,
        'wave_steps': [
            "Ouvrez l'application Wave sur votre téléphone.",
            "Appuyez sur « Envoyer de l'argent ».",
            f"Saisissez le numéro : {wave_num}.",
            "Entrez le montant de votre choix.",
            f"Dans le motif, écrivez « {don_msg} ».",
            "Confirmez l'envoi avec votre code PIN.",
        ],
        'orange_steps': [
            "Composez le *144# ou ouvrez l'app Orange Money.",
            "Choisissez « Transfert d'argent ».",
            f"Entrez le numéro : {orange_num}.",
            "Saisissez le montant de votre choix.",
            f"Dans le motif, écrivez « {don_msg} ».",
            "Validez avec votre code secret.",
        ],
    }
    return render(request, 'dons.html', context)


def _sanitize_header(value: str, max_len: int = 200) -> str:
    import re
    return re.sub(r'[\r\n\t]', ' ', str(value or '')).strip()[:max_len]


@never_cache
def contact(request):
    success = False
    error   = None

    if request.method == 'POST':
        try:
            first_name   = _sanitize_header(request.POST.get('first_name', ''))
            last_name    = _sanitize_header(request.POST.get('last_name', ''))
            email        = _sanitize_header(request.POST.get('email', ''))
            subject      = _sanitize_header(request.POST.get('subject', 'Question générale'))
            message_text = request.POST.get('message', '')[:5000]

            if not email or not message_text:
                error = "Veuillez remplir tous les champs obligatoires"
            else:
                full_name = f"{first_name} {last_name}".strip()

                ContactMessage.objects.create(
                    name=full_name, email=email,
                    subject=subject, message=message_text,
                )

                try:
                    send_mail(
                        f'Nouveau message de contact: {subject}',
                        f'De: {full_name} ({email})\n\n{message_text}',
                        settings.DEFAULT_FROM_EMAIL,
                        [settings.ADMINS[0][1]] if settings.ADMINS else ['admin@safeplace.com'],
                        fail_silently=True,
                    )
                except Exception as e:
                    logger.warning("Erreur envoi email: %s", str(e))

                try:
                    send_mail(
                        'Votre message a été reçu',
                        f'Bonjour {first_name},\n\nMerci de nous avoir contacté. Nous vous répondrons dans les plus brefs délais.\n\nThe SafePlace by K',
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        fail_silently=True,
                    )
                except Exception as e:
                    logger.warning("Erreur envoi email confirmation: %s", str(e))

                success = True
        except Exception as e:
            error = f"Erreur lors de l'envoi du message: {str(e)}"

    context = {'success': success, 'error': error}
    return render(request, 'contact.html', context)


def access_denied(request):
    return render(request, 'access_denied.html', status=403)


def download_episode(request, pk):
    from django.http import FileResponse
    episode = get_object_or_404(Episode, pk=pk, is_published=True)

    # 1. Fichier audio local (importé depuis la galerie)
    if episode.episode_type == 'podcast' and episode.audio_file:
        try:
            f        = episode.audio_file.open('rb')
            filename = os.path.basename(episode.audio_file.name)
            safe     = ''.join(c for c in episode.title if c.isalnum() or c in ' -_')
            ext      = os.path.splitext(filename)[1] or '.mp3'
            return FileResponse(f, as_attachment=True, filename=f"{safe}{ext}")
        except (FileNotFoundError, OSError):
            pass  # fallback vers audio_url

    # 2. Fichier vidéo local
    if episode.episode_type == 'video' and episode.video_file:
        try:
            f        = episode.video_file.open('rb')
            filename = os.path.basename(episode.video_file.name)
            return FileResponse(f, as_attachment=True, filename=filename)
        except (FileNotFoundError, OSError):
            pass

    # 3. URL externe (redirect avec Content-Disposition)
    if episode.episode_type == 'podcast':
        source_url = (episode.audio_url or '').strip()
    else:
        source_url = (episode.video_url or '').strip()

    if not source_url:
        detail_url = 'video_detail' if episode.episode_type == 'video' else 'podcast_detail'
        return redirect(detail_url, pk=episode.pk)

    parsed   = urlparse(source_url)
    filename = parsed.path.split('/')[-1] or ''
    if not filename:
        safe     = ''.join(c for c in episode.title if c.isalnum() or c in ' -_')
        filename = f"{safe}.mp3" if episode.episode_type == 'podcast' else f"{safe}.mp4"

    content_type, _ = mimetypes.guess_type(filename)
    resp = HttpResponse(status=302)
    if content_type:
        resp['Content-Type'] = content_type
    resp['Content-Disposition'] = f'attachment; filename="{filename}"'
    resp['Location'] = source_url
    return resp


def loading(request):
    return render(request, 'loading.html')


_ALLOWED_AUDIO_TYPES = {
    'audio/mpeg', 'audio/mp3', 'audio/mp4', 'audio/x-m4a',
    'audio/wav', 'audio/x-wav', 'audio/ogg', 'audio/aac',
    'audio/flac', 'audio/x-flac',
}
_ALLOWED_AUDIO_EXT = {'.mp3', '.m4a', '.wav', '.ogg', '.aac', '.flac'}


@never_cache
@owner_required
def import_podcast(request):
    """Importer un fichier audio depuis la galerie pour créer un épisode podcast."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    audio_file = request.FILES.get('audio_file')
    title       = (request.POST.get('title') or '').strip()
    description = (request.POST.get('description') or '').strip()
    category_id = request.POST.get('category')
    host        = (request.POST.get('host') or 'The SafePlace by K').strip()
    duration    = (request.POST.get('duration') or '').strip()

    if not audio_file:
        return JsonResponse({'error': 'Aucun fichier sélectionné.'}, status=400)
    if not title:
        return JsonResponse({'error': 'Le titre est obligatoire.'}, status=400)

    import os
    ext = os.path.splitext(audio_file.name)[1].lower()
    content_type = (audio_file.content_type or '').split(';')[0].strip().lower()
    if content_type not in _ALLOWED_AUDIO_TYPES and ext not in _ALLOWED_AUDIO_EXT:
        return JsonResponse({'error': 'Format non supporté. Utilisez MP3, M4A, WAV, OGG ou AAC.'}, status=400)

    # Pas de limite de taille — les gros fichiers sont gérés par Django via fichiers temporaires

    category = None
    if category_id:
        try:
            category = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            pass

    try:
        episode = Episode(
            title=title,
            description=description or title,
            episode_type='podcast',
            category=category,
            host=host,
            duration=duration,
            cover_color='#00261b',
            is_published=True,
        )
        episode.audio_file.save(audio_file.name, audio_file, save=False)
        episode.audio_url = episode.audio_file.url
        episode.save()

        return JsonResponse({
            'success': True,
            'episode': {
                'id':          episode.id,
                'title':       episode.title,
                'description': episode.description,
                'host':        episode.host,
                'duration':    episode.duration,
                'category':    episode.category.name if episode.category else 'Général',
                'cover_color': episode.cover_color,
                'audio_url':   episode.audio_url,
                'detail_url':  f'/podcasts/{episode.id}/',
                'created_at':  episode.created_at.strftime('%d %b %Y'),
            }
        }, status=201)

    except Exception as e:
        logger.error('import_podcast error: %s', e)
        return JsonResponse({'error': f'Erreur lors de l\'enregistrement : {e}'}, status=500)


@csrf_exempt
@never_cache
@require_http_methods(['POST'])
def toggle_like(request, pk):
    episode = get_object_or_404(Episode, pk=pk, is_published=True)

    if not request.session.session_key:
        request.session.create()

    identifier = f"u_{request.user.pk}" if request.user.is_authenticated else request.session.session_key

    from django.db.models import F
    like = Like.objects.filter(episode=episode, identifier=identifier).first()
    if like:
        like.delete()
        Episode.objects.filter(pk=pk).update(likes_count=F('likes_count') - 1)
        liked = False
    else:
        Like.objects.create(episode=episode, identifier=identifier)
        Episode.objects.filter(pk=pk).update(likes_count=F('likes_count') + 1)
        liked = True

    episode.refresh_from_db(fields=['likes_count'])
    return JsonResponse({'liked': liked, 'count': max(episode.likes_count, 0)})


@never_cache
@owner_required
def studio_live(request):
    from .models import MultiStreamConfig
    cfg, _ = MultiStreamConfig.objects.get_or_create(pk=1, defaults={'title': 'Studio SafePlace'})
    return render(request, 'studio.html', {'stream_config': cfg})


@never_cache
@owner_required
def messages_inbox(request):
    """Boîte de réception des messages de contact."""
    filter_type = request.GET.get('f', 'all')
    qs = ContactMessage.objects.all()
    if filter_type == 'unread':
        qs = qs.filter(is_read=False)
    elif filter_type == 'read':
        qs = qs.filter(is_read=True)

    total  = ContactMessage.objects.count()
    unread = ContactMessage.objects.filter(is_read=False).count()
    read   = total - unread

    return render(request, 'messages_inbox.html', {
        'messages':      qs,
        'active_filter': filter_type,
        'total':         total,
        'unread':        unread,
        'read':          read,
    })


@never_cache
@owner_required
@require_http_methods(['POST'])
def message_toggle_read(request, pk):
    """Basculer lu/non lu."""
    msg = get_object_or_404(ContactMessage, pk=pk)
    msg.is_read = not msg.is_read
    msg.save()
    return JsonResponse({'success': True, 'is_read': msg.is_read})


@never_cache
@owner_required
@require_http_methods(['POST'])
def message_delete_view(request, pk):
    """Supprimer un message."""
    msg = get_object_or_404(ContactMessage, pk=pk)
    msg.delete()
    return JsonResponse({'success': True})


@never_cache
@owner_required
@require_http_methods(['POST'])
def messages_mark_all_read(request):
    """Marquer tous les messages comme lus."""
    ContactMessage.objects.filter(is_read=False).update(is_read=True)
    return JsonResponse({'success': True})


@never_cache
@require_http_methods(['POST'])
def add_comment(request, pk):
    episode = get_object_or_404(Episode, pk=pk, is_published=True)

    author_name  = (request.POST.get('author_name') or '').strip()
    author_email = (request.POST.get('author_email') or '').strip()
    content      = (request.POST.get('content') or '').strip()

    if not author_name or not content:
        return JsonResponse({'success': False, 'error': 'Le nom et le commentaire sont obligatoires.'}, status=400)

    if len(content) > 2000:
        return JsonResponse({'success': False, 'error': 'Le commentaire ne peut pas dépasser 2000 caractères.'}, status=400)

    comment = Comment.objects.create(
        episode=episode,
        author_name=author_name,
        author_email=author_email,
        content=content,
    )

    return JsonResponse({
        'success': True,
        'comment': {
            'id':          comment.id,
            'author_name': comment.author_name,
            'content':     comment.content,
            'created_at':  comment.created_at.strftime('%d %B %Y'),
        }
    }, status=201)


@cache_page(CACHE_EVENTS)
def evenements(request):
    from django.utils import timezone
    filter_type  = request.GET.get('type', '').strip()
    valid_types  = [t[0] for t in Event.TYPE_CHOICES]
    if filter_type not in valid_types:
        filter_type = ''

    try:
        now = timezone.now()
        qs  = Event.objects.filter(is_published=True)
        if filter_type:
            qs = qs.filter(event_type=filter_type)

        upcoming_events = list(qs.filter(event_date__gte=now).order_by('event_date'))
        past_events     = list(qs.filter(event_date__lt=now).order_by('-event_date')[:12])

        all_qs          = Event.objects.filter(is_published=True)
        upcoming_count  = all_qs.filter(event_date__gte=now).count()
        total_count     = all_qs.count()

        featured = all_qs.filter(is_featured=True, event_date__gte=now).first()
        if not featured and upcoming_events:
            featured = upcoming_events[0]

    except (OperationalError, ProgrammingError) as e:
        logger.error('evenements: DB error: %s', e)
        upcoming_events = []
        past_events     = []
        featured        = None
        upcoming_count  = 0
        total_count     = 0

    context = {
        'upcoming_events': upcoming_events,
        'past_events':     past_events,
        'featured':        featured,
        'upcoming_count':  upcoming_count,
        'total_count':     total_count,
        'filter_type':     filter_type,
    }
    return render(request, 'evenements.html', context)
