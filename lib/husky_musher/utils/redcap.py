import os
import json
import requests
from flask import request
from datetime import datetime, timedelta
from prometheus_client import CollectorRegistry, Summary
from typing import Dict, Optional, List
from urllib.parse import urlencode, urljoin
from id3c.cli.redcap import is_complete, Project
from diskcache import FanoutCache


DEVELOPMENT_MODE = os.environ.get("FLASK_ENV", "production") == "development"
REDCAP_API_URL = os.environ["HCT_REDCAP_API_URL"]
TIMEOUT = 30

if DEVELOPMENT_MODE:
    # Testing: HCT Year 3 Prototype
    PROJECT_ID = 139
    EVENT_ID = 721
    STUDY_START_DATE = datetime(2022, 7, 22) # Y3 test project start date
else:
    # Husky Coronavirus Testing 2022-2023
    PROJECT_ID = 148
    EVENT_ID = 745
    STUDY_START_DATE = datetime(2022, 7, 22) # Date testing opened for HCT Y3

# Load the RedCap project and fanout cache lazily. Initialize a container
# project so that if this file is run from the test suite, the test suite
#  can inject a dummy project into the container before a RedCap project
# is initialized. If instead this file is imported by the Flask application,
# it will load the connection to the RedCap project as determined by our
# environment configuration, as well as initializing the fanout cache. The
# fanout cache isn't used by either test suite, so is ignored during testing.
class LazyLoadContainer:
    def __init__(self) -> None:
        self.redcap_project = None
        self.cache = None

    def get_project(self):
        """load the desired redcap project if no project has been set"""
        if not self.redcap_project:
            self.redcap_project = Project(REDCAP_API_URL, PROJECT_ID)
        return self.redcap_project

    def get_cache(self):
        """lazy load cache so that doctests doesn't pick it up and break"""
        if not self.cache:
            self.cache = FanoutCache(os.environ.get("CACHE"))
        return self.cache

LazyObjects = LazyLoadContainer()

# These values in REDCap must be imported as their raw codes, not their label,
# else we get a 400 Client Error from REDCap when POSTing.
YES = '1'
KIOSK_WALK_IN = '4'
COMPLETE = '2'


METRIC_REGISTRY = CollectorRegistry()
METRIC_REDCAP_REQUEST_SECONDS = Summary(
    "redcap_request_seconds",
    "Time spent making requests to REDCap",
    labelnames = ["function"],
    registry = METRIC_REGISTRY,
)

# Declare this before using it so that it's always an exported metric, even if
# never called due to perfect caching.
METRIC_FETCH_PARTICIPANT = METRIC_REDCAP_REQUEST_SECONDS.labels("fetch_participant")

def metric_redcap_request_seconds(function_name = None):
    def decorator(function):
        return METRIC_REDCAP_REQUEST_SECONDS.labels(function_name or function.__name__).time()(function)
    return decorator


@metric_redcap_request_seconds("fetch_participant (cached)")
def fetch_participant(user_info: dict) -> Optional[Dict[str, str]]:
    """
    Exports a REDCap record matching the given *user_info*. Returns None if no
    match is found.

    Raises an :class:`AssertionError` if REDCap returns multiple matches for the
    given *user_info*.
    """
    netid = user_info["netid"]
    record = LazyObjects.get_cache().get(netid)

    if not record:
        with METRIC_FETCH_PARTICIPANT.time():
            fields = [
                'netid',
                'record_id',
                'eligibility_screening_complete',
                'consent_form_complete',
                'enrollment_questionnaire_complete',
            ]

            data = {
                'token': LazyObjects.get_project().api_token,
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

            response = requests.post(LazyObjects.get_project().api_url, data=data, timeout=TIMEOUT)
            response.raise_for_status()

            assert 'application/json' in response.headers.get('Content-Type'), "Unexpected content type " \
                f"≪{response.headers.get('Content-Type')}≫, expected ≪application/json≫."

            records = response.json()

            if len(records) == 0:
                return None

            assert len(records) == 1, "Multiple records exist with same NetID: " \
                f"{[ record['record_id'] for record in records ]}"

            record = records[0]

        if redcap_registration_complete(record):
            LazyObjects.get_cache()[netid] = record

    return record


@metric_redcap_request_seconds()
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
        'token': LazyObjects.get_project().api_token,
        'content': 'record',
        'format': 'json',
        'type': 'flat',
        'overwriteBehavior': 'normal',
        'forceAutoNumber': 'true',
        'data': json.dumps(records),
        'returnContent': 'ids',
        'returnFormat': 'json'
    }
    response = requests.post(LazyObjects.get_project().api_url, data=data, timeout=TIMEOUT)
    response.raise_for_status()

    assert 'application/json' in response.headers.get('Content-Type'), "Unexpected content type " \
        f"≪{response.headers.get('Content-Type')}≫, expected ≪application/json≫."

    records = response.json()

    assert len(records) == 1, f"{len(records)} records returned, expected 1."

    return records[0]

