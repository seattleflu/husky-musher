"""
Automates the survey flow and logic for when a participant walks up to a kiosk
for an observed nasal swab.

Glossary:
=========
PT = participant
TD = Testing Determination instrument
TOS = Test Order Survey insrument
KR = Kiosk Registration instrument
"""
import re
import json
from flask import Flask, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException, InternalServerError
from .utils.shibboleth import *
from .utils.redcap import *


app = Flask(__name__)


# Always include a Cache-Control: no-store header in the response so browsers
# or intervening caches don't save pages across auth'd users.  Unlikely, but
# possible.  This is also appropriate so that users always get a fresh REDCap
# lookup.
@app.after_request
def set_cache_control(response):
    response.headers["Cache-Control"] = "no-store"
    return response

@app.errorhandler(404)
def page_not_found(error):
    return render_template('page_not_found.html'), 404

@app.errorhandler(HTTPException)
def handle_http_error(error):
    app.logger.warning(f'POST to REDCap API failed: {error}')
    return render_template('something_went_wrong.html'), error.code

@app.errorhandler(InternalServerError)
def handle_500_error(error):
    app.logger.warning(f'Unexpected error occurred: {error}')
    return render_template('something_went_wrong.html'), 500

@app.route('/')
def main():
    # Get NetID and other attributes from Shibboleth data
    remote_user = request.remote_user
    user_info = extract_user_info(request.environ)

    if not (remote_user and user_info.get("netid")):
        app.logger.error('No remote user!')
        raise

    redcap_record = fetch_participant(user_info)

    if redcap_record is None:
        # If not in REDCap project, create new record
        new_record_id = register_participant(user_info)
        redcap_record = { 'record_id': new_record_id }

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
    if redcap_registration_complete(redcap_record):
        event = 'encounter_arm_1'
        instrument = 'daily_attestation'
        repeat_instance = get_todays_repeat_instance()

        if repeat_instance <= 0:
            # This should never happen!
            app.logger.error("Failed to create a valid repeat instance")
            raise

        if repeat_instance == 1:
            return (f"""
                <p>Thank you for enrolling in Husky Coronavirus Testing!<br><br>
                Daily Check-ins start on {attestation_start}.<br>
                You will receive a daily reminder to complete your check-in via text or email.<br><br>
                If you have any questions or concerns, please reach out to us at:
                <a href="mailto:huskytest@uw.edu">huskytest@uw.edu</a></p>
            """)

    # Generate a link to the appropriate questionnaire, and then redirect.
    survey_link = generate_survey_link(redcap_record['record_id'], event, instrument, repeat_instance)
    return redirect(survey_link)


@app.route('/kiosk')
def kiosk():
    return render_template('kiosk.html')

@app.route('/kiosk/lookup', methods=['GET'])
def redirect_to_kiosk():
    return redirect(url_for('.kiosk'))

@app.route('/kiosk/lookup', methods=['POST'])
def lookup():
    # Sanitize inputs
    netid = re.sub('\W', '', request.form['netid'])
    redcap_record = fetch_participant({ 'netid': netid })

    # Check if PT is already reigstered
    registration_complete = redcap_registration_complete(redcap_record)
    if not registration_complete:
        # Give PT info on how to register
        return render_template('registration_required.html', netid=netid,
            redcap_record_exists=redcap_record is not None,
            registration_complete=registration_complete)

    # Fetch all encounter events in the past 7 days.
    recent_encounters = fetch_encounter_events_past_week(redcap_record)

    # Track noteworthy instances used in survey generation logic
    instances: Dict[str, int] = dict()

    # Look for most recent TD with testing_trigger = 'Yes'
    instances['target'] = max_instance_testing_triggered(recent_encounters)
    # Check if TOS exists and is marked complete on or after this instance.
    instances['complete_tos'] = max_instance('test_order_survey', recent_encounters,
        since=instances['target'])
    # Check for KRs on or after this instance.
    instances['complete_kr'] = max_instance('kiosk_registration_4c7f', recent_encounters,
        since=instances['target'])
    instances['incomplete_kr'] = max_instance('kiosk_registration_4c7f', recent_encounters,
        since=instances['target'], complete=False)

    if instances['complete_tos'] == get_todays_repeat_instance():
        # We won't test this PT twice in one day
        return render_template('test_already_sent.html', netid=netid)

    return redirect(kiosk_registration_link(redcap_record, instances))
