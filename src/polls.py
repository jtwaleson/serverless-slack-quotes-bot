import arrow
import re
import time
import random
import pytz
import json
import uuid
from boto3.dynamodb.conditions import Key, Attr
from blocks import (
    text_input,
    channel_select,
    divider,
    checkboxes,
    static_select,
    static_select_action,
)
from util import (
    slack_command,
    send_message,
    slack_block_action,
    slack_view_submission,
    update_message,
    open_view,
    db_table,
    update_view,
    DATABASE_INDEX_NAME,
    get_all_scheduled_posts,
    delete_scheduled_message,
)

# TODO more votes? The amount of number emojis is limited to single digits.
to_num = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
}


class DraftPoll:
    pass


class RecurringPoll(DraftPoll):
    pass


class ActivePoll(DraftPoll):
    pass


@slack_command("/easee-poll")
def _create_new_poll(data):
    sections = list(
        filter(
            lambda x: len(x) > 0,
            map(lambda y: y.strip(", "), data.get("text", "").split('"')),
        )
    )
    if len(sections) > 0:
        title = sections[0]
        prefilled_options = sections[1:]
    else:
        title = ""
        prefilled_options = []

    trigger_id = data["trigger_id"]
    channel_id = data["channel_id"]
    blocks = [
        text_input(
            text="What's this poll about",
            multiline=True,
            action_id="title",
            optional=False,
            initial_value=title,
        ),
        channel_select(initial_channel=channel_id),
        divider(),
        checkboxes(
            text="Advanced options",
            block_id="advanced-options",
            action_id="create-poll-options-changed",
            options=[{"text": "Anonymous voting", "value": "anonymous-votes"}],
        ),
        static_select_action(
            text="Recurring poll",
            block_id="recurring-settings",
            action_id="update_recurring_settings",
            options=[
                {"text": "Never", "value": "never"},
                {"text": "Daily", "value": "daily"},
                {"text": "Weekly", "value": "weekly"},
                {"text": "Monthly", "value": "monthly"},
            ],
        ),
        static_select(
            block_id="limit-votes",
            initial_option_index=0,
            text="Limit the amount of votes",
            action_id="limit-votes",
            options=[
                {
                    "text": "Unlimited" if i == 0 else str(i),
                    "value": str(i),
                }
                for i in range(10)
            ],
        ),
        divider(),
    ]
    for i in range(9):
        blocks.append(
            {
                "type": "input",
                "block_id": f"option-{i}",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "option",
                    "initial_value": prefilled_options[i]
                    if i < len(prefilled_options)
                    else "",
                },
                "label": {
                    "type": "plain_text",
                    "text": f"Option {i + 1}",
                    "emoji": True,
                },
                "optional": True if i >= 2 else False,
            }
        )
    open_view(
        trigger_id,
        blocks=blocks,
        text="Create a new poll",
        submit_text="Create",
        callback_id="poll-create",
    )
    return "Creating poll"


