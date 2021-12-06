from util import DATABASE_INDEX_NAME
from boto3.dynamodb.conditions import Key
import random
from util import slack_command, db_table
import datetime
import time


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


@slack_command("/add-quote")
def _bot_add_quote(message, slack_team, channel_id, trigger_id):
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
def _bot_last_quotes(message, slack_team, channel_id, trigger_id):
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
def _bot_random_quote(message, slack_team, channel_id, trigger_id):
    all_quotes = _get_all_quotes(slack_team)
    if len(all_quotes) == 0:
        return "No quotes were found"
    quote = random.choice(all_quotes)
    return f"Ok, here is your random quote:\n{quote}"


@slack_command("/search-quotes")
def _bot_search_quotes(message, slack_team, channel_id, trigger_id):
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
