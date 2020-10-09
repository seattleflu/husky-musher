import os
import json
import requests
from flask import request
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from id3c.cli.redcap import is_complete


REDCAP_API_TOKEN = os.environ['REDCAP_API_TOKEN']
REDCAP_API_URL = os.environ['REDCAP_API_URL']
STUDY_START_DATE = datetime(2020, 9, 24) # Study start date of 2020-09-24

# These values in REDCap must be imported as their raw codes, not their label,
# else we get a 400 Client Error from REDCap when POSTing.
YES = '1'
KIOSK_WALK_IN = '4'
COMPLETE = '2'

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


def fetch_encounter_events_past_week(redcap_record: dict) -> List[dict]:
    """
    Given a *redcap_record*, export the full list of related REDCap instances
    from the Encounter arm of the project that have occurred in the past week.
    """
    # Unfortunately, despite its appearance in the returned response from REDCap,
    # `redcap_repeat_instance` is not a field we can query by when exporting
    # REDCap records. Thus, return all information from a REDCap record (without
    # specifying fields) to retrieve the instance key.
    data = {
        'token': REDCAP_API_TOKEN,
        'content': 'record',
        'format': 'json',
        'type': 'flat',
        'csvDelimiter': '',
        'events': 'encounter_arm_1',
        'filterLogic': f'[record_id] = "{redcap_record["record_id"]}"',
        'rawOrLabel': 'label',
        'rawOrLabelHeaders': 'raw',
        'exportCheckboxLabel': 'false',
        'exportSurveyFields': 'false',
        'exportDataAccessGroups': 'false',
        'returnFormat': 'json'
    }

    response = requests.post(REDCAP_API_URL, data=data)
    response.raise_for_status()

    encounters = response.json()
    one_week_ago = get_todays_repeat_instance() - 7
    return [ e for e in encounters if e['redcap_repeat_instance'] >= one_week_ago ]


def max_instance_testing_triggered(redcap_record: List[dict]) -> Optional[int]:
    """
    Returns the most recent instance number in a *redcap_record* with
    `testing_trigger` = "Yes".

    Returns None if no such instances exist.
    """
    events_testing_trigger_yes = [
        encounter
        for encounter in redcap_record
        if encounter['testing_trigger'] == 'Yes'
    ]

    if not events_testing_trigger_yes:
        return None

    return _max_instance(events_testing_trigger_yes)


def max_instance(instrument: str, redcap_record: List[dict],
    complete: bool=True) -> Optional[int]:
    """
    Returns the most recent instance number in a *redcap_record* with an
    *instrument* marked according to the given variable *complete* (True filters
    for only completed instances, and False filters only for incomplete or
    unverified instances). The default value for *complete* is True.

    Returns None if no completed insrument is found.

    >>> max_instance('kiosk_registration_4c7f', [ \
        {'redcap_repeat_instance': '1', 'kiosk_registration_4c7f_complete': '2'}])
    1

    >>> max_instance('kiosk_registration_4c7f', [ \
        {'redcap_repeat_instance': '1', 'kiosk_registration_4c7f_complete': ''}, \
        {'redcap_repeat_instance': '2', 'kiosk_registration_4c7f_complete': '1'}, \
        {'redcap_repeat_instance': '3', 'kiosk_registration_4c7f_complete': '0'}])

    >>> max_instance('kiosk_registration_4c7f', [ \
        {'redcap_repeat_instance': '1', 'kiosk_registration_4c7f_complete': '2'}, \
        {'redcap_repeat_instance': '2', 'kiosk_registration_4c7f_complete': '2'}, \
        {'redcap_repeat_instance': '3', 'kiosk_registration_4c7f_complete': '0'}])
    2

    >>> max_instance('test_order_survey', [ \
        {'redcap_repeat_instance': '1', 'test_order_survey_complete': '1'}, \
        {'redcap_repeat_instance': '2', 'kiosk_registration_4c7f_complete': '2'}])
    """
    events_instrument_complete = [
        encounter
        for encounter in redcap_record
        if is_complete(instrument, encounter)
    ]

    if not events_instrument_complete:
        return None

    return _max_instance(events_instrument_complete)


