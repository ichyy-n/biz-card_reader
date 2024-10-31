import os

from fastapi import Request, FastAPI, Depends
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from google_auth_oauthlib.flow import Flow

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


app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key= os.urandom(24))

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
    
    global user_id
    user_id = get_user_id(events)
    
    token = db.get(User, 1).token
    #tokenがないならGoogle認証用urlを送信
    if token is None:
        auth_url = create_authurl(request)
        return push_message(user_id, f'以下のURLにアクセスしてGoogleアカウントの連携を行ってください:\n{auth_url}')
    
    event_handler(events, token)

    return 'OK'

@app.get("/oauth2callback")
def oauth2callback(request: Request, db: Session = Depends(get_db)):
    state = request.session.get('state')
    flow = Flow.from_client_secrets_file(
      client_secret, scopes=SCOPES, state=state)
    flow.redirect_uri = request.url_for('oauth2callback')
    authorization_response = str(request.url)

    flow.fetch_token(authorization_response=authorization_response)
    creds = flow.credentials
    
    # Save the credentials for the next run
    new_user = User(id=1, token=creds.to_json())
    db.add(new_user)
    db.commit()
    # with open('./token.json', 'w') as token:
    #     token.write(creds.to_json())

    return push_message(user_id, '連携が完了しました。画像を再送してください')


    









