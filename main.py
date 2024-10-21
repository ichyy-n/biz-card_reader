import os, json

from dotenv import load_dotenv
from fastapi import Request, FastAPI
from starlette.middleware.sessions import SessionMiddleware
from google_auth_oauthlib.flow import Flow

from modules.line_api import(
    push_message,
    get_line_events,
    get_user_id,
    event_handler,
)
from modules.gpt_api import read_image
from modules.google_api import( 
    create_authurl
)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key= os.urandom(24))

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/drive"]
#Client Secretを辞書型として読み込み
client_secret = os.getenv('CLIENT_SECRET_PATH')

@app.post("/callback")
async def handle_callback(request: Request):
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body = await request.body()
    body = body.decode()
    events = get_line_events(body, signature)
    
    global user_id
    user_id = get_user_id(events)
    print(json.loads(os.getenv('TOKEN')))
    #tokenがないならGoogle認証用urlを送信
    if not os.getenv('TOKEN'):
        auth_url = create_authurl(request, client_secret)
        return push_message(user_id, f'以下のURLにアクセスしてGoogleアカウントの連携を行ってください:\n{auth_url}')
    
    event_handler(events)

    return 'OK'

@app.get("/oauth2callback")
def oauth2callback(request: Request):
    state = request.session.get('state')
    flow = Flow.from_client_secrets_file(
      client_secret, scopes=SCOPES, state=state)
    flow.redirect_uri = request.url_for('oauth2callback')
    authorization_response = str(request.url)

    flow.fetch_token(authorization_response=authorization_response)
    creds = flow.credentials
    
    # Save the credentials for the next run
    os.environ['TOKEN'] = creds.to_json()

    # with open('./token.json', 'w') as token:
    #     token.write(creds.to_json())

    return push_message(user_id, '連携が完了しました。画像を再送してください')

@app.get("/")
def root():
    return "hello"
    









