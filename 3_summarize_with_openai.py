import os
import csv
import datetime
from pathlib import Path
import json
from tqdm import tqdm
import pandas as pd
import tiktoken
from openai import OpenAI
import re
from dotenv import load_dotenv
load_dotenv()

from audio_postgres_utils import update_completion_boolean_with_pk_id, fetch_user_email_and_request_by_pkid

import sys
sys.path.append('../')  # Adjust path to import from parent directory
from gmail_utils.gmail_utils import send_email  # Modify according to your directory structure

# Configurable Variables
CHUNKING_LOG_DIR = "transcribe"  # Directory where transcribed text files are located

# OpenAI configuration
OPENAI_API_KEY = os.getenv("2023nov17_OPENAI_KEY")
MODEL = 'gpt-4-turbo'  # Model name
MODEL_LIMIT = 128000  # Maximum number of tokens the model can handle
INPUT_COST_PER_MILLION = 10.00  # Cost per 1M tokens for input per https://openai.com/api/pricing
OUTPUT_COST_PER_MILLION = 30.00  # Cost per 1M tokens for output

def calculate_cost(token_count, cost_per_million):
    return (token_count / 1_000_000) * cost_per_million

GLOBAL_SYSTEM_PROMPT = "Summarize the following text."
GLOBAL_OPENAI_TEMPERATURE = 1

# Function to get chat completion from OpenAI
def get_chat_completion(messages, filename, model=MODEL, api_key=OPENAI_API_KEY):
    client = OpenAI(api_key=api_key)
    
    # Making the API call
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=GLOBAL_OPENAI_TEMPERATURE,
    )

    # Converting the response to JSON-compatible format
    response_data = response.to_dict()
    print("Response data (full JSON):")
    print(json.dumps(response_data, indent=4))  # Pretty print the full response data
    
    return response_data

# Function to tokenize the text
def tokenize(text):
    encoding = tiktoken.encoding_for_model(MODEL)
    return encoding.encode(text)

# Function to send email with attachments
def send_email_with_attachments(transcription_dir, pk_id, user_email, summary_content, prompt, original_filename, download_time):
    """
    Send an email with attachments that only match the current pk_id being processed.
    """
    transcription_files = []

    for file in transcription_dir.glob(f"*_pkid_{pk_id}_*"):
        transcription_files.append(str(file))
    
    if user_email and transcription_files:
        user_name = user_email.split('@')[0].replace('.', ' ').title()
        is_default_prompt = prompt.strip() == GLOBAL_SYSTEM_PROMPT
        
        email_body = f"""
        <html>
            <body>
                <p>Hello {user_name},</p>
                <p>Welcome! What you're seeing here is the result of our audio processing script. We downloaded, transcribed, and summarized the audio content you provided.</p>
                <p>{'You provided a custom prompt for this request.' if not is_default_prompt else 'We used our default prompt to process your audio.'}</p>
                <p><strong>What you asked:</strong></p>
                <p><i>{prompt}</i></p>
                <p><strong>Here is the response to your request:</strong></p>
                <p><i>{summary_content}</i></p>
                <p><strong>Original Filename:</strong> {original_filename}</p>
                <p><strong>Downloaded Time:</strong> {download_time}</p>
            </body>
        </html>
        """
        subject = "Results from Your Audio Processing Request"
        to_emails = [user_email]
        
        send_email(subject, email_body, to_emails, transcription_files, is_html=True)
        print(f"Email with {len(transcription_files)} attachments successfully sent to {user_email}")
    else:
        print(f"No relevant transcription files found for pk_id {pk_id}, or no email associated.")