def _max_instance(redcap_record: List[dict]) -> int:
    """
    Internal helper method for :func:`max_instance`. Returns the repeat instance
    number associated with the most recent encounter in the given
    *redcap_record* data.

    Assumes that every event in the given *redcap_record* has a non-empty value
    for 'redcap_repeat_instance'. Raises a :class:`KeyError` if
    'redcap_repeat_instance' is missing, or a :class:`ValueError` if
    'redcap_repeat_instance' is an empty string.

    Assumes that the given *redcap_record* contains at least one event with
    an associated 'redcap_repeat_instance'. Otherwise, throws a
    :class:`ValueError`.

    >>> _max_instance([ \
        {'redcap_repeat_instance': '1'}, {'redcap_repeat_instance': '2'}, \
        {'redcap_repeat_instance': '5'}, {'redcap_repeat_instance': '10'}])
    10

    >>> _max_instance([{'redcap_repeat_instance': '0'}])
    0

    >>> _max_instance([])
    Traceback (most recent call last):
    ...
    ValueError: Expected non-empty *redcap_record*

    >>> _max_instance([{'some_key': 'a value'}])
    Traceback (most recent call last):
    ...
    KeyError: "Expected every event in the given *redcap_record* to contain a key for 'redcap_repeat_instance'"

    >>> _max_instance([{'redcap_repeat_instance': ''}])
    Traceback (most recent call last):
    ...
    ValueError: Expected every event in the given *redcap_record* to contain a non-empty string for 'redcap_repeat_instance'
    """
    if len(redcap_record) == 0:
        raise ValueError("Expected non-empty *redcap_record*")

    try:
        max_instance = int(redcap_record[0]['redcap_repeat_instance'])

        for i in range(1, len(redcap_record)):
            instance_number = int(redcap_record[i]['redcap_repeat_instance'])
            max_instance = max(max_instance, instance_number)

    except KeyError:
        raise KeyError("Expected every event in the given *redcap_record* to contain a "
            "key for 'redcap_repeat_instance'")
    except ValueError:
        raise ValueError("Expected every event in the given *redcap_record* to contain a "
            "non-empty string for 'redcap_repeat_instance'")

    return max_instance


def create_new_testing_determination(redcap_record: dict):
    """
    Given a *redcap_record* to import, creates a new Testing Determination form
    instance with some pre-filled data fit for a kiosk walk-in.

    Raises an :class:`AssertionError` if the REDCap record import did not update
    exactly one record.
    """
    record = [{
        'record_id': redcap_record['record_id'],
        'redcap_event_name': 'encounter_arm_1',
        'redcap_repeat_instance': str(get_todays_repeat_instance()),
        'testing_trigger': YES,
        'testing_type': KIOSK_WALK_IN,
        'testing_date': str(datetime.today().date()),
        'testing_determination_internal_complete': COMPLETE,
    }]

    data = {
        'token': REDCAP_API_TOKEN,
        'content': 'record',
        'format': 'json',
        'type': 'flat',
        'overwriteBehavior': 'normal',
        'forceAutoNumber': 'false',
        'data': json.dumps(record),
        'returnContent': 'ids',
        'returnFormat': 'json'
    }

    response = requests.post(REDCAP_API_URL, data=data)
    response.raise_for_status()

    assert len(response.json()) == 1, \
        f"REDCap updated {len(response.json())} records, expected 1."


def need_to_create_new_td_for_today(instances: Dict[str, int]) -> bool:
    """
    Returns True if we need to create a new TD instance for today. Otherwise,
    returns False.

    We need to create a new TD instance for today in the following conditions:
        1. No TD instance with [testing_trigger] = "Yes" exists in the past 7
           days.
        2. No complete TOS instance exists on or after the target TD instance,
           and a complete KR instance exists on or after the target TD instance.
        3. A complete TOS instance exists on or after the target TD instance,
           the TOS instance is not from today, and a complete KR instance exists
           on or after the target TD instance.

    *target_instance* is a TD instance number with [testing_trigger] = "Yes" in the
    past 7 days.

    *complete_tos_instance* is a TOS instance number marked complete on or after the
    given *target_instance*.

    *complete_kr_instance* is a KR instance number marked complete on or after the
    given *target_intance*.

    >>> need_to_create_new_td_for_today({'target': None, 'complete_tos': 1, 'complete_kr': 1})
    True

    >>> need_to_create_new_td_for_today({'target': 1, 'complete_tos': None, 'complete_kr': 1})
    True

    >>> need_to_create_new_td_for_today({'target': 1, 'complete_tos': 1, 'complete_kr': 1})
    True

    >>> need_to_create_new_td_for_today({'target': 1, 'complete_tos': None, 'complete_kr': None})
    False

    >>> need_to_create_new_td_for_today({'target': 1, 'complete_tos': None, 'complete_kr': 1})
    True

    >>> need_to_create_new_td_for_today({'target': 1, \
        'complete_tos': get_todays_repeat_instance(), 'complete_kr': 1})
    False

    >>> need_to_create_new_td_for_today({'target': 1, \
        'complete_tos': get_todays_repeat_instance(), 'complete_kr': None})
    False
    """
    if not instances['target']:
        return True

    complete_tos_instance = instances['complete_tos']
    if complete_tos_instance is None \
        or (complete_tos_instance is not None \
            and complete_tos_instance != get_todays_repeat_instance()):
        if instances['complete_kr'] is not None:
            return True

    return False


