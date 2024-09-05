import re
import logging
from urllib.parse import urlparse, parse_qs

def extract_video_id(youtube_url):
    """This function extracts the video ID from a YouTube URL."""
    # Parse the URL into components
    parsed_url = urlparse(youtube_url)
    # Try extracting the video ID from 'v' query parameter
    video_id = parse_qs(parsed_url.query).get("v")
    if not video_id:
        # If URL is in the format http://youtu.be/<video_id>
        if parsed_url.hostname in ['youtu.be']:
            video_id = parsed_url.path[1:]  # Strip leading slash
        else:
            raise ValueError("Unable to extract Video ID from YouTube URL")
    return video_id[0] if isinstance(video_id, list) else video_id

def validate_youtube_url(youtube_url):
    logging.info(f'Validating YouTube URL: {youtube_url}')  # New logging line
    try:
        if is_valid_youtube_url(youtube_url):
            video_id = extract_video_id(youtube_url)
            return True, video_id
        else:
            return False, "Invalid YouTube URL format."
    except Exception as e:
        logging.error(f'Error occurred while validating URL: {e}')  # New logging line
        return False, str(e)

def is_valid_youtube_url(youtube_url):
    logging.info(f'Checking if URL is valid: {youtube_url}')  # New logging line
    parsed_url = urlparse(youtube_url)
    if parsed_url.hostname not in ['www.youtube.com', 'youtube.com', 'youtu.be']:
        return False
    if parsed_url.hostname == 'youtu.be' and not parsed_url.path:
        return False
    if parsed_url.hostname in ['www.youtube.com', 'youtube.com'] and not parse_qs(parsed_url.query).get("v"):
        return False
    return True