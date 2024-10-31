import os
import sys
import io
import json

from dotenv import load_dotenv
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
    drive_upload, 
    sheets_update
)


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


def get_user_id(events):
       for event in events:
        if isinstance(event, MessageEvent):
            return event.source.user_id


def event_handler(events, token):
    for event in events:
        if not isinstance(event, MessageEvent):
            continue
        if isinstance(event.message, TextMessageContent):
            reply_message(event.reply_token, '名刺画像を送信してください')
        if isinstance(event.message, ImageMessageContent):
            image_handler(event, token)

#画像受信時の処理
def image_handler(event, token):
    message_id = event.message.id
    user_id = event.source.user_id
    creds = create_creds(token)

    reply_message(event.reply_token, '画像を受け付けました')
    
    #画像データの取得（バイナリデータ）
    try:    
        image_content = line_bot_api_blob.get_message_content(message_id)
    except Exception as e:
        return push_message(user_id, f'画像を取得できませんでした：{e}')
    #gpt4による文字読み取りと構造化
    try:
        bizcard_text = json.loads(read_image(image_content)) #文字列から辞書型に変換
    except Exception as e:
        return push_message(user_id, f'文字の構造化に失敗しました：{e}')
    #画像をGoogle Driveへアップロード
    try:
        file_id = drive_upload(io.BytesIO(image_content),message_id,creds) #バイナリデータをメモリ上でファイルとして扱う
    except Exception as e:
        return push_message(user_id, f'画像をGoogle Driveに保存できませんでした：{e}')
    #読み取った文字データとGoogle Driveの画像リンクをスプレッドシートへ登録
    try:
        sheets_update(bizcard_text, file_id, creds)
        push_message(user_id, 'データの登録が終了しました')
    except Exception as e:
        return push_message(user_id, f'Google spread sheetの更新に失敗しました：{e}')



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