def need_to_create_new_kr_instance(instances: Dict[str, int]) -> bool:
    """
    Returns True if we need to create a new KR instance for the target TD
    instance. Otherwise, returns False.

    We need to create a new KR instance in the following conditions. Both of
    these conditions assume a TD instance with [testing_trigger] = "Yes" exists
    in the past 7 days.
        1. No complete TOS instance exists on or after the target TD instance,
           and no complete KR instance exists on or after the target TD instance.
        2. A complete TOS instance exists on or after the target TD instance,
           the TOS instance is not from today, and no complete KR instance
           exists on or after the target TD instance.

    *target_instance* is a TD instance number with [testing_trigger] = "Yes" in the
    past 7 days.

    *complete_tos_instance* is a TOS instance number marked complete on or after the
    given *target_instance*.

    *complete_kr_instance* is a KR instance number marked complete on or after the
    given *target_intance*.

    >>> need_to_create_new_kr_instance({'target': None, 'complete_tos': 1, 'complete_kr': 1})
    False

    >>> need_to_create_new_kr_instance({'target': 1, 'complete_tos': None, 'complete_kr': 1})
    False

    >>> need_to_create_new_kr_instance({'target': 1, 'complete_tos': 1, 'complete_kr': 1})
    False

    >>> need_to_create_new_kr_instance({'target': 1, 'complete_tos': None, 'complete_kr': None})
    True

    >>> need_to_create_new_kr_instance({'target': 1, 'complete_tos': None, 'complete_kr': 1})
    False

    >>> need_to_create_new_kr_instance({'target': 1, \
        'complete_tos': get_todays_repeat_instance(), 'complete_kr': 1})
    False

    >>> need_to_create_new_kr_instance({'target': 1, \
        'complete_tos': get_todays_repeat_instance(), 'complete_kr': None})
    False
    """
    # Just to be safe, check to make sure we don't need to create a TD instance
    # for today instead.
    complete_tos_instance = instances['complete_tos']

    if need_to_create_new_td_for_today(instances):
        return False

    if complete_tos_instance is None \
        or (complete_tos_instance is not None \
            and complete_tos_instance != get_todays_repeat_instance()):
        return instances['complete_kr'] is None

    return False


def kiosk_registration_link(redcap_record: dict, instances: Dict[str, int]) -> str:
    """
    Given information about recent *instances* of a REDCap record, returns an
    appropriate survey link to the correct instance of a Kiosk Registration
    instrument according to the pre-determined logic flow.
    """
    record_id = redcap_record['record_id']
    event = 'encounter_arm_1'
    instrument = 'kiosk_registration_4c7f'

    if need_to_create_new_td_for_today(instances):
        # Create TD instance based on # of days since project start.
        create_new_testing_determination(redcap_record)

        # Generate a link to the KR, and then redirect.
        survey_link = generate_survey_link(record_id, event, instrument,
            get_todays_repeat_instance())

    elif need_to_create_new_kr_instance(instances):
        # Generate a link to the target instance, and then redirect.
        survey_link = generate_survey_link(record_id, event, instrument,
            instances['target'])

    elif incomplete_kr_instance is not None:
        # Generate a link to the existing KR that is incomplete, and then redirect.
        survey_link = generate_survey_link(record_id, event, instrument,
            instances['incomplete_kr'])

    else:
        raise Exception("Logic error when generating survey links.")

    return survey_link
