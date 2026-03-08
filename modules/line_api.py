import os
import sys
import io
import json
import logging

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)
from fastapi import HTTPException
from linebot.v3 import WebhookHandler, WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import (
    ImageMessageContent,
    TextMessageContent,
    MessageEvent
)
from linebot.v3.messaging import (
    ApiClient,
    MessagingApi, 
    MessagingApiBlob,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
    PushMessageRequest
)

from modules.gpt_api import read_image
from modules.google_api import(
    create_creds,
    create_drive_folder,
    create_spreadsheet,
    drive_upload,
    sheets_update
)
from modules.database import User


load_dotenv()

#チャネルシークレットとアクセストークンの取得
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
if channel_secret is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if channel_access_token is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

configuration = Configuration(
    access_token=channel_access_token
)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)
line_bot_api_blob = MessagingApiBlob(api_client)
handler = WebhookHandler(channel_secret)
parser = WebhookParser(channel_secret)


def get_line_events(body, signature):
    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Line Invalid signature")  
    return events


def handle_single_event(event, token, db, user_id: str):
    """Process a single webhook event with the user's own context."""
    if not isinstance(event, MessageEvent):
        return
    if isinstance(event.message, TextMessageContent):
        reply_message(event.reply_token, '名刺画像を送信してください')
    if isinstance(event.message, ImageMessageContent):
        image_handler(event, token, db, user_id)


MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB（提案9: 画像サイズ制限）

#画像受信時の処理
def image_handler(event, token, db, user_id: str):
    message_id = event.message.id
    creds = create_creds(token, db, user_id)

    # per-userリソースの自動作成（R02: データ分離）
    user = db.query(User).filter(User.line_user_id == user_id).first()
    if user.drive_folder_id is None:
        try:
            user.drive_folder_id = create_drive_folder(creds, user_id)
            db.commit()
        except Exception as e:
            logger.error(f'Google Driveフォルダの作成に失敗: {e}', exc_info=True)
            return push_message(user_id, 'Google Driveフォルダの作成に失敗しました。再度お試しください。')
    if user.spreadsheet_id is None:
        try:
            user.spreadsheet_id = create_spreadsheet(creds, user_id)
            db.commit()
        except Exception as e:
            logger.error(f'スプレッドシートの作成に失敗: {e}', exc_info=True)
            return push_message(user_id, 'スプレッドシートの作成に失敗しました。再度お試しください。')

    reply_message(event.reply_token, '画像を受け付けました')

    #画像データの取得（バイナリデータ）
    try:
        image_content = line_bot_api_blob.get_message_content(message_id)
    except Exception as e:
        logger.error(f'画像の取得に失敗: {e}', exc_info=True)
        return push_message(user_id, '画像を取得できませんでした。再度お試しください。')

    # サイズ制限チェック（提案9）
    if len(image_content) > MAX_IMAGE_SIZE:
        return push_message(user_id, f'画像サイズが大きすぎます（上限5MB）')
    #gpt4による文字読み取りと構造化
    try:
        bizcard_text = json.loads(read_image(image_content)) #文字列から辞書型に変換
    except Exception as e:
        logger.error(f'文字の構造化に失敗: {e}', exc_info=True)
        return push_message(user_id, '文字の構造化に失敗しました。再度お試しください。')
    #画像をGoogle Driveへアップロード
    try:
        file_id = drive_upload(io.BytesIO(image_content), message_id, creds, user.drive_folder_id)
    except Exception as e:
        logger.error(f'画像のGoogle Drive保存に失敗: {e}', exc_info=True)
        return push_message(user_id, '画像をGoogle Driveに保存できませんでした。再度お試しください。')
    #読み取った文字データとGoogle Driveの画像リンクをスプレッドシートへ登録
    try:
        sheets_update(bizcard_text, file_id, creds, user.spreadsheet_id)
        push_message(user_id, 'データの登録が終了しました')
    except Exception as e:
        logger.error(f'Google Spreadsheetの更新に失敗: {e}', exc_info=True)
        return push_message(user_id, 'Google Spreadsheetの更新に失敗しました。再度お試しください。')



#来たメッセージに対する返信
def reply_message(reply_token, message):
    line_bot_api.reply_message(
        ReplyMessageRequest(
            replyToken=reply_token,
            messages=[TextMessage(text=message)]
        )
    )

#メッセージ送信
def push_message(user_id, message):
    line_bot_api.push_message(
        PushMessageRequest(
            to=user_id,
            messages=[TextMessage(text=message)]
        )
    )