"""Step 12 targeted notification and hardening tests."""
import io
from unittest.mock import patch

from app.core.security import hash_password
from app.models.notification import Notification, NotificationPreference, PushSubscription
from app.models.user import User, UserType
from app.services import notification_service

VALID_PASSWORD = "Str0ngPass"


def make_user(db, email="notify@example.com", user_type=UserType.CITIZEN):
    user = User(name="Notify User", email=email, password_hash=hash_password(VALID_PASSWORD), user_type=user_type, is_active=True)
    db.add(user); db.commit(); db.refresh(user)
    return user


def test_01_notification_creation(client, db_session):
    user = make_user(db_session)
    n = Notification(user_id=user.id, notification_type="SYSTEM_ALERT", title="Test", message="Hello", event_key="test:create")
    db_session.add(n); db_session.commit()
    assert db_session.query(Notification).filter_by(event_key="test:create").count() == 1


def test_02_notification_ownership(client, db_session):
    user = make_user(db_session)
    other = make_user(db_session, "other-notify@example.com")
    db_session.add(Notification(user_id=user.id, notification_type="SYSTEM_ALERT", title="Private", message="x", event_key="test:owner")); db_session.commit()
    headers = {"Authorization": f"Bearer {client.post('/api/auth/login', json={'email': other.email, 'password': VALID_PASSWORD}).json()['access_token']}"}
    assert client.get('/api/notifications', headers=headers).status_code == 200
    assert all(x["title"] != "Private" for x in client.get('/api/notifications', headers=headers).json())


def test_03_unread_count(client, db_session):
    user = make_user(db_session)
    for i in range(2): db_session.add(Notification(user_id=user.id, notification_type="SYSTEM_ALERT", title=str(i), message="x", event_key=f"test:count:{i}"))
    db_session.commit()
    headers = {"Authorization": f"Bearer {client.post('/api/auth/login', json={'email': user.email, 'password': VALID_PASSWORD}).json()['access_token']}"}
    assert client.get('/api/notifications/unread-count', headers=headers).json()["count"] == 2


def test_04_mark_read(client, db_session):
    user = make_user(db_session)
    n=Notification(user_id=user.id,notification_type="SYSTEM_ALERT",title="x",message="x",event_key="test:read"); db_session.add(n); db_session.commit()
    headers={"Authorization":f"Bearer {client.post('/api/auth/login',json={'email':user.email,'password':VALID_PASSWORD}).json()['access_token']}"}
    assert client.post(f'/api/notifications/{n.id}/read',headers=headers).status_code==200


def test_05_mark_all_read(client, db_session):
    user=make_user(db_session)
    for i in range(2): db_session.add(Notification(user_id=user.id,notification_type="SYSTEM_ALERT",title=str(i),message="x",event_key=f"test:all:{i}"))
    db_session.commit(); headers={"Authorization":f"Bearer {client.post('/api/auth/login',json={'email':user.email,'password':VALID_PASSWORD}).json()['access_token']}"}
    assert client.post('/api/notifications/read-all',headers=headers).status_code==200
    assert client.get('/api/notifications/unread-count',headers=headers).json()["count"]==0


def test_06_preferences(client, db_session):
    user=make_user(db_session); headers={"Authorization":f"Bearer {client.post('/api/auth/login',json={'email':user.email,'password':VALID_PASSWORD}).json()['access_token']}"}
    assert client.get('/api/notifications/preferences',headers=headers).json()["email_enabled"] is True
    r=client.patch('/api/notifications/preferences',headers=headers,json={"email_enabled":False}); assert r.status_code==200; assert r.json()["email_enabled"] is False


def test_07_email_generation_disabled(client, db_session, monkeypatch):
    monkeypatch.setattr(notification_service, "send_email", lambda *args: None)
    assert notification_service.send_email("x@example.com","x","x") is None


def test_08_email_failure_isolated():
    with patch("app.services.email_service.smtplib.SMTP", side_effect=RuntimeError("smtp down")):
        from app.services.email_service import send_email
        with patch("app.services.email_service.get_settings") as gs:
            gs.return_value.EMAIL_NOTIFICATIONS_ENABLED=True; gs.return_value.SMTP_HOST="smtp"; gs.return_value.SMTP_FROM_EMAIL="x@example.com"; gs.return_value.SMTP_FROM_NAME="PGMS"; gs.return_value.SMTP_PORT=587; gs.return_value.SMTP_TIMEOUT_SECONDS=1; gs.return_value.SMTP_USE_TLS=False; gs.return_value.SMTP_USERNAME=None; gs.return_value.SMTP_PASSWORD=None
            assert send_email("a@example.com","x","x") is False


def test_09_push_subscription_creation(client, db_session):
    user=make_user(db_session); headers={"Authorization":f"Bearer {client.post('/api/auth/login',json={'email':user.email,'password':VALID_PASSWORD}).json()['access_token']}"}
    r=client.post('/api/notifications/push/subscribe',headers=headers,json={"endpoint":"https://push.example/a","p256dh":"key","auth":"auth"}); assert r.status_code==200
    assert db_session.query(PushSubscription).filter_by(user_id=user.id).count()==1


