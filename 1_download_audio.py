# Existing imports
import os
import time
import logging
import requests
from os import environ, path
from urllib.parse import urlparse, parse_qs, unquote
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled, NoTranscriptAvailable
import psycopg2
import psycopg2.extras
import yt_dlp as youtube_dl
import re
import shutil  # Add this import
import sys  # Add this import
from google.cloud import secretmanager  # Add this import

GCP_PROJECT_ID = "kumori-404602"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def load_env_file():
    dotenv_path = path.join(path.dirname(__file__), '.env')
    if path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        return True
    return False

def get_postgres_credentials(gcp_project_id=GCP_PROJECT_ID):
    try:
        if load_env_file():
            return {
                'host': environ.get('2024jan10_POSTGRES_HOST'),
                'dbname': environ.get('2024jan10_POSTGRES_DBNAME'),
                'user': environ.get('2024jan10_POSTGRES_USERNAME'),
                'password': environ.get('2024jan10_POSTGRES_PASSWORD'),
                'connection_name': environ.get('2024jan10_POSTGRES_CONNECTION')
            }
        else:
            raise Exception('.env file not found or not loaded')
    except Exception as env_error:
        logging.warning(f"Failed to load credentials from .env file: {env_error}")
        logging.info("Attempting to load credentials from Google Cloud Secret Manager")
        return {
            'host': get_secret_version(gcp_project_id, 'KUMORI_POSTGRES_IP'),
            'dbname': get_secret_version(gcp_project_id, 'KUMORI_POSTGRES_DB_NAME'),
            'user': get_secret_version(gcp_project_id, 'KUMORI_POSTGRES_USERNAME'),
            'password': get_secret_version(gcp_project_id, 'KUMORI_POSTGRES_PASSWORD'),
            'connection_name': get_secret_version(gcp_project_id, 'KUMORI_POSTGRES_CONNECTION_NAME'),
        }

def get_secret_version(project_id, secret_id, version_id="latest"):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode('UTF-8')

def get_db_connection(gcp_project_id=GCP_PROJECT_ID):
    db_credentials = get_postgres_credentials(gcp_project_id)
    is_gcp = environ.get('GAE_ENV', '').startswith('standard')
    
    if is_gcp:
        db_socket_dir = environ.get("DB_SOCKET_DIR", "/cloudsql")
        cloud_sql_connection_name = db_credentials['connection_name']
        host = f"{db_socket_dir}/{cloud_sql_connection_name}"
    else:
        host = db_credentials['host']
    
    try:
        conn = psycopg2.connect(
            dbname=db_credentials['dbname'],
            user=db_credentials['user'],
            password=db_credentials['password'],
            host=host
        )
        logging.info("Database connection established.")
        return conn
    except Exception as e:
        logging.error(f"Failed to connect to the database: {e}")
        return None

def fetch_audio_submissions(gcp_project_id=GCP_PROJECT_ID):
    conn = get_db_connection(gcp_project_id)
    if conn is not None:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                query = """
                SELECT pk_id, audio_url, date_submitted, format, ingest_point, 
                       email_address, last_updated, completion_boolean, comments, file_size
                FROM prod_user_audio_submissions
                WHERE completion_boolean = False
                """
                cur.execute(query)
                records = cur.fetchall()
                return records
        except Exception as e:
            logging.error(f"Error fetching audio submissions: {e}")
        finally:
            conn.close()
            logging.info("Database connection closed.")
    else:
        logging.error("Failed to create a database connection.")
        return []


# Set a variable for the downloaded files folder
DOWNLOADED_FILE_FOLDER_NAME = "download"

# Define the transcripts directory
transcripts_folder = os.path.join(DOWNLOADED_FILE_FOLDER_NAME, "transcripts")

# Initialize lists to keep track of processed files and download statuses
deleted_files = []
overwritten_files = []
download_failures = []
successful_downloads = []

