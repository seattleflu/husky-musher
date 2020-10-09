import json
from flask import Flask, redirect, request
from .utils.shibboleth import *
from .utils.redcap import *


ERROR_MESSAGE = """
    <p>Error: Something went wrong. Please contact Husky Coronavirus Testing support by
    emailing <a href="mailto:huskytest@uw.edu">huskytest@uw.edu</a> or by calling
    <a href="tel:+12066162414">(206) 616-2414</a>.</p>
"""
app = Flask(__name__)


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
    if redcap_registration_complete(redcap_record):
        event = 'encounter_arm_1'
        instrument = 'daily_attestation'
        repeat_instance = get_todays_repeat_instance()

        if repeat_instance <= 0:
            # This should never happen!
            app.logger.error("Failed to create a valid repeat instance")
            return ERROR_MESSAGE

        if repeat_instance == 1:
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
