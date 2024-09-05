import subprocess
import sys
import os

# Define a list of scripts you want to run in order
scripts_to_run = ['1_download_audio.py', '2_transcribe_audio.py', '3_summarize_with_openai.py']

# Iterate over the script list to run them one by one
for script in scripts_to_run:
    print(f"Running {script}...\n")
    
    # Ensure the working directory is the same as this script's directory
    script_path = os.path.join(os.path.dirname(__file__), script)

    # Starting the process, directing standard output and standard error directly to the console
    process = subprocess.Popen(['python', script_path], stdout=sys.stdout, stderr=sys.stderr)

    # Wait for the process to complete
    process.wait()

    # Check if the process exited with an error
    if process.returncode == 100:
        print(f"\n{script} reported no submissions to process. Exiting gracefully.\n")
        break
    elif process.returncode != 0:
        print(f"\nFailed to run {script} with error code: {process.returncode}\n")
        break