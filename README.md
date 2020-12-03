# husky-musher
A redirecting service for the Husky Coronavirus Testing study

## Running locally
Run the Flask app with:
```sh
pipenv run flask run
```

The default is to use the production REDCap project (i.e. when `FLASK_ENV` is
unset or `FLASK_ENV=production`).

To use the testing/development REDCap project instead, set
`FLASK_ENV=development`.

## Requirements
See Pipfile for required libraries.

The required environment variables are:
* `REDCAP_API_TOKEN_redcap.iths.org_23854` (production)
* `REDCAP_API_TOKEN_redcap.iths.org_24515` (development)


## Tests
Run doctests on the utils functions with:
```sh
pipenv run python3 -m doctest lib/husky_musher/utils/*
```

Run unit tests with:
```sh
pipenv run python -m unittest lib/husky_musher/tests/*
```


## Attributions
"[Paw Print](https://thenounproject.com/search/?q=dog+paw&i=3354750)" icon By Humantech from [the Noun Project](http://thenounproject.com/).
