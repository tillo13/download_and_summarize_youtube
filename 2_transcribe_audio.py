import speech_recognition as sr
from pydub import AudioSegment
import os
import re
import time
import csv
import datetime
import shutil  # Add this import

# Set chunk length in seconds.
GLOBAL_CHUNK_LENGTH = 30

# Setup directories.
input_dir = "download"
transcripts_folder = os.path.join("download", "transcripts")
chunking_log_dir = "transcribe"
os.makedirs(chunking_log_dir, exist_ok=True)

# Generate timestamp for the current run.
run_timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

# Supported audio formats.
supported_formats = [".ogg", ".oga", ".mp4", ".mp3", ".wav"]
recognizer = sr.Recognizer()

# Function: Get audio duration in milliseconds.
def get_audio_duration_ms(input_filepath):
    return len(AudioSegment.from_file(input_filepath))

# Function: Convert seconds to a time string.
def time_str(seconds):
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

# Function: Save transcription logs to CSV.
def save_log_to_csv(log_data, base_filename):
    sanitized_filename = re.sub(r"[^\w\s]", "", base_filename.replace(" ", "_")).lower()
    csv_file_path = os.path.join(chunking_log_dir, f"{sanitized_filename}_{run_timestamp}_translation_logs.csv")
    headers = ["time_stamp", "file_name", "pk_id", "chunk_number", "chunk_length_in_seconds", "transcribed_text", "success_count", "failure_count", "estimated_time_remaining"]

    needs_header = not os.path.exists(csv_file_path)
    with open(csv_file_path, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        if needs_header:
            writer.writeheader()
        writer.writerow(log_data)

# Function: Clear the 'transcribe' folder contents.
def clear_transcribe_folder():
    if os.path.exists(chunking_log_dir):
        for filename in os.listdir(chunking_log_dir):
            file_path = os.path.join(chunking_log_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'Failed to delete {file_path}. Reason: {e}')
        print(f"Cleared the '{chunking_log_dir}' folder.")

# Function: Use existing transcript if available.
def use_existing_transcript_if_available(input_filepath, pk_id, base_filename):
    """
    Checks if a matching transcript file exists in the transcripts folder and uses it to populate the CSV.
    Returns True if a transcript was found and used, False otherwise.
    """
    transcript_file_name = f"{base_filename}.txt"
    transcript_file_path = os.path.join(transcripts_folder, transcript_file_name)
    if os.path.exists(transcript_file_path):
        with open(transcript_file_path, 'r', encoding='utf-8') as transcript_file:
            transcribed_text = transcript_file.read()
        
        log_data = {
            "time_stamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "file_name": os.path.basename(input_filepath),
            "pk_id": pk_id,
            "chunk_number": 1,
            "chunk_length_in_seconds": "NA",  # Not applicable for pre-transcribed content
            "transcribed_text": transcribed_text,
            "success_count": 1,  # Marked as a successful transcription
            "failure_count": 0,
            "estimated_time_remaining": "NA"  # Not applicable
        }
        save_log_to_csv(log_data, base_filename)
        print(f"Used existing transcript for {os.path.basename(input_filepath)} located at {transcript_file_path} in the console log")
        return True
    return False

# Function: Process each audio file.
def process_audio_file(input_filepath, file_number, total_files, total_duration_ms, processed_files_duration_so_far):
    print(f"\nProcessing file {file_number} of {total_files}: {os.path.basename(input_filepath)}")

    base_filename = os.path.splitext(os.path.basename(input_filepath))[0]

    try:
        pk_id_str = re.search(r"_pkid_(\d+)", base_filename).group(1)
        pk_id = int(pk_id_str)
    except AttributeError:
        print(f"Warning: Could not extract pk_id from {input_filepath}. Setting pk_id to None.")
        pk_id = None

    # Check for an existing transcript before processing.
    if use_existing_transcript_if_available(input_filepath, pk_id, base_filename):
        return processed_files_duration_so_far  # Skip processing if transcript is used

    try:
        audio = AudioSegment.from_file(input_filepath)
    except Exception as e:
        print(f"Error loading {input_filepath}: {e}")
        return processed_files_duration_so_far

    chunk_length_ms = GLOBAL_CHUNK_LENGTH * 1000
    processed_file_duration_ms = 0
    file_duration_ms = len(audio)
    total_chunks = len(audio) // chunk_length_ms + (1 if len(audio) % chunk_length_ms else 0)
    chunks_success = 0
    chunks_failure = 0

    for i, chunk in enumerate(audio[i:i+chunk_length_ms] for i in range(0, len(audio), chunk_length_ms)):
        chunk_name = "temp_chunk.wav"
        chunk.export(chunk_name, format="wav")

        text = ""
        try:
            with sr.AudioFile(chunk_name) as source:
                audio_listened = recognizer.record(source)
                text = recognizer.recognize_google(audio_listened)
                chunks_success += 1
                print("==============================")
                print(f"Processing chunk {i+1}/{total_chunks}.")
                print(f"From second {i * GLOBAL_CHUNK_LENGTH}s to {(i+1) * GLOBAL_CHUNK_LENGTH}s.")
                print(f"Total seconds in file: {file_duration_ms // 1000}.")
                print("TRANSCRIBED TEXT: ", text)
        except sr.UnknownValueError:
            chunks_failure += 1
            print(f"Chunk {i+1}: Google SR could not understand audio.")
        except sr.RequestError as e:
            chunks_failure += 1
            print(f"Chunk {i+1}: Request failed; {e}")
        finally:
            os.remove(chunk_name)

        processed_file_duration_ms += chunk_length_ms
        updated_total_processed_duration_so_far = processed_files_duration_so_far + processed_file_duration_ms
        overall_elapsed_time = time.time() - start_time
        processed_ratio = updated_total_processed_duration_so_far / total_duration_ms
        estimated_total_time = overall_elapsed_time / processed_ratio
        estimated_remaining_time = estimated_total_time - overall_elapsed_time

        print(f"All files ({total_files}) total seconds: {total_duration_ms // 1000}")
        print(f"Estimated time remaining for all files: {time_str(estimated_remaining_time)}")
        print("==============================")
        
        log_data = {
            "time_stamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "file_name": os.path.basename(input_filepath),
            "pk_id": pk_id,
            "chunk_number": i + 1,
            "chunk_length_in_seconds": GLOBAL_CHUNK_LENGTH,
            "transcribed_text": text,
            "success_count": chunks_success,
            "failure_count": chunks_failure,
            "estimated_time_remaining": time_str(estimated_remaining_time)
        }
        save_log_to_csv(log_data, base_filename)

    processed_files_duration_so_far += file_duration_ms

    # Log the individual processing summary
    print(f"===INDIVIDUAL PROCESSING for {os.path.basename(input_filepath)}===")
    print(f"Chunks successfully processed: {chunks_success}")
    print(f"Chunks failed to process: {chunks_failure}")
    print(f"% of success: {100. * chunks_success / total_chunks:.2f}%")

    return processed_files_duration_so_far

# Main processing block

# Count and display the number of log files before deletion
if os.path.exists(chunking_log_dir):
    log_files_count = len([f for f in os.listdir(chunking_log_dir) if os.path.isfile(os.path.join(chunking_log_dir, f))])
    print(f"Existing log files: {log_files_count}")

    # Clear the transcribe folder
    clear_transcribe_folder()

# Ensure the transcribe folder exists after deletion
if not os.path.exists(chunking_log_dir):
    os.makedirs(chunking_log_dir)

total_duration_ms = sum(get_audio_duration_ms(os.path.join(input_dir, filename))
                        for filename in os.listdir(input_dir) 
                        if os.path.splitext(filename)[1].lower() in supported_formats)

total_files = sum(1 for filename in os.listdir(input_dir) 
                  if os.path.splitext(filename)[1].lower() in supported_formats)

processed_files_duration = 0
current_file_number = 1
start_time = time.time()

for filename in os.listdir(input_dir):
    if os.path.splitext(filename)[1].lower() in supported_formats:
        filepath = os.path.join(input_dir, filename)
        processed_files_duration = process_audio_file(filepath, current_file_number, total_files, total_duration_ms, processed_files_duration)
        current_file_number += 1

end_time = time.time()
print("\n=== Overall Transcription Summary ===")
print(f"Total processing time: {time_str(end_time - start_time)} for {total_files} files.")