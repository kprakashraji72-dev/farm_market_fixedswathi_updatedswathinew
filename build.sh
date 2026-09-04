#!/usr/bin/env bash
# Render runs this automatically on every deploy (set as the Build Command
# in the Render dashboard: ./build.sh)
set -o errexit  # stop the build immediately if any command fails

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate
