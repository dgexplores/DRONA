// SRMS DRONA - Main Application JS
(function () {
  'use strict';

  // PWA Service Worker Registration
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/static/sw.js')
        .then(function (reg) {
          console.log('[SW] Registered: ', reg.scope);
        })
        .catch(function (err) {
          console.warn('[SW] Registration failed: ', err);
        });
    });
  }

  // ===== Lesson progress =====
  // One reporter, two sources: a native <video> element, or a YouTube IFrame
  // player. Previously this only ran for <video>, so a YouTube lesson could be
  // watched but never accumulated the watch time needed to complete.
  function makeReporter(lessonId, initialPosition) {
    var saveUrl = '/lessons/' + lessonId + '/progress/';
    var lastSaved = parseInt(initialPosition || '0', 10) || 0;
    var watchedSinceSave = 0;

    function save(position, completed) {
      var watched = watchedSinceSave;
      watchedSinceSave = 0;
      fetch(saveUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        credentials: 'same-origin',
        keepalive: !!completed,
        body: JSON.stringify({ position: position, completed: !!completed, watched: watched })
      }).then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.progress_percent !== undefined) updateProgressBar(d.progress_percent);
        })
        .catch(function (e) { console.error('Progress save error:', e); });
    }

    return {
      tick: function () {
        var current = arguments[0];
        if (current - lastSaved >= 10) {
          watchedSinceSave = current - lastSaved;
          lastSaved = current;
          save(current, false);
        }
      },
      flush: function (current) { save(current, false); },
      finish: function (current) { save(current, true); },
      position: function () { return lastSaved; }
    };
  }

  function updateProgressBar(percent) {
    var bars = document.querySelectorAll('[data-progress-percent]');
    bars.forEach(function (bar) {
      bar.style.width = percent + '%';
      var label = document.querySelector('[data-progress-text]');
      if (label) label.textContent = percent + '%';
    });
  }

  var lessonVideo = document.getElementById('lesson-video');
  var lessonEmbed = document.getElementById('lesson-embed');

  if (lessonVideo) {
    var r = makeReporter(lessonVideo.getAttribute('data-lesson-id'),
                         lessonVideo.getAttribute('data-resume'));
    var resume = parseInt(lessonVideo.getAttribute('data-resume') || '0', 10);
    if (resume > 5) {
      lessonVideo.addEventListener('loadedmetadata', function () { lessonVideo.currentTime = resume; });
    }
    lessonVideo.addEventListener('timeupdate', function () { r.tick(Math.floor(lessonVideo.currentTime)); });
    lessonVideo.addEventListener('pause', function () { r.flush(Math.floor(lessonVideo.currentTime)); });
    lessonVideo.addEventListener('ended', function () { r.finish(Math.floor(lessonVideo.currentTime)); });
    window.addEventListener('beforeunload', function () {
      if (lessonVideo.currentTime > 0) r.flush(Math.floor(lessonVideo.currentTime));
    });
  } else if (lessonEmbed && lessonEmbed.getAttribute('data-provider') === 'youtube') {
    // YouTube's IFrame API is the only supported way to read playback position
    // across the origin boundary.
    window.onYouTubeIframeAPIReady = function () {
      var player = new YT.Player(lessonEmbed);
      var rep = null;
      player.on('onReady', function () {
        rep = makeReporter(lessonEmbed.getAttribute('data-lesson-id'),
                           lessonEmbed.getAttribute('data-resume'));
        var resume = parseInt(lessonEmbed.getAttribute('data-resume') || '0', 10);
        if (resume > 5) player.seekTo(resume, true);
      });
      player.on('onStateChange', function (e) {
        if (!rep) return;
        if (e.data === YT.PlayerState.PLAYING) {
          // Poll while playing; the embed gives no timeupdate event.
          if (!rep._timer) {
            rep._timer = setInterval(function () {
              var t = Math.floor(player.getCurrentTime() || 0);
              if (t > 0) rep.tick(t);
            }, 5000);
          }
        } else {
          if (rep._timer) { clearInterval(rep._timer); rep._timer = null; }
          var t = Math.floor(player.getCurrentTime() || 0);
          if (e.data === YT.PlayerState.ENDED) rep.finish(t);
          else if (t > 0) rep.flush(t);
        }
      });
    };
    if (window.YT && window.YT.Player) {
      window.onYouTubeIframeAPIReady();
    } else {
      var s = document.createElement('script');
      s.src = 'https://www.youtube.com/iframe_api';
      s.async = true;
      document.head.appendChild(s);
    }
  } else if (lessonEmbed) {
    // Other providers: mark complete on open, since position is unknowable.
    var rr = makeReporter(lessonEmbed.getAttribute('data-lesson-id'),
                          lessonEmbed.getAttribute('data-resume'));
    rr.finish(Math.max(1, parseInt(lessonEmbed.getAttribute('data-resume') || '1', 10)));
  }

  // ===== Sidebar drawer (mobile) =====
  var sidebar = document.getElementById('sidebar');
  var menuToggle = document.getElementById('menuToggle');
  var backdrop = document.getElementById('sidebarBackdrop');

  function openSidebar() {
    if (!sidebar) return;
    sidebar.classList.add('open');
    if (backdrop) backdrop.classList.add('show');
    if (menuToggle) menuToggle.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
  }

  function closeSidebar() {
    if (!sidebar) return;
    sidebar.classList.remove('open');
    if (backdrop) backdrop.classList.remove('show');
    if (menuToggle) menuToggle.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  }

  if (menuToggle) {
    menuToggle.addEventListener('click', function () {
      if (sidebar.classList.contains('open')) closeSidebar();
      else openSidebar();
    });
  }

  if (backdrop) {
    backdrop.addEventListener('click', closeSidebar);
  }

  // Close drawer when a nav link is tapped on mobile
  document.querySelectorAll('.sidebar-link').forEach(function (link) {
    link.addEventListener('click', function () {
      if (sidebar && sidebar.classList.contains('open')) closeSidebar();
    });
  });

  // Close drawer on resize back to desktop
  window.addEventListener('resize', function () {
    if (window.innerWidth > 900) closeSidebar();
  });

  // ===== Auto-dismiss + manual dismiss alerts =====
  function dismissAlert(alert) {
    if (!alert || alert.classList.contains('is-hidden')) return;
    alert.classList.add('is-hidden');
    alert.addEventListener('transitionend', function () { alert.remove(); },
      { once: true });
    setTimeout(function () { alert.remove(); }, 500);
  }

  // Manual dismiss (close button) via delegation
  document.addEventListener('click', function (e) {
    var close = e.target.closest('.alert-close');
    if (close) dismissAlert(close.closest('.alert'));
  });

  document.querySelectorAll('.alert-dismiss').forEach(function (alert) {
    setTimeout(function () { dismissAlert(alert); }, 6000);
  });

  // Cookie helper for CSRF
  function getCookie(name) {
    var value = '; ' + document.cookie;
    var parts = value.split('; ' + name + '=');
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
  }

  // ===== Scroll reveal (progressive enhancement) =====
  var revealEls = document.querySelectorAll('.reveal');
  if (revealEls.length) {
    if ('IntersectionObserver' in window &&
        window.matchMedia('(prefers-reduced-motion: no-preference)').matches) {
      var ro = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            ro.unobserve(entry.target);
          }
        });
      }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
      revealEls.forEach(function (el) { ro.observe(el); });
    } else {
      revealEls.forEach(function (el) { el.classList.add('is-visible'); });
    }
  }

  // ===== Stat count-up =====
  document.querySelectorAll('[data-count]').forEach(function (el) {
    var raw = el.getAttribute('data-count').trim();
    var target = parseFloat(raw);
    if (isNaN(target)) return;
    var decimals = (raw.split('.')[1] || '').length;
    var suffix = el.textContent.replace(/[0-9.]/g, '');
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce || !('requestAnimationFrame' in window)) {
      el.textContent = target.toFixed(decimals) + suffix;
      return;
    }
    var dur = 700, start = null;
    function tick(ts) {
      if (!start) start = ts;
      var p = Math.min((ts - start) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = (eased * target).toFixed(decimals) + suffix;
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  });

})();
