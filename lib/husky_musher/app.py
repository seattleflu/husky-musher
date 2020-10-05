import os
import json
import requests
from flask import Flask, redirect, request
from typing import Dict, Optional
from datetime import datetime, timedelta
from id3c.cli.redcap import is_complete


REDCAP_API_TOKEN = os.environ['REDCAP_API_TOKEN']
REDCAP_API_URL = os.environ['REDCAP_API_URL']
STUDY_START_DATE = datetime(2020, 9, 24) # Study start date of 2020-09-24
ERROR_MESSAGE = """
    <p>Error: Something went wrong. Please contact Husky Coronavirus Testing support by
    emailing <a href="mailto:huskytest@uw.edu">huskytest@uw.edu</a> or by calling
    <a href="tel:+12066162414">(206) 616-2414</a>.</p>
"""
app = Flask(__name__)


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


def extract_user_info(environ: dict) -> Dict[str, str]:
    """
    Extracts attributes of the authenticated user, provided by UW's IdP via our
    Shibboleth SP, from the request environment *environ*.

    Keys of the returned dict match those used by our REDCap project.
    """
    return {
        "netid": environ['uid'],

        # This won't always be @uw.edu.
        "email": environ.get("mail", ""),

        # Given name will include any middle initial/name.  Both name fields
        # will contain the preferred name parts, if set, otherwise the
        # administrative name parts.
        "core_participant_first_name": environ.get("givenName", ""),
        "core_participant_last_name":  environ.get("surname", ""),

        # Department is generally a colon-separated set of
        # increasingly-specific labels, starting with the School.
        "uw_school": environ.get("department", ""),

        **extract_affiliation(environ),
    }


def extract_affiliation(environ: dict) -> Dict[str, str]:
    """
    Transforms a multi-value affiliation string into our REDCap fields.

    Keys of the returned dict match those used by our REDCap project.

    >>> extract_affiliation({"unscoped-affiliation": "member;faculty;employee;alum"})
    {'affiliation': 'faculty', 'affiliation_other': ''}

    >>> extract_affiliation({"unscoped-affiliation": "member;student;staff"})
    {'affiliation': 'student', 'affiliation_other': ''}

    >>> extract_affiliation({"unscoped-affiliation": "member;faculty;student"})
    {'affiliation': 'student', 'affiliation_other': ''}

    >>> extract_affiliation({"unscoped-affiliation": "member;staff;alum"})
    {'affiliation': 'staff', 'affiliation_other': ''}

    >>> extract_affiliation({"unscoped-affiliation": "member;employee"})
    {'affiliation': 'staff', 'affiliation_other': ''}

    >>> extract_affiliation({"unscoped-affiliation": "member;affiliate;alum"})
    {'affiliation': 'other', 'affiliation_other': 'affiliate;alum'}

    >>> extract_affiliation({"unscoped-affiliation": "member"})
    {'affiliation': '', 'affiliation_other': ''}

    >>> extract_affiliation({})
    {'affiliation': '', 'affiliation_other': ''}
    """
    raw_affilations = environ.get("unscoped-affiliation", "")

    # "Member" is uninteresting and uninformative; a generic catch-all.
    # The empty string might arise from our fallback above.
    affiliations = set(raw_affilations.split(";")) - {"member",""}

    rules = [
        ("student"  in affiliations,    {"affiliation": "student",  "affiliation_other": ""}),
        ("faculty"  in affiliations,    {"affiliation": "faculty",  "affiliation_other": ""}),
        ("staff"    in affiliations,    {"affiliation": "staff",    "affiliation_other": ""}),
        ("employee" in affiliations,    {"affiliation": "staff",    "affiliation_other": ""}),
        (len(affiliations) > 0,         {"affiliation": "other",    "affiliation_other": ";".join(sorted(affiliations))}),
        (True,                          {"affiliation": "",         "affiliation_other": ""})]

    return next(result for condition, result in rules if condition)


# Always include a Cache-Control: no-store header in the response so browsers
# or intervening caches don't save pages across auth'd users.  Unlikely, but
# possible.  This is also appropriate so that users always get a fresh REDCap
# lookup.
@app.after_request
def set_cache_control(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route('/')
def main():
    # Get NetID and other attributes from Shibboleth data
    remote_user = request.remote_user
    user_info = extract_user_info(request.environ)

    if not (remote_user and user_info.get("netid")):
        app.logger.error('No remote user!')
        return ERROR_MESSAGE

    try:
        redcap_record = fetch_participant(user_info)

    except Exception as e:
        app.logger.warning(f'Failed to fetch REDCap data: {e}')
        return ERROR_MESSAGE

    if redcap_record is None:
        # If not in REDCap project, create new record
        try:
            new_record_id = register_participant(user_info)
            redcap_record = { 'record_id': new_record_id }
        except Exception as e:
            app.logger.warning(f'Failed to create new REDCap record: {e}')
            return ERROR_MESSAGE

    # Because of REDCap's survey queue logic, we can point a participant to an
    # upstream survey. If they've completed it, REDCap will automatically direct
    # them to the next, uncompleted survey in the queue.
    event = 'enrollment_arm_1'
    instrument = 'eligibility_screening'
    repeat_instance = None

    # If all enrollment event instruments are complete, point participants
    # to today's daily attestation instrument.
    # If the participant has already completed the daily attestation,
    # REDCap will prevent the participant from filling out the survey again.
    if is_complete('eligibility_screening', redcap_record) and \
        is_complete('consent_form', redcap_record) and \
        is_complete('enrollment_questionnaire', redcap_record):

        event = 'encounter_arm_1'
        instrument = 'daily_attestation'
        # Repeat instance number should be days since the start of the study,
        # with the first instance starting at 1.
        repeat_instance = 1 + (datetime.today() - STUDY_START_DATE).days

        if repeat_instance <= 0:
            # This should never happen!
            app.logger.error("Failed to create a valid repeat instance")
            return ERROR_MESSAGE

        if repeat_instance == 1:
            attestation_start = (STUDY_START_DATE + timedelta(days=1)).strftime("%B %d, %Y")
            return (f"""
                <p>Thank you for enrolling in Husky Coronavirus Testing!<br><br>
                Daily Check-ins start on {attestation_start}.<br>
                You will receive a daily reminder to complete your check-in via text or email.<br><br>
                If you have any questions or concerns, please reach out to us at:
                <a href="mailto:huskytest@uw.edu">huskytest@uw.edu</a></p>
            """)

    # Generate a link to the appropriate questionnaire, and then redirect.
    try:
        survey_link = generate_survey_link(redcap_record['record_id'], event, instrument, repeat_instance)

    except Exception as e:
        app.logger.warning(f'Failed to generate REDCap survey link: {e}')
        return ERROR_MESSAGE

    return redirect(survey_link)