def sanitize_filename(filename):
    """Sanitizes filenames to ensure they are valid and uniform."""
    base_filename, file_extension = os.path.splitext(filename)
    sanitized_filename = re.sub(r"[^\w\s]", "", base_filename.replace(" ", "_")).lower()
    return sanitized_filename + file_extension

def ensure_download_folder_exists():
    """Ensure the 'download' and 'download/transcripts' directories exist."""
    if not os.path.exists(DOWNLOADED_FILE_FOLDER_NAME):
        os.makedirs(DOWNLOADED_FILE_FOLDER_NAME)
    if not os.path.exists(transcripts_folder):
        os.makedirs(transcripts_folder)
    print(f"Ensured that folders '{DOWNLOADED_FILE_FOLDER_NAME}' and '{transcripts_folder}' exist")

def clear_download_folder():
    """Delete all files in the 'download' directory."""
    if os.path.exists(DOWNLOADED_FILE_FOLDER_NAME):
        for filename in os.listdir(DOWNLOADED_FILE_FOLDER_NAME):
            file_path = os.path.join(DOWNLOADED_FILE_FOLDER_NAME, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'Failed to delete {file_path}. Reason: {e}')
        print(f"Cleared the '{DOWNLOADED_FILE_FOLDER_NAME}' folder.")

def download_complete(d):
    """Callback function to log when a download is complete."""
    if d['status'] == 'finished':
        print(f"\nDownload Complete. File saved to {d['filename']}")
        successful_downloads.append(d['filename'])

def get_video_id(video_url):
    parsed_url = urlparse(video_url)
    if parsed_url.hostname == 'youtu.be':
        return parsed_url.path[1:]
    if parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
        if parsed_url.path == '/watch':
            return parse_qs(parsed_url.query).get('v', [None])[0]
        if '/embed/' in parsed_url.path:
            return parsed_url.path.split('/')[2]
        if parsed_url.path[:3] == '/v/':
            return parsed_url.path.split('/')[2]
    return None

def fetch_and_save_youtube_transcript(url, output_filename):
    video_id = get_video_id(url)
    if not video_id:
        print("Failed to extract video ID. No transcript will be saved.")
        return
    
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'en-US'])
        transcribed_text = "\n".join([f"{segment['start']}: {segment['text']}" for segment in transcript_list])
        
        transcript_file_path = os.path.join(transcripts_folder, f"{output_filename}.txt")
        
        with open(transcript_file_path, 'w', encoding='utf-8') as transcript_file:
            transcript_file.write(transcribed_text)
            
        print(f"Transcript saved successfully to {transcript_file_path}")
        
    except (TranscriptsDisabled, NoTranscriptFound, NoTranscriptAvailable) as e:
        print(f"Transcript not available: {e}")
    except Exception as e:
        print(f"Failed to fetch transcript: {e}")

def download_with_ytdlp(url, pk_id, output_filename):
    ydl_opts = {
        'format': 'best[ext=mp4]',  # Ensure MP4 format
        'noplaylist': True,
        'outtmpl': os.path.join(DOWNLOADED_FILE_FOLDER_NAME, f"{output_filename}.mp4"),
        'quiet': False,
        'progress_hooks': [download_complete]
    }
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

def download_and_convert_youtube(url, pk_id):
    try:
        video_id = get_video_id(url)
        if not video_id:
            print(f"Failed to extract video ID for URL: {url}")
            download_failures.append(url)
            return

        # Fetch video details using yt-dlp to get the title
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
        }
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            video_title = sanitize_filename(info_dict.get('title', f"video_{pk_id}"))

        output_filename = f"{video_title}_pkid_{pk_id}"
        
        # Download video and fetch transcript
        try:
            download_with_ytdlp(url, pk_id, output_filename)
            fetch_and_save_youtube_transcript(url, output_filename)
        except Exception as e:
            print(f"Failed to download {url} with yt-dlp. Error: {e}")
            download_failures.append(url)

    except Exception as e:
        print(f"Failed to download YouTube URL {url}. Error: {e}")
        download_failures.append(url)

