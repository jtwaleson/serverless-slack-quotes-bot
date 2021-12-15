import base64
import boto3
import hashlib
import hmac
import os
import requests
import time

try:
    SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
except KeyError:
    raise Exception(
        "Set SLACK_SIGNING_SECRET as an environment variable. "
        "You can find this on the Slack 'App Settings' under "
        "'Signing Secret'."
    )

try:
    BEARER_TOKEN = os.environ["SLACK_BEARER_TOKEN"]
except KeyError:
    raise Exception(
        "Set SLACK_BEARER_TOKEN as an environment variable. "
        "You can find this on the Slack 'App Settings' under "
        "'OAuth Tokens for Your Workspace'."
    )


DATABASE_INDEX_NAME = "team-timestamp-index"
DATABASE_TABLE = "quotes"

SLACK_CALLBACK_HANDLERS = {
    "command": {},
    "block_actions": {},
    "view_submission": {},
    #    "view_closed": {},
    #    "shortcut": {},
    #    "message_actions": {},
}


db_table = boto3.resource("dynamodb").Table(DATABASE_TABLE)


def _slack_callback_handler(callback_type, command):
    global SLACK_CALLBACK_HANDLERS
    if command in SLACK_CALLBACK_HANDLERS[callback_type]:
        raise Exception(f"{callback_type} {command} is already registered")

    def wrapper(handler):
        SLACK_CALLBACK_HANDLERS[callback_type][command] = handler
        return handler

    return wrapper


def slack_command(command):
    return _slack_callback_handler("command", command)


def slack_block_action(action):
    return _slack_callback_handler("block_actions", action)


def slack_view_submission(action):
    return _slack_callback_handler("view_submission", action)


def extract_key_from_payload(callback_type, data):
    if callback_type == "block_actions":
        if "actions" not in data:
            raise Exception("data does not contain actions, help!")
        if len(data["actions"]) > 1:
            raise Exception("I can not yet handle more than one action per response")

        return data["actions"][0]["action_id"]
    elif callback_type == "view_submission":
        return data["view"]["callback_id"]
    raise Exception("Key could not be extracted")


def validate_signature(event):
    print("validating signature")

    # 1 - get data from request
    request_timestamp = event["headers"]["x-slack-request-timestamp"]
    provided_signature = event["headers"]["x-slack-signature"]
    body = base64.b64decode(event["body"])

    # 2 - validate timestamp
    if abs(time.time() - int(request_timestamp)) > 60 * 5:
        raise Exception(
            "Message timestamp is stale, something is wrong. "
            "Are you replaying an old request?"
        )

    # 3 - create signature
    sig_basestring = str.encode("v0:" + request_timestamp + ":") + body

    calculated_signature = (
        "v0="
        + hmac.new(
            str.encode(SLACK_SIGNING_SECRET),
            msg=sig_basestring,
            digestmod=hashlib.sha256,
        ).hexdigest()
    )

    # 4 - ensure calculated signature matches provided signature
    if not hmac.compare_digest(calculated_signature, provided_signature):
        raise Exception("Signature does not match, will not execute request")


def send_message(channel_id, blocks, text, post_at=None):
    payload = {
        "blocks": blocks,
        "channel": channel_id,
        "text": text,
    }
    if post_at is None:
        print("sending message to", channel_id)
        url = "https://slack.com/api/chat.postMessage"
    else:
        print("scheduling message to", channel_id, "at", post_at)
        payload["post_at"] = post_at
        url = "https://slack.com/api/chat.scheduleMessage"

    r = requests.post(
        url,
        headers={
            "Content-type": "application/json",
            "Authorization": f"Bearer {BEARER_TOKEN}",
        },
        json=payload,
    )
    r.raise_for_status()
    if not r.json()["ok"]:
        if "error" in r.json():
            raise Exception(r.json()["error"])
        raise Exception(r.json()["response_metadata"]["messages"])
    if post_at is None:
        return r.json()["ts"]
    else:
        return r.json()["scheduled_message_id"]


def delete_scheduled_message(channel_id, msg_id):
    print("deleting scheduled message", channel_id, msg_id)
    r = requests.post(
        "https://slack.com/api/chat.deleteScheduledMessage",
        headers={
            "Content-type": "application/json",
            "Authorization": f"Bearer {BEARER_TOKEN}",
        },
        json={
            "channel": channel_id,
            "scheduled_message_id": msg_id,
        },
    )
    if not r.json()["ok"]:
        raise Exception(r.json()["response_metadata"]["messages"])
    r.raise_for_status()


def update_message(blocks, channel_id, ts_id):
    print("updating message to", channel_id)
    r = requests.post(
        "https://slack.com/api/chat.update",
        headers={
            "Content-type": "application/json",
            "Authorization": f"Bearer {BEARER_TOKEN}",
        },
        json={
            "channel": channel_id,
            "blocks": blocks,
            "ts": ts_id,
        },
    )
    if not r.json()["ok"]:
        raise Exception(r.json()["response_metadata"]["messages"])
    r.raise_for_status()


def open_view(trigger_id, blocks, text, submit_text, callback_id):
    print("opening view", trigger_id, callback_id)
    r = requests.post(
        "https://slack.com/api/views.open",
        headers={
            "Content-type": "application/json",
            "Authorization": f"Bearer {BEARER_TOKEN}",
        },
        json={
            "trigger_id": trigger_id,
            "view": {
                "type": "modal",
                "callback_id": callback_id,
                "title": {"type": "plain_text", "text": text},
                "blocks": blocks,
                "submit": {
                    "type": "plain_text",
                    "text": submit_text,
                },
            },
        },
    )
    if not r.json()["ok"]:
        raise Exception(r.json()["response_metadata"]["messages"])
    r.raise_for_status()


def update_view(view, view_id):
    print("updating view", view_id)
    r = requests.post(
        "https://slack.com/api/views.update",
        headers={
            "Content-type": "application/json",
            "Authorization": f"Bearer {BEARER_TOKEN}",
        },
        json={
            "view": view,
            "view_id": view_id,
        },
    )
    if not r.json()["ok"]:
        raise Exception(r.json()["response_metadata"]["messages"])
    r.raise_for_status()


def get_all_scheduled_posts(channel):
    past_cursors = set()
    payload = {
        "channel": channel,
    }
    while True:
        print("getting", payload)
        r = requests.get(
            "https://slack.com/api/chat.scheduledMessages.list",
            headers={
                "Content-type": "application/json",
                "Authorization": f"Bearer {BEARER_TOKEN}",
            },
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
        yield from data["scheduled_messages"]
        del data["scheduled_messages"]
        print(data)
        if "next_cursor" in data["response_metadata"]:
            payload["cursor"] = data["response_metadata"]["next_cursor"]
            if len(payload["cursor"]) == 0 or payload["cursor"] in past_cursors:
                return
            past_cursors.add(payload["cursor"])
        else:
            return
