/* ═══════════════════════════════════════════════
   SafePlace — Persistent Audio Player (full)
   ═══════════════════════════════════════════════ */
(function () {
  'use strict';

  var audio = document.getElementById('sp-audio');
  if (!audio) return;

  /* ── Desktop elements ── */
  var playerFooter   = document.getElementById('sp-player');
  var titleEl        = document.getElementById('player-title');
  var hostEl         = document.getElementById('player-host');
  var coverEl        = document.getElementById('player-cover');
  var playPauseBtn   = document.getElementById('play-pause-btn');
  var playIcon       = document.getElementById('play-icon');
  var progressBar    = document.getElementById('progress-bar');
  var progressFill   = document.getElementById('progress-fill');
  var currentTimeEl  = document.getElementById('current-time');
  var totalTimeEl    = document.getElementById('total-time');
  var prevBtn        = document.getElementById('prev-btn');
  var nextBtn        = document.getElementById('next-btn');
  var shuffleBtn     = document.getElementById('shuffle-btn');
  var shuffleIcon    = document.getElementById('shuffle-icon');
  var repeatBtn      = document.getElementById('repeat-btn');
  var repeatIcon     = document.getElementById('repeat-icon');
  var favoriteBtn    = document.getElementById('favorite-btn');
  var favIcon        = document.getElementById('fav-icon');
  var speedBtn       = document.getElementById('speed-btn');
  var playlistBtn    = document.getElementById('playlist-btn');
  var volumeBtn      = document.getElementById('volume-btn');
  var volumeIcon     = document.getElementById('volume-icon');
  var volumeTrack    = document.getElementById('volume-track');
  var volumeFill     = document.getElementById('volume-fill');
  var queuePanel     = document.getElementById('sp-queue-panel');
  var queueList      = document.getElementById('sp-queue-list');

  /* ── Mobile elements ── */
  var mobilePlayer        = document.getElementById('sp-mobile-player');
  var mobTitle            = document.getElementById('sp-mob-title');
  var mobPlayBtn          = document.getElementById('sp-mob-play-btn');
  var mobPlayIcon         = document.getElementById('sp-mob-play-icon');
  var mobCover            = document.getElementById('sp-mob-cover');
  var mobileProgressEl    = document.getElementById('sp-mobile-progress');
  var mobileProgressFill  = document.getElementById('sp-mobile-progress-fill');
  var mobCloseBtn         = document.getElementById('sp-mob-close-btn');

  /* ── State ── */
  var queue        = [];   // [{audioUrl, title, host, color, episodeId}]
  var queueIndex   = -1;
  var shuffleOn    = false;
  var repeatMode   = 0;    // 0=off 1=one 2=all
  var speeds       = [1, 1.25, 1.5, 2, 0.75];
  var speedIndex   = 0;
  var currentData  = null;
  var prevVolume   = 1;

  /* ── Helpers ── */
  function fmt(s) {
    if (!isFinite(s)) return '0:00';
    var m = Math.floor(s / 60), sec = Math.floor(s % 60);
    return m + ':' + (sec < 10 ? '0' : '') + sec;
  }

  function setPlayIcons(playing) {
    var icon = playing ? 'pause' : 'play_arrow';
    if (playIcon)    playIcon.textContent    = icon;
    if (mobPlayIcon) mobPlayIcon.textContent = icon;
  }

  function updateCover(color) {
    var c = color || '#00261b';
    var grad = 'linear-gradient(135deg,' + c + ',#416900)';
    var inner = '<span class="material-symbols-outlined" style="color:#fff;font-size:22px;font-variation-settings:\'FILL\' 1">headphones</span>';
    if (coverEl)  { coverEl.style.background  = grad; coverEl.innerHTML  = inner; }
    if (mobCover) { mobCover.style.background = grad; mobCover.innerHTML = '<span class="material-symbols-outlined text-white" style="font-size:17px;font-variation-settings:\'FILL\' 1">headphones</span>'; }
  }

  function showPlayers() {
    if (playerFooter) playerFooter.style.display = 'block';
    if (mobilePlayer) mobilePlayer.classList.add('sp-player-visible');
  }

  function hideMobilePlayer() {
    if (mobilePlayer) mobilePlayer.classList.remove('sp-player-visible');
  }

  /* ── Volume helpers ── */
  function syncVolumeUI(vol) {
    if (volumeFill) volumeFill.style.width = (vol * 100) + '%';
    if (volumeIcon) {
      volumeIcon.textContent = vol === 0 ? 'volume_off' : vol < 0.5 ? 'volume_down' : 'volume_up';
    }
  }

  /* ── Queue helpers ── */
  function buildQueueFromPage() {
    var btns = document.querySelectorAll('.js-play-btn[data-audio-url]');
    var arr = [];
    btns.forEach(function(b) {
      arr.push({
        audioUrl:  b.dataset.audioUrl,
        title:     b.dataset.title  || 'The SafePlace by K',
        host:      b.dataset.host   || '',
        color:     b.dataset.color  || '#00261b',
        episodeId: b.dataset.episodeId || '',
      });
    });
    return arr;
  }

  function renderQueue() {
    if (!queueList) return;
    queueList.innerHTML = '';
    if (!queue.length) {
      queueList.innerHTML = '<p style="padding:12px 16px;font-size:13px;color:rgba(0,38,27,.45)">Aucun épisode en file.</p>';
      return;
    }
    queue.forEach(function(item, i) {
      var row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:10px;padding:8px 16px;cursor:pointer;transition:background .15s;border-radius:0';
      row.style.background = i === queueIndex ? 'rgba(0,38,27,.06)' : '';
      row.innerHTML =
        '<span class="material-symbols-outlined" style="font-size:16px;color:' + (i === queueIndex ? '#416900' : 'rgba(0,38,27,.3)') + ';flex-shrink:0">' +
          (i === queueIndex ? 'graphic_eq' : 'music_note') +
        '</span>' +
        '<span style="font-size:13px;font-weight:' + (i === queueIndex ? '700' : '500') + ';color:#00261b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1">' + item.title + '</span>';
      row.addEventListener('mouseenter', function() { if (i !== queueIndex) row.style.background = 'rgba(0,38,27,.03)'; });
      row.addEventListener('mouseleave', function() { if (i !== queueIndex) row.style.background = ''; });
      row.addEventListener('click', function() { playIndex(i); });
      queueList.appendChild(row);
    });
  }

  /* ── Load & play ── */
  function loadAndPlay(data) {
    if (!data || !data.audioUrl) return;
    currentData = data;
    audio.src = data.audioUrl;
    audio.playbackRate = speeds[speedIndex];
    audio.load();
    audio.play().catch(function(){});
    if (titleEl)  titleEl.textContent  = data.title || 'The SafePlace by K';
    if (hostEl)   hostEl.textContent   = data.host  || '';
    if (mobTitle) mobTitle.textContent = data.title || 'The SafePlace by K';
    updateCover(data.color);
    showPlayers();
    setPlayIcons(true);
    updateFavUI(false);
    renderQueue();
  }

  function playIndex(i) {
    if (i < 0 || i >= queue.length) return;
    queueIndex = i;
    loadAndPlay(queue[i]);
  }

  function getNextIndex() {
    if (!queue.length) return -1;
    if (shuffleOn) {
      var candidates = queue.map(function(_, i) { return i; }).filter(function(i) { return i !== queueIndex; });
      if (!candidates.length) return queueIndex;
      return candidates[Math.floor(Math.random() * candidates.length)];
    }
    return (queueIndex + 1) < queue.length ? queueIndex + 1 : (repeatMode === 2 ? 0 : -1);
  }

  function getPrevIndex() {
    if (!queue.length) return -1;
    if (audio.currentTime > 3) return queueIndex; // rewind instead
    return (queueIndex - 1) >= 0 ? queueIndex - 1 : (repeatMode === 2 ? queue.length - 1 : -1);
  }

  /* ── sp:play event (fired by main.js) ── */
  document.addEventListener('sp:play', function(e) {
    var data = e.detail || {};
    // Rebuild queue from page each time
    queue = buildQueueFromPage();
    // Find index of this track
    var idx = queue.findIndex(function(q) { return q.audioUrl === data.audioUrl; });
    queueIndex = idx >= 0 ? idx : 0;
    if (idx < 0) { queue.unshift(data); queueIndex = 0; }
    loadAndPlay(data);
  });

  /* ── Play/Pause ── */
  if (playPauseBtn) {
    playPauseBtn.addEventListener('click', function() {
      if (audio.paused) audio.play().catch(function(){});
      else              audio.pause();
    });
  }
  if (mobPlayBtn) {
    mobPlayBtn.addEventListener('click', function() {
      if (audio.paused) audio.play().catch(function(){});
      else              audio.pause();
    });
  }

  /* ── Skip previous ── */
  if (prevBtn) {
    prevBtn.addEventListener('click', function() {
      if (audio.currentTime > 3) {
        audio.currentTime = 0; return;
      }
      var i = getPrevIndex();
      if (i >= 0) playIndex(i);
    });
  }

  /* ── Skip next ── */
  if (nextBtn) {
    nextBtn.addEventListener('click', function() {
      var i = getNextIndex();
      if (i >= 0) playIndex(i);
    });
  }

  /* ── Shuffle ── */
  if (shuffleBtn) {
    shuffleBtn.addEventListener('click', function() {
      shuffleOn = !shuffleOn;
      if (shuffleIcon) shuffleIcon.style.color = shuffleOn ? '#416900' : '';
      shuffleBtn.style.color = shuffleOn ? '#416900' : '';
    });
  }

  /* ── Repeat (0=off → 1=one → 2=all → 0) ── */
  if (repeatBtn) {
    repeatBtn.addEventListener('click', function() {
      repeatMode = (repeatMode + 1) % 3;
      if (repeatMode === 0) {
        audio.loop = false;
        if (repeatIcon) repeatIcon.textContent = 'repeat';
        repeatBtn.style.color = '';
      } else if (repeatMode === 1) {
        audio.loop = true;
        if (repeatIcon) repeatIcon.textContent = 'repeat_one';
        repeatBtn.style.color = '#416900';
      } else {
        audio.loop = false;
        if (repeatIcon) repeatIcon.textContent = 'repeat';
        repeatBtn.style.color = '#416900';
      }
    });
  }

  /* ── Speed ── */
  if (speedBtn) {
    speedBtn.addEventListener('click', function() {
      speedIndex = (speedIndex + 1) % speeds.length;
      var s = speeds[speedIndex];
      audio.playbackRate = s;
      speedBtn.textContent = s + 'x';
      speedBtn.style.color = s !== 1 ? '#416900' : '';
    });
  }

  /* ── Favorite ── */
  function updateFavUI(liked) {
    if (!favIcon) return;
    favIcon.style.fontVariationSettings = liked ? "'FILL' 1" : "'FILL' 0";
    favIcon.style.color = liked ? '#e11d48' : '';
    if (favoriteBtn) favoriteBtn.dataset.liked = liked ? '1' : '0';
  }

  if (favoriteBtn) {
    favoriteBtn.addEventListener('click', function() {
      var liked = favoriteBtn.dataset.liked === '1';
      updateFavUI(!liked);
      // Appel API like si un épisode est identifié
      var epId = currentData && currentData.episodeId;
      if (epId && window.SP_LIKE_URL) {
        var url = window.SP_LIKE_URL.replace('{id}', epId);
        fetch(url, {
          method: 'POST',
          headers: { 'X-CSRFToken': window.SP_CSRF || '', 'Content-Type': 'application/json' },
        }).catch(function(){});
      }
    });
  }

  /* ── Playlist panel ── */
  if (playlistBtn && queuePanel) {
    playlistBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      var visible = queuePanel.style.display !== 'none';
      queuePanel.style.display = visible ? 'none' : 'block';
      if (!visible) renderQueue();
    });
    document.addEventListener('click', function(e) {
      if (queuePanel && !queuePanel.contains(e.target) && e.target !== playlistBtn) {
        queuePanel.style.display = 'none';
      }
    });
  }

  /* ── Volume icon → mute toggle ── */
  if (volumeBtn) {
    volumeBtn.addEventListener('click', function() {
      if (audio.volume > 0) {
        prevVolume = audio.volume;
        audio.volume = 0;
      } else {
        audio.volume = prevVolume || 1;
      }
      syncVolumeUI(audio.volume);
    });
  }

  /* ── Volume bar ── */
  if (volumeTrack) {
    volumeTrack.addEventListener('click', function(e) {
      var rect = volumeTrack.getBoundingClientRect();
      var vol  = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      audio.volume = vol;
      syncVolumeUI(vol);
    });
  }

  /* ── Mobile close ── */
  if (mobCloseBtn) {
    mobCloseBtn.addEventListener('click', function() {
      audio.pause(); audio.src = '';
      hideMobilePlayer();
    });
  }

  /* ── Audio events → UI ── */
  audio.addEventListener('play',  function() { setPlayIcons(true);  });
  audio.addEventListener('pause', function() { setPlayIcons(false); });
  audio.addEventListener('ended', function() {
    setPlayIcons(false);
    if (repeatMode === 1) return; // loop handles it
    var i = getNextIndex();
    if (i >= 0) { playIndex(i); return; }
    setPlayIcons(false);
  });

  audio.addEventListener('timeupdate', function() {
    if (!audio.duration) return;
    var pct = (audio.currentTime / audio.duration) * 100;
    if (progressFill)       progressFill.style.width       = pct + '%';
    if (mobileProgressFill) mobileProgressFill.style.width = pct + '%';
    if (currentTimeEl)      currentTimeEl.textContent      = fmt(audio.currentTime);
  });

  audio.addEventListener('loadedmetadata', function() {
    if (totalTimeEl) totalTimeEl.textContent = fmt(audio.duration);
  });

  /* ── Progress bar seek (desktop) ── */
  if (progressBar) {
    progressBar.addEventListener('click', function(e) {
      if (!audio.duration) return;
      var rect = progressBar.getBoundingClientRect();
      audio.currentTime = ((e.clientX - rect.left) / rect.width) * audio.duration;
    });
  }

  /* ── Progress bar seek (mobile) ── */
  if (mobileProgressEl) {
    mobileProgressEl.addEventListener('click', function(e) {
      if (!audio.duration) return;
      var rect = mobileProgressEl.getBoundingClientRect();
      audio.currentTime = ((e.clientX - rect.left) / rect.width) * audio.duration;
    });
  }

  /* ── Keyboard shortcuts ── */
  document.addEventListener('keydown', function(e) {
    var tag = (e.target.tagName || '').toUpperCase();
    if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return;
    if (!currentData) return;
    if (e.code === 'Space') {
      e.preventDefault();
      if (audio.paused) audio.play().catch(function(){});
      else              audio.pause();
    } else if (e.code === 'ArrowRight') {
      e.preventDefault();
      audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 10);
    } else if (e.code === 'ArrowLeft') {
      e.preventDefault();
      audio.currentTime = Math.max(0, audio.currentTime - 10);
    } else if (e.code === 'KeyM') {
      if (audio.volume > 0) { prevVolume = audio.volume; audio.volume = 0; }
      else { audio.volume = prevVolume || 1; }
      syncVolumeUI(audio.volume);
    }
  });

  /* ── Init volume UI ── */
  syncVolumeUI(audio.volume || 1);

})();
