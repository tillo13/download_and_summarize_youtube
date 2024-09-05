# Audio Processing App

This project is an audio processing application that automates the download, transcription, and summarization of audio files using OpenAI's API and other utilities.

## Table of Contents

1. [Project Structure](#project-structure)
2. [Setting Up](#setting-up)
3. [Running the Application](#running-the-application)
4. [Scripts Description](#scripts-description)
5. [Dependencies](#dependencies)

## Project Structure

The application consists of a total of 10 Python files spread across 2 directories.

### Directory Structure:
├── . │ ├── 0_run_all.py │ ├── 1_download_audio.py │ ├── 2_transcribe_audio.py │ ├── 3_summarize_with_openai.py │ ├── audio_postgres_utils.py │ ├── gather_pythons.py │ ├── google_secret_utils.py │ ├── youtube_utils.py │ ├── gmail_utils │ ├── gmail_utils.py │ ├── google_secret_utils.py

### List of Python File Paths:
- `./0_run_all.py`
- `./1_download_audio.py`
- `./2_transcribe_audio.py`
- `./3_summarize_with_openai.py`
- `./audio_postgres_utils.py`
- `./gather_pythons.py`
- `./google_secret_utils.py`
- `./youtube_utils.py`
- `./gmail_utils/gmail_utils.py`
- `./gmail_utils/google_secret_utils.py`

## Setting Up

1. **Clone the repository:**
    ```sh
    git clone <repository_url>
    cd <repository_directory>
    ```

2. **Install dependencies:**
    ```sh
    pip install -r requirements.txt
    ```

3. **Setup environment variables:**
    Create a `.env` file in the root directory and add the necessary environment variables.
    ```env
    2024jan10_POSTGRES_HOST=<your_postgres_host>
    2024jan10_POSTGRES_DBNAME=<your_postgres_dbname>
    2024jan10_POSTGRES_USERNAME=<your_postgres_username>
    2024jan10_POSTGRES_PASSWORD=<your_postgres_password>
    2024jan10_POSTGRES_CONNECTION=<your_postgres_connection>
    2023nov17_OPENAI_KEY=<your_openai_key>
    2024may_17_GMAIL_USER=<your_gmail_user>
    2024may_17_GMAIL_PASSWORD=<your_gmail_password>
    ```
4. **Google Cloud Setup:**
    Ensure you have correctly set up and authorized the Google Cloud SDK, and have access to the secret manager.

## Running the Application

1. **Run All Scripts:**
    The `0_run_all.py` script runs all the necessary scripts in the defined order:
    ```sh
    python 0_run_all.py
    ```

## Scripts Description

### `0_run_all.py`
This script orchestrates the execution of all the following steps:
1. Download audio files.
2. Transcribe those audio files.
3. Summarize the transcriptions using OpenAI.

### `1_download_audio.py`
Downloads audio files from various sources like YouTube and Google Drive and saves them in a local directory for further processing.

### `2_transcribe_audio.py`
Transcribes the downloaded audio files using the Google Speech Recognition API and splits the audio into smaller chunks if necessary.

### `3_summarize_with_openai.py`
Summarizes the transcribed audio texts using OpenAI's GPT-4 model and sends a summary report to the user via email.

### `audio_postgres_utils.py`
Contains utility functions to interact with the PostgreSQL database for fetching and updating audio submissions information.

### `gather_pythons.py`
Gathers information about all the `.py` files in the project and writes detailed logs about each file.

### `google_secret_utils.py`
Utility script for fetching secrets from Google Cloud Secret Manager.

### `youtube_utils.py`
Utility functions for handling and validating YouTube URLs.

### `gmail_utils/gmail_utils.py`
Utility functions for sending emails, including setting up attachments and handling authentication with Google.

### `gmail_utils/google_secret_utils.py`
Utility script for fetching Gmail credentials from Google Cloud Secret Manager.

## Dependencies

- Python 3.8 or above
- YouTube Transcript API
- Pydub
- SpeechRecognition
- OpenAI
- Google Cloud Secret Manager
- psycopg2
- dotenv
- `yt_dlp`

Install dependencies using:
```sh
pip install -r requirements.txt
Make sure you have FFmpeg installed for audio processing used in Pydub:

# On Ubuntu
sudo apt update && sudo apt install ffmpeg

# On MacOS using Brew
brew install ffmpeg