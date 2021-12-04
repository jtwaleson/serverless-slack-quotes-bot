#!/bin/bash
set -euo pipefail
#wget $(AWS_PROFILE=playground aws lambda get-function --function-name slack-quotes-bot | jq -r .Code.Location) -O src.zip
#unzip -f src.zip -d src
#rm src.zip

cd src
zip ../src.zip *
cd ..
AWS_PROFILE=playground aws lambda update-function-code --function-name slack-quotes-bot --zip-file fileb://src.zip
rm src.zip
