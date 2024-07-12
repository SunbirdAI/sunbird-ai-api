```sh
export HEROKU_ORGANIZATION=sunbird
heroku pg:info -a sema-dashboard
heroku pg:psql
heroku pg:psql -a sema-dashboard
heroku config -a sema-dashboard
heroku config:get DATABASE_URL -a sema-dashboard
heroku pg:backups -a sema-dashboard
heroku run python manage.py dumpdata --format=json --indent=2 -a sema-dashboard > fixtures/backup.json
heroku run python manage.py dumpdata devices --format=json --indent=2 -a sema-dashboard > fixtures/devices.json
heroku config -a sema-dashboard
heroku apps
heroku addons:create ssl:endpoint -a sema-dashboard
heroku domains -a sema-dashboard
heroku certs:auto:enable --app sema-dashboard\n
heroku certs:auto --app sema-dashboard
heroku teams
heroku run bash -a sema-dashboard

 heroku create sunbirdai-api
 heroku addons:create heroku-postgresql:essential-1 -a sunbirdai-api
 heroku addons:create heroku-redis:mini -a sunbirdai-api

 heroku addons:docs heroku-postgresql -a sunbirdai-api # view documentation
 heroku addons:docs heroku-redis -a sunbirdai-api
 heroku addons -a sunbirdai-api | grep heroku-redis
 heroku config:get DATABASE_URL -a sunbirdai-api
 heroku config:get REDIS_URL -a sunbirdai-api
 heroku pg:psql -a sunbirdai-api
 heroku addons:upgrade heroku-redis:mini heroku-redis:premium-0 -a sunbirdai-api
 heroku config:get REDIS_URL -a sunbirdai-api

 heroku config -a sunbirdai-api
 heroku config -a sunbirdai-api | grep REDIS

heroku config:set NEW_RELIC_LICENSE_KEY=b00b7ba49dbe7************************ -a sunbirdai-api
heroku config:set NEW_RELIC_APP_NAME="SunbirdAI API" -a sunbirdai-api
heroku config:set NEW_RELIC_ENV=production -a sunbirdai-api

heroku drains:add "https://log-api.newrelic.com/log/v1?Api-Key=b00b7ba49dbe7a192c83c60830cdf017FFFFNRAL&format=heroku" -a sunbirdai-api
```

0f7c8268a772194ab5d40c487de24bb6FFFFNRAL


```sh
docker run \
-e NEW_RELIC_LICENSE_KEY=b00b7ba49dbe7************************ \
-e NEW_RELIC_APP_NAME="SunbirdAI API" \
-p 8000:8000 -it --rm --name CONTAINER-NAME my_python_api:IMAGE_TAG
```


```sh
docker build -t registry.heroku.com/sunbirdai-api/web .
docker push registry.heroku.com/sunbirdai-api/web
heroku container:release web --app sunbirdai-api
```