def download_and_convert_google_drive(url, pk_id):
    final_url = url
    try:
        if "drive.google.com" in url:
            file_id_match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
            if file_id_match:
                file_id = file_id_match.group(1)
                final_url = f"https://drive.google.com/uc?id={file_id}&export=download"
        response = requests.get(final_url, stream=True)
        if b'accounts.google.com' in response.content[0:1000]:
            print("The file isn't shared properly or it's not available for download.")
            download_failures.append(final_url)
            return

        if response.status_code == 200:
            content_disposition = response.headers.get('Content-Disposition', '')
            filename = ''
            if 'filename=' in content_disposition:
                filename = content_disposition.split('filename=')[1].strip('"')
            else:
                filename = os.path.basename(final_url.split("?")[0])
            filename = unquote(filename)

            filename_with_pkid = f"{os.path.splitext(filename)[0]}_pkid_{pk_id}{os.path.splitext(filename)[1]}"
            sanitized_filename = sanitize_filename(filename_with_pkid)
            download_path = os.path.join(DOWNLOADED_FILE_FOLDER_NAME, sanitized_filename)
            
            with open(download_path, 'wb') as f:
                f.write(response.content)
            print(f"\nDownloaded Google Drive file to {download_path}")
            successful_downloads.append(download_path)

    except Exception as e:
        print(f"Failed to process Google Drive URL {final_url}. Error: {e}")
        download_failures.append(final_url)
    finally:
        print(f"\nFinished processing: {url} as gdrive with pk_id = {pk_id}")

def download_and_convert(url, ingest_point, pk_id):
    ensure_download_folder_exists()
    print(f"\nProcessing: {url} as {ingest_point} with pk_id = {pk_id}")
    if ingest_point == 'youtube':
        download_and_convert_youtube(url, pk_id)
    elif ingest_point == 'gdrive':
        download_and_convert_google_drive(url, pk_id)

if __name__ == "__main__":
    start_time = time.time()

    # Count and display the number of video and transcript files before deletion
    if os.path.exists(DOWNLOADED_FILE_FOLDER_NAME):
        video_files_count = len([f for f in os.listdir(DOWNLOADED_FILE_FOLDER_NAME) if os.path.isfile(os.path.join(DOWNLOADED_FILE_FOLDER_NAME, f))])
        transcript_files_count = len([f for f in os.listdir(transcripts_folder) if os.path.isfile(os.path.join(transcripts_folder, f))]) if os.path.exists(transcripts_folder) else 0
        print(f"Existing video files: {video_files_count}")
        print(f"Existing transcript files: {transcript_files_count}")

        # Clear the download folder
        clear_download_folder()

    # Ensure the download folder exists after deletion
    ensure_download_folder_exists()

    # Check if it has anything to process
    submissions = fetch_audio_submissions()
    print(f"Fetched {len(submissions)} submissions")
    if not submissions:
        print("No audio submissions to process. Exiting.")
        sys.exit(100)

    for submission in submissions:
        url = submission['audio_url']
        ingest_point = submission['ingest_point']
        pk_id = submission['pk_id']
        print(f"Processing Submission: URL={url}, Ingest Point={ingest_point}, PK_ID={pk_id}")
        download_and_convert(url, ingest_point, pk_id)

    print("\n=== Final Summary ===")
    print(f"Deleted Files: {deleted_files}")
    print(f"Overwritten Files: {overwritten_files}")
    print(f"Download Failures: {download_failures}")
    print(f"Successful Downloads: {len(successful_downloads)}")
    print(f"Failed Downloads: {len(download_failures)}")

    end_time = time.time()
    print(f"\nTotal Time Taken: {end_time - start_time:.2f} seconds")