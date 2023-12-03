#!/bin/bash
set -e

php /usr/local/composer-mirror/bin/console app:crawler
# 6553/32768
if [[ $RANDOM -le 6553 ]]; then
    php /usr/local/composer-mirror/bin/console app:clear --expired=json
fi