@metric_redcap_request_seconds()
def generate_survey_link(record_id: str, event: str, instrument: str, instance: int = None) -> str:
    """
    Returns a generated survey link for the given *instrument* within the
    *event* of the *record_id*.

    Will include the repeat *instance* if provided.
    """
    data = {
        'token': LazyObjects.get_project().api_token,
        'content': 'surveyLink',
        'format': 'json',
        'instrument': instrument,
        'event': event,
        'record': record_id,
        'returnFormat': 'json'
    }

    if instance:
        data['repeat_instance'] = str(instance)

    response = requests.post(LazyObjects.get_project().api_url, data=data, timeout=TIMEOUT)
    response.raise_for_status()

    assert 'text/html' in response.headers.get('Content-Type'), "Unexpected content type " \
        f"≪{response.headers.get('Content-Type')}≫, expected ≪text/html≫."

    return response.text


@metric_redcap_request_seconds()
def fetch_deleted_records(begin_time, end_time):
    """
    Returns the REDCap log records of REDCap records which have been deleted
    at some point between *begin_time* and *end_time*.
    """
    data = {
            'token': LazyObjects.get_project().api_token,
            'content': 'log',
            'logtype': 'record_delete',
            'user': '',
            'record': '',
            'beginTime': begin_time,
            'endTime': end_time,
            'format': 'json',
            'returnFormat': 'json'
        }

    response = post_and_validate_redcap_request(LazyObjects.get_project().api_url, data=data, timeout=TIMEOUT)

    assert 'application/json' in response.headers.get('Content-Type'), "Unexpected content type " \
        f"≪{response.headers.get('Content-Type')}≫, expected ≪application/json≫."

    return response.json()


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


@metric_redcap_request_seconds()
def fetch_encounter_events_past_week(redcap_record: dict) -> List[dict]:
    """
    Given a *redcap_record*, export the full list of related REDCap instances
    from the Encounter arm of the project that have occurred in the past week.
    """
    fields = [
        'record_id', 'testing_trigger', 'testing_determination_complete',
        'kiosk_registration_4c7f_complete', 'test_order_survey_complete', 'nasal_swab_q'
    ]
    # Unfortunately, despite its appearance in the returned response from REDCap,
    # `redcap_repeat_instance` is not a field we can query by when exporting
    # REDCap records. However, it does get returned when we request `record_id`
    # as a field.
    #
    # Additionally, the `dateRangeBegin` key in REDCap is not
    # useful to us, because all instances associated with a record are returned,
    # regardless of the instance's creation or modification date.
    data = {
        'token': LazyObjects.get_project().api_token,
        'content': 'record',
        'format': 'json',
        'type': 'flat',
        'csvDelimiter': '',
        'events': 'encounter_arm_1',
        'records': redcap_record["record_id"],
        'fields': ",".join(map(str, fields)),
        'rawOrLabel': 'label',
        'rawOrLabelHeaders': 'raw',
        'exportCheckboxLabel': 'false',
        'exportSurveyFields': 'false',
        'exportDataAccessGroups': 'false',
        'returnFormat': 'json'
    }

    response = requests.post(LazyObjects.get_project().api_url, data=data, timeout=TIMEOUT)
    response.raise_for_status()

    assert 'application/json' in response.headers.get('Content-Type'), "Unexpected content type " \
        f"≪{response.headers.get('Content-Type')}≫, expected ≪application/json≫."

    encounters = response.json()
    return [ e for e in encounters if e['redcap_repeat_instance'] >= one_week_ago() ]


