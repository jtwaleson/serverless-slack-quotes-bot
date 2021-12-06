import json
import base64
import traceback
from urllib.parse import parse_qsl


import util

import quotes
import polls


def lambda_handler(event, context):
    try:
        util._validate_signature(event)

        print("parsing body data and handling command")
        data = dict(parse_qsl(base64.b64decode(event["body"]).decode("utf-8")))
        if "command" in data:
            print(json.dumps(data, indent=4).replace(' ', '_'))
            response_text = util.handle_command(
                data["command"],
                data.get("text"),
                data["team_id"],
                data["channel_id"],
                data["trigger_id"],
            )
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "response_type": "in_channel",
                        "text": response_text,
                    }
                ),
                "headers": {"Content-Type": "application/json"},
            }
        elif "payload" in data:
            data = json.loads(data["payload"])
            print(json.dumps(data, indent=4).replace(' ', '_'))
            util.handle_action(data)
            return {
                "statusCode": 200,
                "body": json.dumps({}),
                "headers": {"Content-Type": "application/json"},
            }
    except Exception:
        traceback.print_exc()
        return {
            "statusCode": 200,
            "body": ("Oops, I failed to execute properly:\n" + traceback.format_exc()),
        }
