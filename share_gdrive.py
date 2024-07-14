import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import TransportError
from googleapiclient.http import MediaFileUpload


# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/drive"]
SERVICE = None

def get_token():
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if not os.path.exists("credentials.json"):
        print("No credentials.json file found. For Upload to gdrive please set up your authentication.")
        print("Info on how to do it: https://developers.google.com/drive/api/quickstart/python#enable_the_api")
        exit()
    flow = InstalledAppFlow.from_client_secrets_file(
        "credentials.json", SCOPES
    )
    creds = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open("token.json", "w") as token:
        token.write(creds.to_json())

def get_credentials():
    global SERVICE
    dir_path = os.path.dirname(os.path.realpath(__file__))
    token_path = os.path.join(dir_path, "token.json")
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        # If there are no (valid) credentials available, let the user log in.
        if creds.expired and creds.refresh_token:
            print("WARNING: Your Credentials are expired or invalid. Please Login again.")
            try:
                creds.refresh(Request())
            except TransportError:
                print("No internet connection")
                return

        # create drive api client
        SERVICE = build("drive", "v3", credentials=creds)
    else:
        print("WARNING: Please run share_gdrive.py to generate a token.json from your credentials.json if you want to use the share function")

def upload_image(image_path):
    # https://developers.google.com/drive/api/guides/manage-uploads#multipart
    file_metadata = {"name": image_path}
    media = MediaFileUpload(image_path, mimetype="image/jpeg")
    file = (
        SERVICE.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )
    return file.get("id")

def share_image(file_id):
    SERVICE.permissions().create(body={"role":"reader", "type":"anyone"}, fileId=file_id).execute()
    link = f"https://drive.google.com/file/d/{file_id}"
    return link

def delete_image(file_id):
    # deletion of shared images is done manually after the event
    pass


if __name__ == "__main__":
    get_token()