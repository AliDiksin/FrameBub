import hashlib
import re
import urllib.parse


def mediawiki_thumb_url(base_or_api_url, filename, thumb_width):
    """Build a deterministic MediaWiki thumbnail URL for a file name."""
    base_url = str(base_or_api_url or "").rsplit("/api.php", 1)[0].rstrip("/")
    normalized_name = str(filename or "").strip().replace(" ", "_")
    if not base_url or not normalized_name:
        return ""
    digest = hashlib.md5(normalized_name.encode("utf-8")).hexdigest()
    encoded_name = urllib.parse.quote(normalized_name, safe="._()-")
    return f"{base_url}/images/thumb/{digest[0]}/{digest[:2]}/{encoded_name}/{thumb_width}px-{encoded_name}"


def resize_mediawiki_thumb_url(url, thumb_width):
    """Resize a MediaWiki thumbnail URL by replacing the trailing width segment."""
    text = str(url or "").strip()
    if not text:
        return ""
    return re.sub(r"/\d+px-([^/]+)$", rf"/{thumb_width}px-\1", text)
