import base64
import hmac
import os
import time
import hashlib
import traceback
import boto3
import random
import datetime
from boto3.dynamodb.conditions import Key
from urllib.parse import parse_qsl


# A - settings

try:
    SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
except KeyError:
    raise Exception(
        "Set SLACK_SIGNING_SECRET as an environment variable. "
        "You can find this on the Slack 'App Settings' under "
        "'Signing Secret'."
    )

DATABASE_INDEX_NAME = "team-timestamp-index"
DATABASE_TABLE = "quotes"


# B - bot command routing boilerplate

SLACK_COMMAND_TO_HANDLER = {}


def _handle_command(command, message, slack_team):
    print("handling command", command)
    if command in SLACK_COMMAND_TO_HANDLER:
        handler = SLACK_COMMAND_TO_HANDLER[command]
        kwargs = {
            "message": message,
            "slack_team": slack_team,
        }
        response = handler(**kwargs)
        if response is None:
            raise Exception(f"Handler {str(handler)} should return a string")
        else:
            return response
    else:
        return f"No handler registered for command {command}"


# this is a decorator for routing commands
def slack_command(command):
    global SLACK_COMMAND_TO_HANDLER
    if command in SLACK_COMMAND_TO_HANDLER:
        raise Exception(f"command {command} is already registered")

    def wrapper(command_handler):
        SLACK_COMMAND_TO_HANDLER[command] = command_handler
        return command_handler

    return wrapper


# database initialization
db_table = boto3.resource("dynamodb").Table(DATABASE_TABLE)


def _get_all_quotes(slack_team):
    all_quotes = db_table.query(
        IndexName=DATABASE_INDEX_NAME,
        KeyConditionExpression=Key("team").eq(slack_team),
        ScanIndexForward=False,
    )
    return list(
        map(
            lambda item: str(
                datetime.datetime.fromtimestamp(int(item["timestamp"] / 1000))
            )
            + " (UTC) - "
            + str(item["message"]),
            all_quotes["Items"],
        )
    )


# C - actual bot functions


@slack_command("/add-quote")
def _bot_add_quote(message, slack_team):
    if message is None:
        return "A quote must have a text... Try again with '/add-quote I am an idiot'"
    parts = message.split(" ")
    if not parts[0].startswith("@"):
        return "The quote must start with the slack name of a user (including @)"
    if len(parts) < 2:
        return "Very good, but now the person must say something, try '/add-quote @user: I am an idiot'"
    db_table.put_item(
        Item={
            "team": slack_team,
            "timestamp": int(time.time()) * 1000 + random.randint(0, 1000),
            "message": message,
        }
    )
    return "Thanks! Your quote was preserved for future generations."


@slack_command("/last-quotes")
def _bot_last_quotes(message, slack_team):
    all_quotes = _get_all_quotes(slack_team)
    if len(all_quotes) == 0:
        return "No quotes were found"
    if message is None:
        return "\n - ".join(["Here are the latest quotes:"] + all_quotes[:10])
    elif message == "all":
        return "\n - ".join(["Here are all quotes:"] + all_quotes)
    else:
        try:
            skip = int(message)
        except ValueError:
            return "You can use /last-quotes with a number to skip a number of quotes. Example: '/last-quotes 30' will skip the 30 latest quotes"
        return "\n - ".join(
            [f"Here are some quotes skipping the first {skip}:"]
            + all_quotes[skip : skip + 10]
        )


@slack_command("/random-quote")
def _bot_random_quote(message, slack_team):
    all_quotes = _get_all_quotes(slack_team)
    if len(all_quotes) == 0:
        return "No quotes were found"
    quote = random.choice(all_quotes)
    return f"Ok, here is your random quote:\n{quote}"


@slack_command("/search-quotes")
def _bot_search_quotes(message, slack_team):
    if message is None or len(message) == 0:
        return "We need some text to search for! Try '/search-quote hi'"
    all_quotes = _get_all_quotes(slack_team)
    unlimited = message.endswith(" unlimited")
    if unlimited:
        message = message[: -len(" unlimited")]

    matches = list(filter(lambda x: message.lower() in x.lower(), all_quotes))
    if len(matches) == 0:
        return "No quote found! Sorry. Just keep adding more of them."
    elif unlimited:
        return "\n - ".join(
            ["You found the unlimited function, you are 1337:"] + matches
        )
    else:
        random.shuffle(matches)
        return "\n - ".join(["This is what I found (limited to 10): \n"] + matches[:10])


# D - slack message handling boilerplate


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


# E - entry point of the app


def lambda_handler(event, context):
    try:
        _validate_signature(event)

        print("parsing body data and handling command")
        data = dict(parse_qsl(base64.b64decode(event["body"]).decode("utf-8")))
        response_text = _handle_command(
            data["command"], data.get("text"), data["team_id"]
        )
        return {
            "statusCode": 200,
            "body": response_text,
        }
    except Exception:
        traceback.print_exc()
        return {
            "statusCode": 200,
            "body": ("Oops, I failed to execute properly:\n" + traceback.format_exc()),
        }