def one_week_ago() -> int:
    """
    Return the REDCap instance instance currently representing one week ago.
    """
    return get_todays_repeat_instance() - 7


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


def max_instance(instrument: str, redcap_record: List[dict], since: int,
    complete: bool=True, required_field: str='') -> Optional[int]:
    """
    Returns the most recent instance number in a *redcap_record* on or after the
    given filter instance *since*. Filters also by events with an *instrument*
    marked according to the given variable *complete* (True filters for only
    completed instances, and False filters only for incomplete or unverified
    instances). The default value for *complete* is True.

    Returns None if no completed instrument is found.

    >>> max_instance('kiosk_registration_4c7f', [ \
        {'redcap_repeat_instance': '1', 'kiosk_registration_4c7f_complete': '2'}], \
        since=0)
    1

    >>> max_instance('kiosk_registration_4c7f', [ \
        {'redcap_repeat_instance': '1', 'kiosk_registration_4c7f_complete': ''}, \
        {'redcap_repeat_instance': '2', 'kiosk_registration_4c7f_complete': '1'}, \
        {'redcap_repeat_instance': '3', 'kiosk_registration_4c7f_complete': '0'}], \
        since=0)

    >>> max_instance('kiosk_registration_4c7f', [ \
        {'redcap_repeat_instance': '1', 'kiosk_registration_4c7f_complete': ''}, \
        {'redcap_repeat_instance': '2', 'kiosk_registration_4c7f_complete': '1'}, \
        {'redcap_repeat_instance': '3', 'kiosk_registration_4c7f_complete': '0'}], \
        since=0, complete=False)
    3

    >>> max_instance('kiosk_registration_4c7f', [ \
        {'redcap_repeat_instance': '1', 'kiosk_registration_4c7f_complete': '2'}, \
        {'redcap_repeat_instance': '2', 'kiosk_registration_4c7f_complete': '2'}, \
        {'redcap_repeat_instance': '3', 'kiosk_registration_4c7f_complete': '0'}], \
        since=2)
    2

    >>> max_instance('kiosk_registration_4c7f', [ \
        {'redcap_repeat_instance': '1', 'kiosk_registration_4c7f_complete': '0'}, \
        {'redcap_repeat_instance': '2', 'kiosk_registration_4c7f_complete': '0'}, \
        {'redcap_repeat_instance': '3', 'kiosk_registration_4c7f_complete': '2'}], \
        since=2, complete=False)
    2

    >>> max_instance('kiosk_registration_4c7f', [ \
        {'redcap_repeat_instance': '1', 'kiosk_registration_4c7f_complete': '2'}, \
        {'redcap_repeat_instance': '2', 'kiosk_registration_4c7f_complete': '2'}, \
        {'redcap_repeat_instance': '3', 'kiosk_registration_4c7f_complete': '0'}], \
        since=3)

    >>> max_instance('test_order_survey', [ \
        {'redcap_repeat_instance': '1', 'test_order_survey_complete': '1', \
            'kiosk_registration_4c7f_complete': ''}, \
        {'redcap_repeat_instance': '2', 'test_order_survey_complete': '', \
            'kiosk_registration_4c7f_complete': '2'}], \
        since=0)

    >>> max_instance('kiosk_registration_4c7f', [ \
        {'redcap_repeat_instance': '1', 'kiosk_registration_4c7f_complete': '2', 'nasal_swab_q': ''}, \
        {'redcap_repeat_instance': '2', 'kiosk_registration_4c7f_complete': '2', 'nasal_swab_q': ''}, \
        {'redcap_repeat_instance': '3', 'kiosk_registration_4c7f_complete': '0', 'nasal_swab_q': ''}], \
        since=1, complete=False, required_field='nasal_swab_q')

    >>> max_instance('kiosk_registration_4c7f', [ \
        {'redcap_repeat_instance': '1', 'kiosk_registration_4c7f_complete': '2', 'nasal_swab_q': ''}, \
        {'redcap_repeat_instance': '2', 'kiosk_registration_4c7f_complete': '2', 'nasal_swab_q': '2021-09-10'}, \
        {'redcap_repeat_instance': '3', 'kiosk_registration_4c7f_complete': '0', 'nasal_swab_q': '2021-09-11'}], \
        since=1, complete=False, required_field='nasal_swab_q')
    3

    >>> max_instance('kiosk_registration_4c7f', [ \
        {'redcap_repeat_instance': '1', 'kiosk_registration_4c7f_complete': '2', 'nasal_swab_q': '2021-09-09'}, \
        {'redcap_repeat_instance': '2', 'kiosk_registration_4c7f_complete': '2', 'nasal_swab_q': ''}, \
        {'redcap_repeat_instance': '3', 'kiosk_registration_4c7f_complete': '0', 'nasal_swab_q': '2021-09-11'}], \
        since=1, required_field='nasal_swab_q')
    1

    >>> max_instance('kiosk_registration_4c7f', [ \
        {'redcap_repeat_instance': '1', 'kiosk_registration_4c7f_complete': '2', 'nasal_swab_q': '2021-09-09'}, \
        {'redcap_repeat_instance': '2', 'kiosk_registration_4c7f_complete': '2', 'nasal_swab_q': '2021-09-10'}, \
        {'redcap_repeat_instance': '3', 'kiosk_registration_4c7f_complete': '0', 'nasal_swab_q': '2021-09-11'}], \
        since=1, required_field='nasal_swab_q')
    2

    """
    events_instrument_complete = [
        encounter
        for encounter in redcap_record
        if encounter[f"{instrument}_complete"] != ''
        and is_complete(instrument, encounter) == complete
        and (not required_field or encounter[required_field] != '')
    ]

    # Filter since the latest instance where testing was triggered.
    # If no instance exists, do not filter. Note: at this point in the code, we
    # already are only considering instances in the past week.
    if since is not None:
        events_instrument_complete = list(filter(
            lambda encounter: int(encounter['redcap_repeat_instance']) >= since,
            events_instrument_complete
        ))

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
        max_instance = max(int(event['redcap_repeat_instance']) for event in redcap_record)

    except KeyError:
        raise KeyError("Expected every event in the given *redcap_record* to contain a "
            "key for 'redcap_repeat_instance'")
    except ValueError:
        raise ValueError("Expected every event in the given *redcap_record* to contain a "
            "non-empty string for 'redcap_repeat_instance'")

    return max_instance


