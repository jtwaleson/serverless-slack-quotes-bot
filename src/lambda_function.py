import json
import base64
import traceback
from urllib.parse import parse_qsl


from util import SLACK_CALLBACK_HANDLERS, validate_signature, extract_key_from_payload

import quotes  # NOQA
import polls  # NOQA


def lambda_handler(event, context):
    data = None
    sub_data = None
    try:
        validate_signature(event)

        print("parsing body data and handling command")
        data = dict(parse_qsl(base64.b64decode(event["body"]).decode("utf-8")))

        if "command" in data:
            handlers = SLACK_CALLBACK_HANDLERS["command"]
            command = data["command"]
            if command not in handlers:
                raise Exception(f"No command hanlder registered for {command}")

            response_text = handlers[command](data)
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
            sub_data = json.loads(data["payload"])
            callback_type = sub_data["type"]
            if callback_type not in SLACK_CALLBACK_HANDLERS:
                raise Exception(
                    f"No callback handler built-in for type {callback_type}"
                )
            key = extract_key_from_payload(sub_data["type"], sub_data)
            handlers = SLACK_CALLBACK_HANDLERS[callback_type]
            if key not in handlers:
                raise Exception(f"No {callback_type} callback registered for {key}")
            response = handlers[key](sub_data)
            return {
                "statusCode": 200,
                "body": json.dumps(response),
                "headers": {"Content-Type": "application/json"},
            }
        else:
            print("COULD NOT HANDLE INCOMING DATA")
            print(json.dumps(data, indent=4).replace(" ", "_"))
            raise Exception("Could not handle incoming data, no command or payload")
    except Exception:
        if sub_data:
            print("data that lead to exception:")
            print(json.dumps(sub_data, indent=4).replace(" ", "_"))
        elif data:
            print("data that lead to exception:")
            print(json.dumps(data, indent=4).replace(" ", "_"))
        traceback.print_exc()
        return {
            "statusCode": 200,
            "body": ("Oops, I failed to execute properly:\n" + traceback.format_exc()),
        }
