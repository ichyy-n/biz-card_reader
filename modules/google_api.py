import os.path
import json
import base64
import hmac
import hashlib
import secrets
import time
import logging

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from gspread.client import Client
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet
from modules.database import User, OAuthNonce

load_dotenv()
key = os.getenv('CRYPT_KEY')

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",    # アプリが作成したファイルのみ（提案5: 最小権限化）
    "https://www.googleapis.com/auth/spreadsheets",  # スプレッドシート操作
]
# Migration only. Will be deprecated.
folder_ID = os.getenv('FOLDER_ID')
sheet_id = os.getenv('SHEET_ID')
#Client Secretを辞書型として読み込み
client_secret = os.getenv('CLIENT_SECRET_PATH')


#Google OAuth認証 token.jsonがない場合にGoogle認証用urlを生成
def create_authurl(request, user_id, db: Session):
   flow = Flow.from_client_secrets_file(
          client_secret, SCOPES
      )
   flow.redirect_uri = request.url_for('oauth2callback')
   state_payload = create_oauth_state(user_id, db)
   authorization_url, _ = flow.authorization_url(
      access_type='offline',
      include_granted_scopes='true',
      state=state_payload,
   )
   return authorization_url


def create_oauth_state(user_id: str, db: Session) -> str:
    nonce = secrets.token_hex(16)
    payload = json.dumps({
        "user_id": user_id,
        "nonce": nonce,
        "exp": int(time.time()) + 600,
    })
    secret = os.getenv("SESSION_SECRET_KEY", "").encode()
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    state_data = base64.urlsafe_b64encode(
        f"{payload}:{sig}".encode()
    ).decode()
    db.add(OAuthNonce(nonce=nonce))
    db.commit()
    return state_data

#Google OAuth認証情報読み込み
def create_creds(token, db: Session, user_id: str):
  # The file token.json stores the user's access and refresh tokens, and is
  # created automatically when the authorization flow completes for the first
  # time.
  creds = Credentials.from_authorized_user_info(json.loads(token), SCOPES)

  # If there are no (valid) credentials available, let the user log in.
  if not creds.valid and creds.expired and creds.refresh_token:
    creds.refresh(Request())
    token = creds.to_json()
    user = db.query(User).filter(User.line_user_id == user_id).first()  # 提案6: user_idで検索
    user.token = Fernet(key).encrypt(token.encode()).decode()
    db.commit()  # トークン更新を永続化（提案1: CRITICAL bugfix）
    logger.info(f"Token refreshed for user_id={user_id}")

  return creds


#per-userのGoogle Driveフォルダを自動作成
def create_drive_folder(creds, line_user_id):
  service = build("drive", "v3", credentials=creds)
  file_metadata = {
      "name": f"BizCard - {line_user_id}",
      "mimeType": "application/vnd.google-apps.folder",
  }
  folder = service.files().create(body=file_metadata, fields="id").execute()
  folder_id = folder.get("id")
  logger.info(f"Created Drive folder for user={line_user_id}: {folder_id}")
  return folder_id


#per-userのGoogle Spreadsheetを自動作成
def create_spreadsheet(creds, line_user_id):
  service = build("sheets", "v4", credentials=creds)
  spreadsheet_body = {
      "properties": {"title": f"名刺リスト - {line_user_id}"},
  }
  spreadsheet = service.spreadsheets().create(body=spreadsheet_body, fields="spreadsheetId").execute()
  ss_id = spreadsheet.get("spreadsheetId")
  logger.info(f"Created Spreadsheet for user={line_user_id}: {ss_id}")
  return ss_id


#画像をGoogle Driveへアップロード
def drive_upload(image, message_id, creds, user_folder_id):
  try:
    service = build("drive", "v3", credentials=creds)
    file_metadata = {
      "name": f"{message_id}.jpeg",
      "parents": [user_folder_id]
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
    logger.error(f"Drive upload failed for message_id={message_id}: {error}", exc_info=True)
    raise RuntimeError(f"Drive upload failed: {error}") from error

#Googleスプレッドシートへの登録
def sheets_update(dict, file_id, creds, user_sheet_id):
  #gspreadによる操作
  gc = Client(auth=creds)
  sh = gc.open_by_key(user_sheet_id)
  ws = sh.get_worksheet(0)
  append_list = []

  #読み取った情報をリスト型として保存
  for i in dict.keys():
    append_list.append(dict[i])

  #名刺画像ファイルへのリンクを追加
  append_list.append(f"https://drive.google.com/file/d/{file_id}")
  #最終行へリスト情報を追加
  ws.append_row(append_list)



