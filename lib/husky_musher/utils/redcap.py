import os
import json
import requests
from flask import request
from datetime import datetime, timedelta
from typing import Dict, Optional
from id3c.cli.redcap import is_complete


REDCAP_API_TOKEN = os.environ['REDCAP_API_TOKEN']
REDCAP_API_URL = os.environ['REDCAP_API_URL']
STUDY_START_DATE = datetime(2020, 9, 24) # Study start date of 2020-09-24

attestation_start = (STUDY_START_DATE + timedelta(days=1)).strftime("%B %d, %Y")


def fetch_participant(user_info: dict) -> Optional[Dict[str, str]]:
    """
    Exports a REDCap record matching the given *user_info*. Returns None if no
    match is found.

    Raises an :class:`AssertionError` if REDCap returns multiple matches for the
    given *user_info*.
    """
    netid = user_info["netid"]

    fields = [
        'netid',
        'record_id',
        'eligibility_screening_complete',
        'consent_form_complete',
        'enrollment_questionnaire_complete',
    ]

    data = {
        'token': REDCAP_API_TOKEN,
        'content': 'record',
        'format': 'json',
        'type': 'flat',
        'csvDelimiter': '',
        'filterLogic': f'[netid] = "{netid}"',
        'fields': ",".join(map(str, fields)),
        'rawOrLabel': 'raw',
        'rawOrLabelHeaders': 'raw',
        'exportCheckboxLabel': 'false',
        'exportSurveyFields': 'false',
        'exportDataAccessGroups': 'false',
        'returnFormat': 'json'
    }

    response = requests.post(REDCAP_API_URL, data=data)
    response.raise_for_status()

    if len(response.json()) == 0:
        return None

    assert len(response.json()) == 1, "Multiple records exist with same NetID: " \
        f"{[ record['record_id'] for record in response.json() ]}"

    return response.json()[0]


def register_participant(user_info: dict) -> str:
    """
    Returns the REDCap record ID of the participant newly registered with the
    given *user_info*
    """
    # REDCap enforces that we must provide a non-empty record ID. Because we're
    # using `forceAutoNumber` in the POST request, we do not need to provide a
    # real record ID.
    records = [{**user_info, 'record_id': 'record ID cannot be blank'}]
    data = {
        'token': REDCAP_API_TOKEN,
        'content': 'record',
        'format': 'json',
        'type': 'flat',
        'overwriteBehavior': 'normal',
        'forceAutoNumber': 'true',
        'data': json.dumps(records),
        'returnContent': 'ids',
        'returnFormat': 'json'
    }
    response = requests.post(REDCAP_API_URL, data=data)
    response.raise_for_status()
    return response.json()[0]


def generate_survey_link(record_id: str, event: str, instrument: str, instance: int = None) -> str:
    """
    Returns a generated survey link for the given *instrument* within the
    *event* of the *record_id*.

    Will include the repeat *instance* if provided.
    """
    data = {
        'token': REDCAP_API_TOKEN,
        'content': 'surveyLink',
        'format': 'json',
        'instrument': instrument,
        'event': event,
        'record': record_id,
        'returnFormat': 'json'
    }

    if instance:
        data['repeat_instance'] = str(instance)

    response = requests.post(REDCAP_API_URL, data=data)
    response.raise_for_status()
    return response.text


def get_todays_repeat_instance() -> int:
    """
    Returns the repeat instance number, i.e. days since the start of the study
    with the first instance starting at 1.
    """
    return 1 + (datetime.today() - STUDY_START_DATE).days


def redcap_registration_complete(redcap_record: dict) -> bool:
    """
    Returns True if a given *redcap_record* shows a participant has completed
    the enrollment surveys. Otherwise, returns False.

    >>> redcap_registration_complete(None)
    False

    >>> redcap_registration_complete({})
    False

    >>> redcap_registration_complete({ \
        'eligibility_screening_complete': '1', \
        'consent_form_complete': '2', \
        'enrollment_questionnaire_complete': '0'})
    False

    >>> redcap_registration_complete({ \
        'eligibility_screening_complete': '2', \
        'consent_form_complete': '2', \
        'enrollment_questionnaire_complete': '1'})
    False

    >>> redcap_registration_complete({ \
        'eligibility_screening_complete': '2', \
        'consent_form_complete': '2', \
        'enrollment_questionnaire_complete': '2'})
    True
    """
    if not redcap_record:
        return False

    return (is_complete('eligibility_screening', redcap_record) and \
            is_complete('consent_form', redcap_record) and \
            is_complete('enrollment_questionnaire', redcap_record))