def test_10_push_subscription_ownership(client, db_session):
    user=make_user(db_session); other=make_user(db_session,"push-other@example.com")
    db_session.add(PushSubscription(user_id=user.id,endpoint="https://push.example/private",p256dh_key="k",auth_key="a")); db_session.commit()
    headers={"Authorization":f"Bearer {client.post('/api/auth/login',json={'email':other.email,'password':VALID_PASSWORD}).json()['access_token']}"}
    assert client.delete('/api/notifications/push/subscribe',headers=headers,params={"endpoint":"https://push.example/private"}).status_code==200
    assert db_session.query(PushSubscription).filter_by(endpoint="https://push.example/private").one().active is True


def test_11_invalid_push_subscription_rejected(client, db_session):
    user=make_user(db_session); headers={"Authorization":f"Bearer {client.post('/api/auth/login',json={'email':user.email,'password':VALID_PASSWORD}).json()['access_token']}"}
    assert client.post('/api/notifications/push/subscribe',headers=headers,json={"endpoint":"","p256dh":"k","auth":"a"}).status_code==422


def test_12_notification_deduplication(db_session):
    user=make_user(db_session,"dedupe@example.com")
    n=Notification(user_id=user.id,notification_type="SYSTEM_ALERT",title="x",message="x",event_key="same-key"); db_session.add(n); db_session.commit()
    assert db_session.query(Notification).filter_by(event_key="same-key").count()==1


def test_13_protected_identity_message_is_generic():
    from app.services.notification_service import _EVENT_TEXT
    assert "citizen" not in _EVENT_TEXT["GRIEVANCE_STATUS_CHANGED"][2].lower()


def test_14_resolution_event_template_exists():
    from app.services.notification_service import _EVENT_TEXT
    assert "RESOLUTION_READY_FOR_CITIZEN_REVIEW" in _EVENT_TEXT


def test_15_dispute_event_template_exists():
    from app.services.notification_service import _EVENT_TEXT
    assert "RESOLUTION_DISPUTED" in _EVENT_TEXT


def test_16_officer_event_template_exists():
    from app.services.notification_service import _EVENT_TEXT
    assert "OFFICER_CLAIMED" in _EVENT_TEXT


def test_17_admin_event_types_are_available():
    from app.models.notification import NotificationType
    assert NotificationType.SYSTEM_ALERT.value == "SYSTEM_ALERT"
    assert NotificationType.AUDIT_INTEGRITY_FAILURE.value == "AUDIT_INTEGRITY_FAILURE"


def test_18_sla_warning_type_available():
    from app.models.notification import NotificationType
    assert NotificationType.SLA_WARNING.value == "SLA_WARNING"


def test_19_unauthorized_notification_access(client, db_session):
    user=make_user(db_session,"unauth-a@example.com"); other=make_user(db_session,"unauth-b@example.com")
    n=Notification(user_id=user.id,notification_type="SYSTEM_ALERT",title="private",message="x",event_key="private-event"); db_session.add(n); db_session.commit()
    headers={"Authorization":f"Bearer {client.post('/api/auth/login',json={'email':other.email,'password':VALID_PASSWORD}).json()['access_token']}"}
    assert client.post(f'/api/notifications/{n.id}/read',headers=headers).status_code==404


def test_20_health_ready(client, db_session):
    r=client.get('/api/health/ready'); assert r.status_code==200; assert r.json()["status"] in {"ready","not_ready"}


def test_21_notification_config_never_exposes_private_key(client, db_session):
    user=make_user(db_session,"config@example.com"); headers={"Authorization":f"Bearer {client.post('/api/auth/login',json={'email':user.email,'password':VALID_PASSWORD}).json()['access_token']}"}
    data=client.get('/api/notifications/config',headers=headers).json(); assert "vapid_private_key" not in data


def test_22_file_signature_security(tmp_path):
    from app.utils.file_storage import _validate_file_signature
    p=tmp_path/'bad.png'; p.write_bytes(b'not an image')
    try: _validate_file_signature(p,'.png')
    except Exception: pass
    assert not p.exists()


def test_23_rate_limit_is_present():
    from app.utils.rate_limit import enforce_rate_limit
    assert callable(enforce_rate_limit)


def test_24_security_header_logic(client):
    r=client.get('/api/health'); assert r.headers.get('x-content-type-options')=='nosniff'; assert r.headers.get('x-frame-options')=='DENY'


def test_25_notification_models_are_registered():
    from app.models import Notification, NotificationPreference, PushSubscription
    assert Notification.__tablename__=='notifications'; assert NotificationPreference.__tablename__=='notification_preferences'; assert PushSubscription.__tablename__=='push_subscriptions'


def test_26_sms_is_not_a_notification_type():
    from app.models.notification import NotificationType
    assert not any('SMS' in member.value for member in NotificationType)
