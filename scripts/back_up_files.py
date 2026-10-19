import os
import glob
import time
import schedule

from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive


# Configuration
LOCAL_DIR = r'C:\Users\Nortek1000\Documents\Nortek\Deployment\Online'
DRIVE_FOLDER_ID = '1HQrbL4uMdQmaTPMI9Hhg2ENSSYOngnqw'
INTERVAL_MINUTES = 5

# Authenticate
gauth = GoogleAuth()
gauth.LocalWebserverAuth()
drive = GoogleDrive(gauth)

# Track successfully synchronized files
synced_files = {}


def run():
    print('\nStarting synchronization...')

    try:
        # Retrieve remote files
        file_list = drive.ListFile({
            'q': f"'{DRIVE_FOLDER_ID}' in parents and trashed=false"
        }).GetList()

        remote_files = {
            f['title']: f
            for f in file_list
        }

    except Exception as e:
        print(f'Failed to retrieve Google Drive files: {e}')
        return

    # Retrieve local files
    local_files = sorted(
        glob.glob(os.path.join(LOCAL_DIR, 'Terminal_2026*.txt'))
    )

    print(f'{len(local_files)} local files found .... beeeer!')

    for local_file in local_files:
        filename = os.path.basename(local_file)

        try:
            # Get current file state
            stat = os.stat(local_file)
            file_state = (stat.st_mtime_ns, stat.st_size)

            # Skip files that have not changed since successful sync
            if (
                filename in remote_files
                and synced_files.get(local_file) == file_state
            ):
                continue

            print(f'Processing: {filename}')

            if filename in remote_files:
                # Update existing file
                remote_file = remote_files[filename]
                remote_file.SetContentFile(local_file)
                remote_file.Upload()

                print(f'Updated: {filename}')

            else:
                # Upload new file
                remote_file = drive.CreateFile({
                    'title': filename,
                    'parents': [{'id': DRIVE_FOLDER_ID}]
                })

                remote_file.SetContentFile(local_file)
                remote_file.Upload()

                remote_files[filename] = remote_file

                print(f'Uploaded: {filename}')

            # Verify file did not change during upload
            new_stat = os.stat(local_file)
            new_state = (new_stat.st_mtime_ns, new_stat.st_size)

            if new_state == file_state:
                synced_files[local_file] = file_state
            else:
                synced_files.pop(local_file, None)
                print(f'File changed during upload: {filename}')

        except Exception as e:
            print(f'Error processing {filename}: {e}')

    print('Synchronization completed')


# Run immediately
run()

# Schedule subsequent synchronizations
schedule.every(INTERVAL_MINUTES).minutes.do(run)

while True:
    schedule.run_pending()
    time.sleep(1)