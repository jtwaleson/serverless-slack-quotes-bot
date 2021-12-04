import uuid
import json
from util import slack_command, send_message, slack_action, update_message

to_num = {
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
def _create_new_poll(message, slack_team, channel_id):
    sections = list(
        filter(lambda x: len(x) > 0, map(lambda y: y.strip(", "), message.split('"')))
    )

    blocks = [
        {
            "type": "section",
            "text": {"type": "plain_text", "text": sections[0], "emoji": True},
        }
    ]
    for idx, section in enumerate(sections[1:]):
        idx += 1
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":{to_num[idx]}: {section}",
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": f":{to_num[idx]}:",
                        "emoji": True,
                    },
                    "value": f"vote-{str(uuid.uuid4())}",
                    "action_id": "vote-poll",
                },
            }
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": " "}})

    send_message(channel_id, blocks=blocks)
    return "Poll created"


@slack_action("vote-poll")
def _handle_vote(data):
    print(json.dumps(data, indent=4))
    blocks = data["message"]["blocks"]
    added_or_removed_user = f'<@{data["user"]["id"]}>'
    for action in data["actions"]:
        for idx, block in enumerate(blocks):
            try:
                if block["accessory"]["value"] == action["value"]:
                    current_users = blocks[idx + 1]["text"]["text"].split()
                    try:
                        current_users.remove(added_or_removed_user)
                    except ValueError:
                        current_users.append(added_or_removed_user)
                    blocks[idx + 1]["text"]["text"] = " ".join(current_users) + " "
            except KeyError:
                pass
    update_message(blocks, data["channel"]["id"], data["message"]["ts"])
