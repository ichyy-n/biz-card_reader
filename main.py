import os

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

#alg = 'vdu'
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key= os.urandom(24))
# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/drive"]
client_secret = os.getenv('CLIENT_SECRET_FILE')

@app.post("/callback")
async def handle_callback(request: Request):
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body = await request.body()
    body = body.decode()
    events = get_line_events(body, signature)
    global user_id
    user_id = get_user_id(events)
    push_message(user_id, f'{request.url_for('oauth2callback')}')
    #tokenがないならGoogle認証用urlを送信
    if not os.path.exists("webtoken.json"):
       auth_url = create_authurl(request)
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
    push_message(user_id, f'{type(authorization_response)}')
    flow.fetch_token(authorization_response=authorization_response)
    creds = flow.credentials
    push_message(user_id, 'a')
    # Save the credentials for the next run
    with open("webtoken.json", "w") as token:
      token.write(creds.to_json())
    
    return push_message(user_id, '連携が完了しました。画像を再送してください')


    








