Serverless Slack Quote Bot
===

This is a minimalistic, single-file, serverless Quote Bot for Slack, based on this starting point: https://github.com/jtwaleson/minimalistic-serverless-slack-app .

It was created in June 2020.

Project goals
---

- Provide a Slack Quote Bot to store the legendary, embarrassing, funny sayings of your coworkers.

Technologies used
---

Shared with https://github.com/jtwaleson/minimalistic-serverless-slack-app:

- AWS API Gateway
- AWS Lambda
- Python 3.8
- Slack App

Additional:

- AWS DynamoDB

Design goals
---

- Simplicity (single file, no Layers in Lambda, no dependencies)
- Cheap to run, it should only cost a couple of cents per month
- Secure
- Cloud-only. You can not run this program locally. No Flask, no Gunicorn, no WSGI etc. Just a plain Lambda handler.


Included functionality
---

Slack Slash Commands:
- `/add-quote`
- `/last-quotes`
- `/random-quote`
- `/search-quotes`


Setting it up
===

Start by setting up the basic infrastructure from https://github.com/jtwaleson/minimalistic-serverless-slack-app via the README there. This should take about 10 minutes.

Then we'll follow these steps:

1. Create the DynamoDB table and Index
2. Give your Lambda IAM Role access to the DynamoDB table
3. Change the code to include the new slash commands
4. Add the Slash commands in Slack

Here we go!

Step 1 - Create the DynamoDB table and Index
---

Step 2 - Give your Lambda IAM Role access to the DynamoDB table
---
Step 3 - Change the code to include the new slash commands
---

Step 4 - Add the Slash commands in Slack
---