@slack_block_action("update-recurring-settings")
def _update_recurring_settings(data):
    view = data["view"]
    recurring_block = None
    settings_blocks = []

    for idx, block in enumerate(view["blocks"]):
        if block["block_id"] == "recurring-settings":
            recurring_block = idx
        elif block["block_id"].startswith("recurring-sub-settings"):
            settings_blocks.append(block)

    for settings_block in settings_blocks:
        view["blocks"].remove(settings_block)

    frequency = view["state"]["values"]["recurring-settings"][
        "update-recurring-settings"
    ]["selected_option"]["value"]

    at = recurring_block + 1
    if frequency != "never":
        view["blocks"].insert(
            at,
            {
                "type": "input",
                "block_id": "recurring-sub-settings-tz",
                "label": {
                    "type": "plain_text",
                    "text": "Timezone",
                    "emoji": True,
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "timzeone",
                    "initial_value": "Europe/Amsterdam",
                },
                "optional": False,
            },
        )
        at += 1
        view["blocks"].insert(
            at,
            {
                "type": "input",
                "block_id": "recurring-sub-settings-time",
                "label": {
                    "type": "plain_text",
                    "text": "Pick a time for posting the poll.",
                    "emoji": True,
                },
                "element": {
                    "type": "timepicker",
                    "action_id": "timepicker",
                    "placeholder": {"type": "plain_text", "text": "Select a time"},
                },
                "optional": False,
            },
        )
        at += 1

    if frequency == "weekly":
        view["blocks"].insert(
            at,
            {
                "type": "input",
                "block_id": "recurring-sub-settings-days",
                "element": {
                    "type": "multi_static_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select days",
                        "emoji": True,
                    },
                    "options": [],
                    "action_id": "on-which-days",
                },
                "label": {
                    "type": "plain_text",
                    "text": "Select the days on which to post",
                    "emoji": True,
                },
            },
        )
        for day in (
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ):
            view["blocks"][at]["element"]["options"].append(
                {
                    "text": {
                        "type": "plain_text",
                        "text": day,
                    },
                    "value": day,
                }
            )
        at += 1
    elif frequency == "monthly":
        view["blocks"].insert(
            at,
            {
                "type": "input",
                "block_id": "recurring-sub-settings-day-number",
                "element": {
                    "type": "static_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select days",
                        "emoji": True,
                    },
                    "options": [],
                    "action_id": "on-which-day-number",
                },
                "label": {
                    "type": "plain_text",
                    "text": "Select the day of the month on which to post",
                    "emoji": True,
                },
            },
        )
        for day in range(32):
            view["blocks"][at]["element"]["options"].append(
                {
                    "text": {
                        "type": "plain_text",
                        "text": str(day)
                        if day < 29
                        else f"{day} (will not happen every month)",
                    },
                    "value": str(day),
                }
            )
        at += 1

    if frequency != "never":
        view["blocks"].insert(
            at, {"type": "divider", "block_id": "recurring-sub-settings-final-divider"}
        )
        at += 1

    update_view(
        {
            "blocks": view["blocks"],
            "title": view["title"],
            "submit": view["submit"],
            "callback_id": view["callback_id"],
            "type": view["type"],
        },
        view_id=view["id"],
    )
    return ""


@slack_block_action("vote-poll")
def _handle_vote(data):
    blocks = data["message"]["blocks"]
    added_or_removed_user = f'<@{data["user"]["id"]}>'

    item = db_table.get_item(
        Key={
            "timestamp": int(data["message"]["blocks"][0]["block_id"].split(":")[1]),
        }
    )["Item"]

    if item["team"] != f'{data["message"]["team"]}:poll':
        raise Exception("wrong team")

    limit_votes = item.get("limit_votes", 0)

    anonymous = item["anonymous"]

    votes = item["votes"]

    current_vote_count_for_user = 0
    for v in votes.values():
        if added_or_removed_user in v:
            current_vote_count_for_user += 1

    for action in data["actions"]:
        vote = votes[action["block_id"]]
        if added_or_removed_user in vote:
            vote.remove(added_or_removed_user)
        else:
            if limit_votes > 0 and current_vote_count_for_user >= limit_votes:
                raise Exception("User is at max votes. Can we show this friendly?")
            vote.append(added_or_removed_user)

    db_table.put_item(Item=item)

    for block in blocks:
        if not block["block_id"].startswith("option-"):
            continue
        vote = votes[block["block_id"].replace("-people", "")]
        if block["block_id"].endswith("-people"):
            if not anonymous:
                block["text"]["text"] = " ".join(vote) + " "
            else:
                block["text"]["text"] = ":thumbsup:" * len(vote) + " "
        else:
            block["text"]["text"] = re.sub(" `\\d+`$", "", block["text"]["text"]) + (
                f" `{len(vote)}`" if len(vote) > 0 else ""
            )
    update_message(blocks, data["channel"]["id"], data["message"]["ts"])


