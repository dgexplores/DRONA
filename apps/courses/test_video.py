from django.test import SimpleTestCase

from apps.courses.video import resolve_video


class ResolveVideoTests(SimpleTestCase):
    """A pasted YouTube link must never be handed to <video src>.

    That combination downloads an HTML page and plays nothing, silently, so the
    form's own placeholder used to advertise links that could not work.
    """

    def test_youtube_watch_url_becomes_an_embed(self):
        r = resolve_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(r["kind"], "embed")
        self.assertEqual(r["provider"], "youtube")
        self.assertEqual(r["embed_url"],
                         "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?enablejsapi=1&rel=0")
        self.assertEqual(r["src"], "")

    def test_short_youtube_url_forms(self):
        for url in (
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        ):
            with self.subTest(url=url):
                self.assertEqual(resolve_video(url)["embed_url"],
                                 "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?enablejsapi=1&rel=0")

    def test_vimeo_becomes_an_embed(self):
        r = resolve_video("https://vimeo.com/123456789")
        self.assertEqual(r["kind"], "embed")
        self.assertEqual(r["embed_url"], "https://player.vimeo.com/video/123456789")

    def test_direct_file_is_played_by_the_video_element(self):
        for url in ("https://cdn.example.com/sop.mp4", "https://x.test/a.webm", "https://x.test/s.m3u8"):
            with self.subTest(url=url):
                r = resolve_video(url)
                self.assertEqual(r["kind"], "file")
                self.assertEqual(r["src"], url)

    def test_empty_and_garbage_values(self):
        for value in ("", None, "   "):
            self.assertIsNone(resolve_video(value)["kind"])

    def test_a_watch_url_without_an_id_is_not_treated_as_a_video(self):
        # "watch" with no v= must not silently become a broken embed.
        self.assertEqual(resolve_video("https://www.youtube.com/watch")["kind"], "file")


class EmbedProgressTests(SimpleTestCase):
    """A YouTube lesson must be completable.

    The progress heartbeat used to run only when a <video> element existed, so an
    embedded YouTube lesson could be watched forever and never complete - the
    course would never finish and no certificate would be issued.
    """

    def test_youtube_embed_enables_the_iframe_api(self):
        url = resolve_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ")["embed_url"]
        self.assertIn("enablejsapi=1", url,
                      "without enablejsapi the page cannot read playback position")

    def test_lesson_page_wires_an_embed_hook(self):
        import re
        from pathlib import Path
        tpl = Path("templates/courses/lesson.html").read_text(encoding="utf-8")
        self.assertIn('id="lesson-embed"', tpl)
        self.assertIn('data-provider="{{ video.provider }}"', tpl)
        self.assertIn("data-resume=", tpl)

    def test_csp_allows_the_youtube_iframe_api(self):
        from pathlib import Path
        mw = Path("srms_dorna/middleware.py").read_text(encoding="utf-8")
        self.assertIn("https://www.youtube.com;", mw,
                      "script-src must allow the IFrame API or progress silently fails")
