import os.path
from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from gspread.client import Client

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/drive"]
client_secret = os.getenv('CLIENT_SECRET_FILE')
webtoken = os.getenv('TOKEN')
folder_ID = os.getenv('FOLDER_ID')
sheet_id = os.getenv('SHEET_ID')

#Google OAuth認証 token.jsonがない場合にGoogle認証用urlを生成
def create_authurl(request):
   flow = Flow.from_client_secrets_file(
          client_secret, SCOPES
      )
   flow.redirect_uri = request.url_for('oauth2callback')
   authorization_url, state = flow.authorization_url(
      access_type= 'offline',
    include_granted_scopes= 'true'
    )
   request.session['state'] = state
   return authorization_url

#Google OAuth認証情報読み込み
def create_creds():
  # The file token.json stores the user's access and refresh tokens, and is
  # created automatically when the authorization flow completes for the first
  # time.
  creds = Credentials.from_authorized_user_file(webtoken, SCOPES)
  # If there are no (valid) credentials available, let the user log in.
  if not creds.valid and creds.expired and creds.refresh_token:
    creds.refresh(Request())
    
  return creds


#画像をGoogle Driveへアップロード
def drive_upload(image, message_id, creds):
  try:
    service = build("drive", "v3", credentials=creds)
    file_metadata = {
      "name": f"{message_id}.jpeg",
      "parents": [folder_ID]
      }
    
    media = MediaIoBaseUpload(image, mimetype="image/jpeg") #BytesIo型を扱う
    file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )
    file_id = file.get("id")

    return file_id
  
  except HttpError as error:
    print(f"An error occurred: {error}")
    file = None
    message = 'failed'

#Googleスプレッドシートへの登録
def sheets_update(dict, file_id, creds):
  #gspreadによる操作
  gc = Client(auth=creds)
  sh = gc.open_by_key(sheet_id)
  ws = sh.get_worksheet(0)
  append_list = []
  
  #読み取った情報をリスト型として保存
  for i in dict.keys():
    append_list.append(dict[i])
  
  #名刺画像ファイルへのリンクを追加
  append_list.append(f"https://drive.google.com/file/d/{file_id}")
  #最終行へリスト情報を追加
  ws.append_row(append_list)