@metric_redcap_request_seconds()
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
        'testing_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'testing_determination_internal_complete': COMPLETE,
    }]

    data = {
        'token': LazyObjects.get_project().api_token,
        'content': 'record',
        'format': 'json',
        'type': 'flat',
        'overwriteBehavior': 'normal',
        'forceAutoNumber': 'false',
        'data': json.dumps(record),
        'returnContent': 'ids',
        'returnFormat': 'json'
    }

    response = requests.post(LazyObjects.get_project().api_url, data=data, timeout=TIMEOUT)
    response.raise_for_status()

    assert 'application/json' in response.headers.get('Content-Type'), "Unexpected content type " \
        f"≪{response.headers.get('Content-Type')}≫, expected ≪application/json≫."

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
    given *target_instance*.

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

    if instances['complete_tos'] != get_todays_repeat_instance():
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
           and no KR instance exists on or after the target TD instance.
        2. A complete TOS instance exists on or after the target TD instance,
           the TOS instance is not from today, and no KR instance exists on or
           after the target TD instance.

    *target_instance* is a TD instance number with [testing_trigger] = "Yes" in the
    past 7 days.

    *complete_tos_instance* is a TOS instance number marked complete on or after the
    given *target_instance*.

    *complete_kr_instance* is a KR instance number marked complete on or after the
    given *target_instance*.

    >>> need_to_create_new_kr_instance({'target': None, 'complete_tos': 1, 'complete_kr': 1, 'incomplete_kr': None})
    False

    >>> need_to_create_new_kr_instance({'target': 1, 'complete_tos': None, 'complete_kr': 1, 'incomplete_kr': None})
    False

    >>> need_to_create_new_kr_instance({'target': 1, 'complete_tos': 1, 'complete_kr': 1, 'incomplete_kr': None})
    False

    >>> need_to_create_new_kr_instance({'target': 1, 'complete_tos': None, 'complete_kr': None, 'incomplete_kr': None})
    True

    >>> need_to_create_new_kr_instance({'target': 1, 'complete_tos': None, 'complete_kr': None, 'incomplete_kr': 2})
    False

    >>> need_to_create_new_kr_instance({'target': 1, 'complete_tos': None, 'complete_kr': 1, 'incomplete_kr': None})
    False

    >>> need_to_create_new_kr_instance({'target': 1, \
        'complete_tos': get_todays_repeat_instance(), 'complete_kr': 1, 'incomplete_kr': None})
    False

    >>> need_to_create_new_kr_instance({'target': 1, \
        'complete_tos': get_todays_repeat_instance(), 'complete_kr': None, 'incomplete_kr': None})
    False
    """
    # Just to be safe, check to make sure we don't need to create a TD instance
    # for today instead.
    if need_to_create_new_td_for_today(instances):
        return False

    complete_tos_instance = instances['complete_tos']
    kr_exists = instances['complete_kr'] is not None or instances['incomplete_kr'] is not None


    if complete_tos_instance != get_todays_repeat_instance():
        return not kr_exists

    return False


def kiosk_registration_link(redcap_record: dict, instances: Dict[str, int]) -> str:
    """
    Given information about recent *instances* of a *redcap_record*, returns an
    internal link to the correct instance of a Kiosk Registration instrument
    according to the pre-determined logic flow.
    """
    incomplete_kr_instance = instances['incomplete_kr']

    if need_to_create_new_td_for_today(instances):
        # Create TD instance based on # of days since project start, but
        # only if this is not the testing project
        if LazyObjects.get_project().id != -1:
            create_new_testing_determination(redcap_record)

        instance = get_todays_repeat_instance()

    elif need_to_create_new_kr_instance(instances):
        instance = instances['target']

    elif incomplete_kr_instance is not None:
        instance = incomplete_kr_instance

    else:
        raise Exception("Logic error when generating survey links.")

    return generate_redcap_link(redcap_record, instance)


def generate_redcap_link(redcap_record: dict, instance: int):
    """
    Given a *redcap_record*, generate a link to the internal REDCap portal's
    Kiosk Registration form for the record's given REDCap repeat *instance*.
    """
    query = urlencode({
        'pid': LazyObjects.get_project().id,
        'id': redcap_record['record_id'],
        'arm': 'encounter_arm_1',
        'event_id': EVENT_ID,
        'page': 'kiosk_registration_4c7f',
        'instance': instance,
    })

    return urljoin(LazyObjects.get_project().base_url,
        f"redcap_v{LazyObjects.get_project().redcap_version}/DataEntry/index.php?{query}")


def post_and_validate_redcap_request(api_url, data, headers=None, timeout=300, max_retry_count=10):
    retry_count = 0

    # Added as workaround for REDCap API bug which incorrectly returns 200 status code
    # and HTML response with "unknown error" message and substring included below, which
    # in many cases succeeds with additional attempts.
    # -drr, 7/28/2021
    while retry_count <= max_retry_count:
        response = requests.post(api_url, data=data, headers=headers, timeout=timeout)
        if response.status_code==200 and 'multiple browser tabs of the same REDCap page. If that is not the case' in response.text:
            retry_count += 1
            continue
        break

    response.raise_for_status()
    return response
