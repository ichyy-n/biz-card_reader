import os
import json
import base64
import logging
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["会社名", "部署名", "氏名"]

def read_image(image_content):
    base64_image = base64.b64encode(image_content).decode('utf-8') # 画像をbase64にエンコード
    client = OpenAI(timeout=30.0)  # 30秒タイムアウト設定
    schema = {
        "会社名": "string",
        "部署名": "string",
        "氏名": "string",
        "会社住所": "string | null",
        "電話番号": "string | null",
        "e-mailアドレス": "string | null",
    }

    #gpt-4へのリクエスト
    response = client.chat.completions.create(
        model = 'gpt-5.2',
        response_format={ "type": "json_object" },
        messages=[
            {'role': 'user',
            'content': [
                {'type': 'text', 'text': f'次の画像から文字を読み取り、{schema}に従って構造化し、JSON形式で出力してください。'},
                {'type': 'image_url', 'image_url':{
                    'url': f"data:image/jpeg;base64,{base64_image}"
                    },
                },
                ]
            },
        ],
    )

    raw_content = response.choices[0].message.content  #json型(文字列)

    # 名刺データとして有効か検証
    try:
        parsed = json.loads(raw_content)
    except (json.JSONDecodeError, TypeError):
        logger.warning("GPTレスポンスのJSONパースに失敗")
        return None

    # 必須フィールド（会社名・部署名・氏名）が全て空なら名刺以外と判断
    if all(not parsed.get(field) for field in REQUIRED_FIELDS):
        logger.info("名刺以外の画像と判断: 必須フィールドが全て空")
        return None

    return raw_content