# Function to save the response from OpenAI to a CSV
def save_response_to_csv(response_data, chunk_sent, output_filename, pk_id, token_count, input_cost_estimate, output_cost_estimate, total_cost_estimate):
    csv_file = Path(output_filename)
    
    headers = ["id", "created", "model", "system_fingerprint", "completion_tokens", "prompt_tokens", "total_tokens", "response_from_openai", "chunk_sent_to_openai", "pk_id", "tiktoken_count", "input_cost_estimate", "output_cost_estimate", "total_cost_estimate"]
    
    row_data = {
        "id": response_data["id"],
        "created": datetime.datetime.fromtimestamp(response_data["created"]).isoformat(),
        "model": response_data["model"],
        "system_fingerprint": response_data["system_fingerprint"],
        "completion_tokens": response_data["usage"]["completion_tokens"],
        "prompt_tokens": response_data["usage"]["prompt_tokens"],
        "total_tokens": response_data["usage"]["total_tokens"],
        "response_from_openai": response_data["choices"][0]["message"]["content"],
        "chunk_sent_to_openai": chunk_sent,
        "pk_id": pk_id,
        "tiktoken_count": token_count,
        "input_cost_estimate": input_cost_estimate,
        "output_cost_estimate": output_cost_estimate,
        "total_cost_estimate": total_cost_estimate
    }
    
    with open(csv_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        writer.writerow(row_data)

# Function to parse filename for original filename and download time
def parse_filename(filename):
    base_filename, _ = os.path.splitext(filename)
    match = re.match(r"(.+)_pkid_(\d+)_([0-9]+_[0-9]+)_translation_logs", base_filename)
    if match:
        original_filename = match.group(1).replace("__", " ").replace("_", " ").title()
        pk_id = match.group(2)
        download_time_str = match.group(3)
        download_time = datetime.datetime.strptime(download_time_str, '%Y%m%d_%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
        return original_filename, download_time
    else:
        return "Unknown", "Unknown"

# Function to read and summarize CSV files
def read_and_summarize_csv_files():
    total_cost_across_all_files = 0
    chunking_log_dir = Path(CHUNKING_LOG_DIR)
    print(f"Looking for CSV files in the directory: {chunking_log_dir}")
    csv_files = list(chunking_log_dir.glob("*.csv"))

    if not csv_files:
        print("No CSV files found in the specified directory. Exiting the function.")
        return
    else:
        print(f"Found {len(csv_files)} CSV file(s) in the directory.")

    for csv_file_path in csv_files:
        if csv_file_path.name.endswith("_summarized_response.csv"):
            print(f"Skipping already summarized file: {csv_file_path}")
            continue

        print(f"\nReading CSV file {csv_file_path}...")

        # Extracting pk_id using regular expression to ensure each file can be uniquely identified if needed.
        pk_id_match = re.search(r"_pkid_([0-9]+)_", csv_file_path.name)
        pk_id = pk_id_match.group(1) if pk_id_match else "NULL"
        print(f"Extracted pk_id from filename: {pk_id}")

        df = pd.read_csv(csv_file_path)

        if 'transcribed_text' not in df.columns:
            print(f"Expected 'transcribed_text' column not found in {csv_file_path}. Skipping this file.")
            continue
        else:
            print("Successfully located 'transcribed_text' column. Compiling text for summarization...")

        complete_text = ' '.join(df['transcribed_text'].fillna('').values)
        print("Text compiled from CSV. Preparing to request summarization...")
        token_count = len(tokenize(complete_text))  # Using the tokenize function here to count tokens
        
        used_percentage = (token_count / MODEL_LIMIT) * 100
        used_percentage_formatted = f"{used_percentage:.7f}%"
        input_cost_estimate = calculate_cost(token_count, INPUT_COST_PER_MILLION)
        output_cost_estimate = calculate_cost(token_count, OUTPUT_COST_PER_MILLION)
        total_cost_estimate = input_cost_estimate + output_cost_estimate

        # Update the cumulative total cost
        total_cost_across_all_files += total_cost_estimate
        
        print(f"Token count for current combined chunks: {token_count}")
        print(f"Model = {MODEL}")
        print(f"Limit = {MODEL_LIMIT}")
        print(f"% used of limit = {token_count}/{MODEL_LIMIT} = {used_percentage_formatted}")
        print(f"Estimated input cost: ${input_cost_estimate:.7f}")
        print(f"Estimated output cost: ${output_cost_estimate:.7f}")
        print(f"Total estimated cost: ${total_cost_estimate:.7f}")
  
        output_filename = str(csv_file_path).replace(".csv", "_summarized_response.csv")
        
        user_email, user_request = fetch_user_email_and_request_by_pkid(pk_id=pk_id)
        
        original_filename, download_time = parse_filename(csv_file_path.name)

        if user_request:
            file_specific_prompt = user_request
        else:
            file_specific_prompt = f"""
            You are being passed data about an audio file we attempted to transcribe with the filename: {csv_file_path.name}. 
            Please read the provided text content and summarize the main points in bullet points, focusing on topics, themes, or notable elements discussed. 
            If you find the text content sparse or absent, then refer to the filename to deduce what the audio could be about, 
            and summarize potential topics in bullet points. 
            Use the filename only as a last resort for deducing the content's nature.
            """

        messages = [{"role": "system", "content": file_specific_prompt},
                    {"role": "user", "content": complete_text}]
        
        response_data = get_chat_completion(messages, csv_file_path.name) 

        print(f"Received response for {csv_file_path.name}. Proceeding to save the summary...")      

        save_response_to_csv(response_data, complete_text, output_filename, pk_id, token_count, input_cost_estimate, output_cost_estimate, total_cost_estimate)

        print(f"Summary successfully saved as {output_filename}")

        # After saving the summary successfully
        update_completion_boolean_with_pk_id(pk_id=pk_id)

        # Prepare the OpenAI summary content from the response_data obtained from OpenAI
        openai_summary = response_data['choices'][0]['message']['content'] if response_data and response_data['choices'] else "No summary available."

        # Then call send_email_with_attachments with the correctly set variables
        if user_email:  # Check if user_email was successfully fetched
            send_email_with_attachments(chunking_log_dir, pk_id, user_email, openai_summary, file_specific_prompt, original_filename, download_time)
        else:
            print(f"Could not fetch email for pk_id: {pk_id} or no files found to attach. No email sent.")

    # Print the cumulative total cost at the end
    print("===SUMMARY RESULTS===")
    print(f"Total cost incurred for OpenAI API calls across all files: ${total_cost_across_all_files:.2f}")

def main():
    read_and_summarize_csv_files()

if __name__ == "__main__":
    main()