def get_message_id(msg):
    # strip off the last 3 random digits
    return msg["blocks"][0]["block_id"][:-3]


def get_next_event_timestamps(recurring_data):
    tz = recurring_data["tz"]
    frequency = recurring_data["frequency"]
    hours, minutes = map(int, recurring_data["time"].split(":"))

    t1 = arrow.now(tz)
    t = t1.replace(hour=hours, minute=minutes, second=0, microsecond=0)
    if t < t1:
        t = t.shift(days=1)
    for i in range(10):
        week_day = t.format("dddd")
        result = int(t.timestamp())
        if recurring_data["frequency"] == "daily":
            yield result
        elif (
            recurring_data["frequency"] == "weekly"
            and week_day in recurring_data["days"]
        ):
            yield result
        elif recurring_data["frequency"] == "monthly" and t.day == int(
            recurring_data["day_number"]
        ):
            yield result
        t = t.shift(days=1)


def schedule_recurring_polls(team):
    channel_messages = {}
    all_recurring_polls = db_table.query(
        IndexName=DATABASE_INDEX_NAME,
        KeyConditionExpression=Key("team").eq(f"{team}:poll-recurring"),
        ScanIndexForward=False,
    )
    for recurring_poll in all_recurring_polls["Items"]:
        print("recurring_poll", recurring_poll)
        channel = recurring_poll["channel"]
        if channel not in channel_messages:
            channel_messages[channel] = {}
            for scheduled_post in get_all_scheduled_posts(channel):
                msg_id = get_message_id(scheduled_post)
                channel_messages[channel][msg_id] = scheduled_post

        scheduled_messages = channel_messages[channel]

        for i in get_next_event_timestamps(recurring_poll["recurring"]):
            in_msg_id = i * 1000 + random.randint(0, 1000)
            to_schedule_message_id = f"{recurring_poll['uuid']}:{in_msg_id}"
            if to_schedule_message_id in scheduled_messages:
                del scheduled_messages[to_schedule_message_id]
            else:
                blocks, votes = get_blocks_for_polls(
                    title=recurring_poll.get("title", "SORRY"),
                    anonymous=recurring_poll["anonymous"],
                    limit_votes=recurring_poll["limit_votes"],
                    texts=recurring_poll["options"],
                    created_by=recurring_poll["created_by"],
                    scheduled=True,
                    top_id=to_schedule_message_id,
                )
                msg_id = send_message(
                    channel, blocks=blocks, text="Recurring poll", post_at=i
                )
                db_table.put_item(
                    Item={
                        "team": f"{team}:poll",
                        "timestamp": in_msg_id,
                        "created_by": recurring_poll["created_by"],
                        "anonymous": recurring_poll["anonymous"],
                        "votes": votes,
                        "limit_votes": recurring_poll["limit_votes"],
                        "scheduled_message_id": msg_id,
                    }
                )

    print("deleting scheduled messages")
    for scheduled_messages in channel_messages.values():
        for k, v in scheduled_messages.items():
            delete_scheduled_message(channel, v["id"])


