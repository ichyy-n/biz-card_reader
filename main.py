import os
import logging

from fastapi import Request, FastAPI, Depends

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from google_auth_oauthlib.flow import Flow
from cryptography.fernet import Fernet
from dotenv import load_dotenv

from modules.line_api import(
    push_message,
    get_line_events,
    get_user_id,
    event_handler,
)
from modules.google_api import( 
    create_authurl,
    SCOPES,
    client_secret
)
from modules.database import Base, User, engine, sessionLocal

#環境変数読み込み
load_dotenv()
key = os.getenv('CRYPT_KEY')

app = FastAPI()
session_secret = os.getenv('SESSION_SECRET_KEY')
if not session_secret:
    raise RuntimeError("SESSION_SECRET_KEY environment variable not set")
app.add_middleware(SessionMiddleware, secret_key=session_secret)

#DB関連処理
Base.metadata.create_all(engine)

def get_db():
    db = sessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/callback")
async def handle_callback(request: Request, db: Session = Depends(get_db)):
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body = await request.body()
    body = body.decode()
    events = get_line_events(body, signature)

    user_id = get_user_id(events)  # ローカル変数として保持（提案2: global排除）

    ALLOWED_USERS = os.getenv("ALLOWED_LINE_USERS", "").split(",")
    if user_id not in ALLOWED_USERS:
        return 'OK'

    #tokenがないならGoogle認証用urlを送信
    if db.get(User, user_id) is None:
        auth_url = create_authurl(request)
        request.session['pending_user_id'] = user_id  # セッションに保存
        return push_message(user_id, f'以下のURLにアクセスしてGoogleアカウントの連携を行ってください:\n{auth_url}')
    else:
        user = db.get(User, user_id)
        token = Fernet(key).decrypt(user.token.encode()).decode()
        event_handler(events, token, db, user_id)

    return 'OK'


@app.get("/oauth2callback")
def oauth2callback(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get('pending_user_id')  # セッションから取得（提案2）
    state = request.session.get('state')
    flow = Flow.from_client_secrets_file(
      client_secret, scopes=SCOPES, state=state)
    flow.redirect_uri = request.url_for('oauth2callback')
    authorization_response = str(request.url)

    flow.fetch_token(authorization_response=authorization_response)
    creds = flow.credentials
    token = creds.to_json()

    # Save the credentials for the next run
    new_user = User(line_user_id=user_id, token=Fernet(key).encrypt(token.encode()).decode())
    db.add(new_user)
    db.commit()

    return push_message(user_id, '連携が完了しました。画像を再送してください')


@app.get("/")
def root():
    return 'OK'   









