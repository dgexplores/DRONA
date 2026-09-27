"""Work out how a lesson's video should be played.

A lesson stores one `video_url`, which in practice is a YouTube/Vimeo watch link
about as often as it is a direct file. A YouTube watch URL cannot be handed to a
<video src> - the browser downloads an HTML page and plays nothing, silently.
So detect the provider and hand the template either an embed URL or a plain
media URL.
"""
from urllib.parse import parse_qs, urlparse

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}
VIMEO_HOSTS = {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}


def _youtube_id(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        return None
    if host.endswith("youtu.be"):
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path == "/watch":
        candidate = (parse_qs(parsed.query).get("v") or [""])[0]
    else:
        parts = [p for p in parsed.path.split("/") if p]
        # /embed/<id>, /v/<id>, /shorts/<id>, /live/<id>
        if len(parts) >= 2 and parts[0] in {"embed", "v", "shorts", "live"}:
            candidate = parts[1]
        else:
            candidate = ""
    return candidate if len(candidate or "") == 11 else None


def _vimeo_id(url):
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in VIMEO_HOSTS:
        return None
    parts = [p for p in parsed.path.split("/") if p and p.isdigit()]
    return parts[-1] if parts else None


def resolve_video(url):
    """Return a dict describing how to play `url`.

    kind: 'embed'  -> use `embed_url` in an <iframe>
          'file'   -> use `src` in a <video> element
          None     -> nothing usable was supplied
    """
    if url:
        url = url.strip()
    if not url:
        return {"kind": None, "src": "", "embed_url": "", "provider": ""}

    if yt := _youtube_id(url):
        return {
            "kind": "embed",
            "src": "",
            "embed_url": f"https://www.youtube-nocookie.com/embed/{yt}",
            "provider": "youtube",
        }
    if vimeo := _vimeo_id(url):
        return {
            "kind": "embed",
            "src": "",
            "embed_url": f"https://player.vimeo.com/video/{vimeo}",
            "provider": "vimeo",
        }
    return {"kind": "file", "src": url, "embed_url": "", "provider": ""}
