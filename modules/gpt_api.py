import os
import base64
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

def read_image(image_content):
    base64_image = base64.b64encode(image_content).decode('utf-8') # 画像をbase64にエンコード
    client = OpenAI()  # OPENAI_API_KEY 環境変数を自動読み込み（提案7: 環境変数名標準化）
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

    return response.choices[0].message.content  #json型(文字列)

