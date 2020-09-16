import os
import json
import requests
from flask import Flask, redirect, request
from typing import Dict, Optional
from id3c.cli.redcap import is_complete
from husky_musher.middleware import ForwardedRemoteUser


REDCAP_API_TOKEN = os.environ['REDCAP_API_TOKEN']
REDCAP_API_URL = os.environ['REDCAP_API_URL']
ERROR_MESSAGE = """
    Error: Something went wrong. Please contact Husky Coronavirus Testing support by
    emailing <a href="mailto:huskytest@uw.edu">huskytest@uw.edu</a> or by calling
    <a href="tel:+12066162414">(206) 616-2414</a>.
"""
app = Flask(__name__)
app.wsgi_app = ForwardedRemoteUser(app.wsgi_app)


def fetch_user_data(net_id: str) -> Optional[Dict[str, str]]:
    """
    Exports a REDCap record matching the given *net_id*. Returns None if no
    match is found.

    Raises an :class:`AssertionError` if REDCap returns multiple matches for the
    given *net_id*.
    """
    fields = [
        'netid', 'record_id', 'eligibility_screening_complete', 'consent_form_complete',
        'enrollment_questionnaire_complete'
    ]

    filter_logic = f'[netid] = "{net_id}"'
    data = {
        'token': REDCAP_API_TOKEN,
        'content': 'record',
        'format': 'json',
        'type': 'flat',
        'csvDelimiter': '',
        'filterLogic': filter_logic,
        'rawOrLabel': 'raw',
        'rawOrLabelHeaders': 'raw',
        'exportCheckboxLabel': 'false',
        'exportSurveyFields': 'false',
        'exportDataAccessGroups': 'false',
        'returnFormat': 'json'
    }
    data['fields'] = ",".join(map(str, fields))

    response = requests.post(REDCAP_API_URL, data=data)
    response.raise_for_status()

    if len(response.json()) == 0:
        return None

    assert len(response.json()) == 1, "Multiple records exist with same NetID: " \
        f"{[ record['record_id'] for record in response.json() ]}"

    return response.json()[0]

def register_net_id(net_id: str) -> str:
    """
    Returns the REDCap record ID of the participant newly registered under the
    given *net_id*.
    """
    # REDCap enforces that we must provide a non-empty record ID. Because we're
    # using `forceAutoNumber` in the POST request, we do not need to provide a
    # real record ID.
    values = [{'netid': net_id, 'record_id': 'record ID cannot be blank'}]
    data = {
        'token': REDCAP_API_TOKEN,
        'content': 'record',
        'format': 'json',
        'type': 'flat',
        'overwriteBehavior': 'normal',
        'forceAutoNumber': 'true',
        'data': json.dumps(values),
        'returnContent': 'ids',
        'returnFormat': 'json'
    }
    response = requests.post(REDCAP_API_URL, data=data)
    response.raise_for_status()
    return response.json()[0]


def generate_survey_link(record_id: str) -> str:
    """
    Returns a generated survey link to the eligibility screening instrument for
    the given *record_id*.
    """
    data = {
        'token': REDCAP_API_TOKEN,
        'content': 'surveyLink',
        'format': 'json',
        'instrument': 'eligibility_screening',
        'event': 'enrollment_arm_1',  # TODO subject to change
        'record': record_id,
        'returnFormat': 'json'
    }
    response = requests.post(REDCAP_API_URL, data=data)
    response.raise_for_status()
    return response.text


@app.route('/')
def main():
    # Get NetID from Shibboleth data
    net_id = request.remote_user

    if not net_id:
        # TODO for testing purposes only
        net_id = 'KaasenG'

    if not net_id:
        app.logger.warning('Failed to get NetID for user')
        return ERROR_MESSAGE

    try:
        user_data = fetch_user_data(net_id)

    except Exception as e:
        app.logger.warning(f'Failed to fetch REDCap data: {e}')
        return ERROR_MESSAGE

    if user_data is None:
        # If not in REDCap project, create new record
        user_data = {'record_id': register_net_id(net_id)}

    # TODO -- generate a survey link for a particular day
    # We are awaiting finalization of the REDCap project to know how
    # daily attestations (repeating instruments) will be implemented.
    if is_complete('eligibility_screening', user_data) and \
        is_complete('consent_form', user_data) and \
        is_complete('enrollment_questionnaire', user_data):
        return f"Congrats, {net_id}, you're already registered under record ID " \
            f"{user_data['record_id']} and your eligibility " \
            "screening, consent form, and enrollment questionnaires are complete!"

    # Generate a link to the eligibility questionnaire, and then redirect.
    # Because of REDCap's survey queue logic, we can point a participant to an
    # upstream survey. If they've completed it, REDCap will automatically direct
    # them to the next, uncompleted survey in the queue.
    return redirect(generate_survey_link(user_data['record_id']))
