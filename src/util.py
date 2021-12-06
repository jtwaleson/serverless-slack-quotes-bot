import base64
import json
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

SLACK_COMMAND_TO_HANDLER = {}
SLACK_ACTION_TO_HANDLER = {}


db_table = boto3.resource("dynamodb").Table(DATABASE_TABLE)


def handle_command(command, message, slack_team, channel_id, trigger_id):
    print("handling command", command)
    if command in SLACK_COMMAND_TO_HANDLER:
        handler = SLACK_COMMAND_TO_HANDLER[command]
        kwargs = {
            "message": message,
            "slack_team": slack_team,
            "channel_id": channel_id,
            "trigger_id": trigger_id,
        }
        response = handler(**kwargs)
        if response is None:
            raise Exception(f"Handler {str(handler)} should return a string")
        else:
            return response
    else:
        return f"No handler registered for command {command}"


def handle_action(data):
    if "actions" not in data:
        raise Exception("data does not contain actions, help!")
    if len(data["actions"]) > 1:
        raise Exception("I can not yet handle more than one action per response")

    action = data["actions"][0]["action_id"]

    print("handling action", action)

    if action in SLACK_ACTION_TO_HANDLER:
        handler = SLACK_ACTION_TO_HANDLER[action]
        handler(data)
    else:
        raise Exception(f"No handler registered for action {action}")


# this is a decorator for routing commands
def slack_command(command):
    global SLACK_COMMAND_TO_HANDLER
    if command in SLACK_COMMAND_TO_HANDLER:
        raise Exception(f"command {command} is already registered")

    def wrapper(command_handler):
        SLACK_COMMAND_TO_HANDLER[command] = command_handler
        return command_handler

    return wrapper


# this is a decorator for routing actions
def slack_action(action):
    global SLACK_ACTION_TO_HANDLER
    if action in SLACK_ACTION_TO_HANDLER:
        raise Exception(f"action {action} is already registered")

    def wrapper(action_handler):
        SLACK_ACTION_TO_HANDLER[action] = action_handler
        return action_handler

    return wrapper


def _validate_signature(event):
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


def send_message(channel_id, blocks):
    print("sending message to", channel_id)
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={
            "Content-type": "application/json",
            "Authorization": f"Bearer {BEARER_TOKEN}",
        },
        json={
            "blocks": blocks,
            "channel": channel_id,
        },
    )
    print("sending message", r.json())


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
    print("updating message", json.dumps(r.json(), indent=4))


def open_view(trigger_id, blocks):
    print("opening view", trigger_id)
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
                "callback_id": "hmmmwhat",
                "title": {"type": "plain_text", "text": "Create a new poll"},
                "blocks": blocks,
                "submit": {
                    "type": "plain_text",
                    "text": "Create Poll"
                },
            },
        },
    )
    print("sending message", r.json())
