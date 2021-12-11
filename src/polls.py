import re
import uuid
from util import (
    slack_command,
    send_message,
    slack_block_action,
    slack_view_submission,
    update_message,
    open_view,
    db_table,
)

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
        {
            "type": "input",
            "block_id": "title",
            "element": {
                "type": "plain_text_input",
                "multiline": True,
                "action_id": "title",
                "initial_value": title,
            },
            "label": {
                "type": "plain_text",
                "text": "What's the poll about",
                "emoji": True,
            },
            "optional": False,
        },
        {
            "type": "input",
            "element": {
                "type": "channels_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Channel",
                    "emoji": True,
                },
                "action_id": "selected-channel",
                "initial_channel": channel_id,
            },
            "label": {"type": "plain_text", "text": "Select a channel", "emoji": True},
        },
        {"type": "divider"},
        {
            "type": "input",
            "block_id": "advanced-options",
            "element": {
                "type": "checkboxes",
                "options": [
                    {
                        "text": {
                            "type": "plain_text",
                            "text": "Anonymous voting",
                            "emoji": True,
                        },
                        "value": "anonymous-votes",
                    },
                    #             {
                    #                 "text": {
                    #                     "type": "plain_text",
                    #                     "text": "Schedule recurring message",
                    #                     "emoji": True,
                    #                 },
                    #                 "value": "recurring-poll",
                    #             },
                ],
                "action_id": "create-poll-options-changed",
            },
            "label": {"type": "plain_text", "text": "Advanced options", "emoji": True},
            "optional": True,
        },
        {
            "type": "input",
            "element": {
                "type": "static_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select an item",
                    "emoji": True,
                },
                "options": [],
                "action_id": "limit-votes",
                "initial_option": {
                    "text": {
                        "type": "plain_text",
                        "text": "Unlimited",
                    },
                    "value": "0",
                },
            },
            "label": {
                "type": "plain_text",
                "text": "Limit the amount of votes",
                "emoji": True,
            },
        },
        {"type": "divider"},
    ]
    for i in range(10):
        blocks[-2]["element"]["options"].append(
            {
                "text": {
                    "type": "plain_text",
                    "text": "Unlimited" if i == 0 else str(i),
                },
                "value": str(i),
            }
        )
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
    return ""


@slack_block_action("vote-poll")
def _handle_vote(data):
    blocks = data["message"]["blocks"]
    added_or_removed_user = f'<@{data["user"]["id"]}>'

    item = db_table.get_item(
        Key={
            "timestamp": int(data["message"]["ts"].replace(".", "")),
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


@slack_view_submission("poll-create")
def _handle_post_poll(data):
    anonymous = False
    limit_votes = 0
    # recurring = False
    texts = []
    title = None
    created_by = data["user"]["id"]

    channel_id = None

    for k1, v1 in data["view"]["state"]["values"].items():
        for k, v in v1.items():
            if k == "limit-votes":
                limit_votes = int(v["selected_option"]["value"])
            elif k1 == "advanced-options":
                for s in v["selected_options"]:
                    if s["value"] == "anonymous-votes":
                        anonymous = True
                    # elif s["value"] == "recurring-poll":
                    #     recurring = True
            elif k == "option":
                if v["value"] is not None and len(v["value"].strip()) > 0:
                    texts.append(v["value"].strip())
            elif k == "title":
                title = v["value"].strip()
            elif k == "selected-channel":
                channel_id = v["selected_channel"]

    blocks = [
        {
            "type": "section",
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
                    "text": f"Poll created by <@{created_by}>",
                }
            ],
        }
    )
    message_id = send_message(channel_id, blocks=blocks, text=title)
    db_table.put_item(
        Item={
            "team": f'{data["view"]["team_id"]}:poll',
            "timestamp": int(message_id.replace(".", "")),
            "created_by": created_by,
            "anonymous": anonymous,
            "votes": votes,
            "limit_votes": limit_votes,
        }
    )

    return {}