@slack_view_submission("poll-create")
def _handle_post_poll(data):
    anonymous = False
    limit_votes = 0
    texts = []
    title = None
    created_by = data["user"]["id"]
    team = data["team"]["id"]

    channel_id = None

    recurring = {}

    #    print(json.dumps(data["view"]["state"]["values"], indent=4).replace(" ", "_"))

    for k1, v1 in data["view"]["state"]["values"].items():
        for k, v in v1.items():
            if k == "limit-votes":
                limit_votes = int(v["selected_option"]["value"])
            elif k1 == "advanced-options":
                for s in v["selected_options"]:
                    if s["value"] == "anonymous-votes":
                        anonymous = True
            elif k == "option":
                if v["value"] is not None and len(v["value"].strip()) > 0:
                    texts.append(v["value"].strip())
            elif k == "title":
                title = v["value"].strip()
            elif k == "selected-channel":
                channel_id = v["selected_channel"]
            elif k1 == "recurring-settings":
                recurring["frequency"] = v["selected_option"]["value"]
            elif k1 == "recurring-sub-settings-day-number":
                recurring["day_number"] = int(v["selected_option"]["value"])
            elif k1 == "recurring-sub-settings-tz":
                recurring["tz"] = v["value"]
            elif k1 == "recurring-sub-settings-time":
                recurring["time"] = v["selected_time"]
            elif k1 == "recurring-sub-settings-days":
                recurring["days"] = list(
                    map(lambda x: x["value"], v["selected_options"])
                )

    if recurring.get("frequency", "never") != "never":
        if recurring["tz"] not in pytz.all_timezones:
            return {
                "response_action": "errors",
                "errors": {
                    "recurring-sub-settings-tz": "Not a valid timezone. Use e.g. Europe/Amsterdam. For a full list see https://en.wikipedia.org/wiki/List_of_tz_database_time_zones."
                },
            }
        db_table.put_item(
            Item={
                "timestamp": int(time.time()) * 1000 + random.randint(0, 1000),
                "team": f"{team}:poll-recurring",
                "recurring": recurring,
                "created_by": created_by,
                "anonymous": anonymous,
                "limit_votes": limit_votes,
                "options": texts,
                "title": title,
                "channel": channel_id,
                "uuid": str(uuid.uuid4()),
            }
        )
        return {}

    msg_id = int(time.time()) * 1000 + random.randint(0, 1000)
    blocks, votes = get_blocks_for_polls(
        title,
        anonymous,
        limit_votes,
        texts,
        created_by,
        scheduled=False,
        top_id=f":{msg_id}",
    )

    message_id = send_message(channel_id, blocks=blocks, text=title)
    db_table.put_item(
        Item={
            "team": f'{data["view"]["team_id"]}:poll',
            "timestamp": msg_id,
            "created_by": created_by,
            "anonymous": anonymous,
            "votes": votes,
            "limit_votes": limit_votes,
        }
    )

    return {}


def get_blocks_for_polls(
    title, anonymous, limit_votes, texts, created_by, scheduled, top_id
):
    blocks = [
        {
            "type": "section",
            "block_id": top_id,
            "text": {
                "type": "plain_text",
                "text": f"{title}{' - (anonymous)' if anonymous else ''}{' - max ' + str(limit_votes) + ' votes per person' if limit_votes > 0 else ''}",
            },
        }
    ]
    votes = {}
    for idx, option in enumerate(texts):
        idx += 1
        votes[f"option-{idx}"] = []
        blocks.append(
            {
                "type": "section",
                "block_id": f"option-{idx}",
                "text": {
                    "type": "mrkdwn",
                    "text": f":{to_num[idx]}: {option}",
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": f":{to_num[idx]}:",
                    },
                    "value": f"vote-{str(uuid.uuid4())}",
                    "action_id": "vote-poll",
                },
            }
        )
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": " "},
                "block_id": f"option-{idx}-people",
            }
        )

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Poll created by <@{created_by}>{', scheduled regularly' if scheduled else ''}",
                }
            ],
        }
    )
    return blocks, votes


def schedule_all_recurring_polls():
    scan_kwargs = {
        "FilterExpression": Attr("recurring").exists(),
        "ProjectionExpression": "team",
    }
    teams = set()

    done = False
    start_key = None
    while not done:
        if start_key:
            scan_kwargs["ExclusiveStartKey"] = start_key
        response = db_table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            if item["team"].endswith(":poll-recurring"):
                teams.add(item["team"].split(":")[0])
        start_key = response.get("LastEvaluatedKey", None)
        done = start_key is None

    for team in teams:
        schedule_recurring_polls(team)
