import os
import base64
import json
import hmac
import hashlib
import time
import logging
from contextlib import asynccontextmanager

from fastapi import Request, FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)
from sqlalchemy import inspect as sa_inspect, text
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
from modules.database import Base, User, OAuthNonce, engine, sessionLocal

#環境変数読み込み
load_dotenv()
key = os.getenv('CRYPT_KEY')


@asynccontextmanager
async def lifespan(app: FastAPI):
    #DB起動時処理: テーブル存在確認 + カラム追加マイグレーション（冪等）
    inspector = sa_inspect(engine)
    if not inspector.has_table('users'):
        Base.metadata.create_all(bind=engine)
        logger.info("DBスキーマ初期化完了: テーブル新規作成")
    else:
        if not inspector.has_table('oauth_nonces'):
            OAuthNonce.__table__.create(bind=engine)
            logger.info("DBスキーマ更新: oauth_noncesテーブル作成")
        columns = [col['name'] for col in inspector.get_columns('users')]
        added = []
        if 'drive_folder_id' not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN drive_folder_id VARCHAR"))
            added.append('drive_folder_id')
        if 'spreadsheet_id' not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN spreadsheet_id VARCHAR"))
            added.append('spreadsheet_id')
        if added:
            logger.info(f"DBマイグレーション完了: カラム追加 {added}")
        else:
            logger.info("DBスキーマ確認完了: 変更なし")

    # R02マイグレーション: 既存ユーザーにデフォルトのfolder_id/sheet_idを設定
    # Migration only. Will be deprecated.
    migration_folder_id = os.getenv('FOLDER_ID')
    migration_sheet_id = os.getenv('SHEET_ID')
    if migration_folder_id or migration_sheet_id:
        db = sessionLocal()
        try:
            updated = 0
            if migration_folder_id:
                result = db.execute(
                    text("UPDATE users SET drive_folder_id = :fid WHERE drive_folder_id IS NULL"),
                    {"fid": migration_folder_id}
                )
                updated += result.rowcount
            if migration_sheet_id:
                result = db.execute(
                    text("UPDATE users SET spreadsheet_id = :sid WHERE spreadsheet_id IS NULL"),
                    {"sid": migration_sheet_id}
                )
                updated += result.rowcount
            if updated > 0:
                db.commit()
                logger.info(f"R02マイグレーション完了: {updated}件更新")
            else:
                logger.info("R02マイグレーション: 対象レコードなし")
        finally:
            db.close()

    yield


app = FastAPI(lifespan=lifespan)
session_secret = os.getenv('SESSION_SECRET_KEY')
if not session_secret:
    raise RuntimeError("SESSION_SECRET_KEY environment variable not set")
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    https_only=True,
    same_site="lax",
)

def get_db():
    db = sessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/callback")
async def handle_callback(request: Request, db: Session = Depends(get_db)):
    signature = request.headers.get('X-Line-Signature')
    if not signature:
        return JSONResponse({"error": "Missing signature"}, status_code=400)
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
        auth_url = create_authurl(request, user_id, db)  # pass user_id to embed in OAuth state
        return push_message(user_id, f'以下のURLにアクセスしてGoogleアカウントの連携を行ってください:\n{auth_url}')
    else:
        user = db.get(User, user_id)
        token = Fernet(key).decrypt(user.token.encode()).decode()
        event_handler(events, token, db, user_id)

    return 'OK'


def verify_oauth_state(state_param: str, db: Session) -> str:
    try:
        decoded = base64.urlsafe_b64decode(state_param + '==').decode()
        payload_str, sig = decoded.rsplit(":", 1)
        secret = os.getenv("SESSION_SECRET_KEY", "").encode()
        expected_sig = hmac.new(secret, payload_str.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            raise HTTPException(status_code=400, detail="Invalid state signature")
        payload = json.loads(payload_str)
        if time.time() > payload["exp"]:
            raise HTTPException(status_code=400, detail="State expired")
        nonce_record = db.query(OAuthNonce).filter_by(nonce=payload["nonce"]).first()
        if not nonce_record:
            raise HTTPException(status_code=400, detail="Invalid nonce")
        db.delete(nonce_record)
        db.commit()
        return payload["user_id"]
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid state")


@app.get("/oauth2callback")
def oauth2callback(request: Request, db: Session = Depends(get_db)):
    state_param = request.query_params.get('state', '')
    try:
        user_id = verify_oauth_state(state_param, db)
    except HTTPException as e:
        logger.error(f"OAuth state verification failed: {e.detail}")
        return JSONResponse(
            {"error": "認証セッションが無効です。LINEから再度お試しください。"},
            status_code=400,
        )

    flow = Flow.from_client_secrets_file(client_secret, scopes=SCOPES)
    flow.redirect_uri = request.url_for('oauth2callback')
    authorization_response = str(request.url)

    flow.fetch_token(authorization_response=authorization_response)
    creds = flow.credentials
    token = creds.to_json()

    # Upsert: update token if user already exists, create otherwise
    user = db.query(User).filter(User.line_user_id == user_id).first()
    if not user:
        user = User(line_user_id=user_id, token=Fernet(key).encrypt(token.encode()).decode())
        db.add(user)
    else:
        user.token = Fernet(key).encrypt(token.encode()).decode()
    db.commit()

    return push_message(user_id, '連携が完了しました。画像を再送してください')


@app.get("/")
def root():
    return 'OK'   









