import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.musher_redcap import *

REDCAP_RECORD = {
    'record_id': '-1',
}

class TestLeadDawgs0(unittest.TestCase):
    """
    A test case where a PT has no recent encounters.
    """
    def setUp(self):
        self.recent_encounters = []
        self.instances = dict()
        self.instances['target'] = target = max_instance_testing_triggered(self.recent_encounters)
        self.instances['complete_tos'] = max_instance('test_order_survey',
            self.recent_encounters, since=target)
        self.instances['complete_kr'] = max_instance('kiosk_registration_4c7f',
            self.recent_encounters, since=target)
        self.instances['incomplete_kr'] = max_instance('kiosk_registration_4c7f',
            self.recent_encounters, since=target, complete=False)

    def test_instances(self):
        self.assertEqual(self.instances, {
            'target': None,
            'complete_tos': None,
            'complete_kr': None,
            'incomplete_kr': None,
        })

    def test_need_to_create_new_td_for_today(self):
        self.assertTrue(need_to_create_new_td_for_today(self.instances))

    def test_need_to_create_new_kr_instance(self):
        self.assertFalse(need_to_create_new_kr_instance(self.instances))

    def test_kiosk_registration_link(self):
        self.assertEqual(kiosk_registration_link(REDCAP_RECORD, self.instances),
            f"{REDCAP_BASE_URL}redcap_v{PROJECT.redcap_version}/DataEntry/index.php?"
            f"pid={PROJECT_ID}&id={REDCAP_RECORD['record_id']}"
            f"&arm=encounter_arm_1&event_id={EVENT_ID}&page=kiosk_registration_4c7f"
            f"&instance={get_todays_repeat_instance()}"
        )


class TestLeadDawgs1(unittest.TestCase):
    """
    A test case where a PT's testing was triggered on instance 7 (within past
    week) and neither a TOS or KR was complete on or after that instance.
    """
    def setUp(self):
        self.recent_encounters = [
            {
                'redcap_repeat_instance': '1',
                'testing_determination_complete': '2',
                'testing_trigger': 'No',
                'test_order_survey_complete': '',
                'kiosk_registration_4c7f_complete': ''
            }, {
                'redcap_repeat_instance': '2',
                'testing_determination_complete': '2',
                'testing_trigger': 'No',
                'test_order_survey_complete': '',
                'kiosk_registration_4c7f_complete': ''
            }, {
                'redcap_repeat_instance': '7',
                'testing_determination_complete': '2',
                'testing_trigger': 'Yes',
                'test_order_survey_complete': '',
                'kiosk_registration_4c7f_complete': ''
            }
        ]
        self.instances = dict()
        self.instances['target'] = target = max_instance_testing_triggered(self.recent_encounters)
        self.instances['complete_tos'] = max_instance('test_order_survey',
            self.recent_encounters, since=target)
        self.instances['complete_kr'] = max_instance('kiosk_registration_4c7f',
            self.recent_encounters, since=target)
        self.instances['incomplete_kr'] = max_instance('kiosk_registration_4c7f',
            self.recent_encounters, since=target, complete=False)

    def test_instances(self):
        self.assertEqual(self.instances, {
            'target': 7,
            'complete_tos': None,
            'complete_kr': None,
            'incomplete_kr': None,
        })

    def test_need_to_create_new_td_for_today(self):
        self.assertFalse(need_to_create_new_td_for_today(self.instances))

    def test_need_to_create_new_kr_instance(self):
        self.assertTrue(need_to_create_new_kr_instance(self.instances))

    def test_kiosk_registration_link(self):
        self.assertEqual(kiosk_registration_link(REDCAP_RECORD, self.instances),
            f"{REDCAP_BASE_URL}redcap_v{PROJECT.redcap_version}/DataEntry/index.php?"
            f"pid={PROJECT_ID}&id={REDCAP_RECORD['record_id']}"
            f"&arm=encounter_arm_1&event_id={EVENT_ID}&page=kiosk_registration_4c7f"
            f"&instance={self.instances['target']}"
        )

class TestLeadDawgs2(unittest.TestCase):
    """
    A test case where a PT's testing was triggered on instance 2 (within past
    week), there is no complete TOS on or after instance 2, but an incomplete KR
    exists after instance 2.
    """
    def setUp(self):
        self.recent_encounters = [
            {
                'redcap_repeat_instance': '1',
                'testing_determination_complete': '2',
                'testing_trigger': 'No',
                'test_order_survey_complete': '',
                'kiosk_registration_4c7f_complete': ''
            }, {
                'redcap_repeat_instance': '2',
                'testing_determination_complete': '2',
                'testing_trigger': 'Yes',
                'test_order_survey_complete': '',
                'kiosk_registration_4c7f_complete': ''
            }, {
                'redcap_repeat_instance': '7',
                'testing_determination_complete': '',
                'testing_trigger': '',
                'test_order_survey_complete': '',
                'kiosk_registration_4c7f_complete': '1'
            }
        ]
        self.instances = dict()
        self.instances['target'] = target = max_instance_testing_triggered(self.recent_encounters)
        self.instances['complete_tos'] = max_instance('test_order_survey',
            self.recent_encounters, since=target)
        self.instances['complete_kr'] = max_instance('kiosk_registration_4c7f',
            self.recent_encounters, since=target)
        self.instances['incomplete_kr'] = max_instance('kiosk_registration_4c7f',
            self.recent_encounters, since=target, complete=False)

    def test_instances(self):
        self.assertEqual(self.instances, {
            'target': 2,
            'complete_tos': None,
            'complete_kr': None,
            'incomplete_kr': 7,
        })

    def test_need_to_create_new_td_for_today(self):
        self.assertFalse(need_to_create_new_td_for_today(self.instances))

    def test_need_to_create_new_kr_instance(self):
        self.assertFalse(need_to_create_new_kr_instance(self.instances))

    def test_incomplete_kr_instance_is_not_none(self):
        self.assertTrue(self.instances['incomplete_kr'] is not None)

    def test_kiosk_registration_link(self):
        self.assertEqual(kiosk_registration_link(REDCAP_RECORD, self.instances),
            f"{REDCAP_BASE_URL}redcap_v{PROJECT.redcap_version}/DataEntry/index.php?"
            f"pid={PROJECT_ID}&id={REDCAP_RECORD['record_id']}"
            f"&arm=encounter_arm_1&event_id={EVENT_ID}&page=kiosk_registration_4c7f"
            f"&instance={self.instances['incomplete_kr']}"
        )

class TestLeadDawgs3(unittest.TestCase):
    """
    A test case where a PT's testing was triggered on instance 2 (within past
    week), there is a both a complete TOS and complete KR on or after instance
    2.
    """
    def setUp(self):
        self.recent_encounters = [
            {
                'redcap_repeat_instance': '1',
                'testing_determination_complete': '2',
                'testing_trigger': 'No',
                'test_order_survey_complete': '',
                'kiosk_registration_4c7f_complete': ''
            }, {
                'redcap_repeat_instance': '2',
                'testing_determination_complete': '2',
                'testing_trigger': 'Yes',
                'test_order_survey_complete': '',
                'kiosk_registration_4c7f_complete': ''
            }, {
                'redcap_repeat_instance': '7',
                'testing_determination_complete': '',
                'testing_trigger': '',
                'test_order_survey_complete': '2',
                'kiosk_registration_4c7f_complete': '2'
            }
        ]
        self.instances = dict()
        self.instances['target'] = target = max_instance_testing_triggered(self.recent_encounters)
        self.instances['complete_tos'] = max_instance('test_order_survey',
            self.recent_encounters, since=target)
        self.instances['complete_kr'] = max_instance('kiosk_registration_4c7f',
            self.recent_encounters, since=target)
        self.instances['incomplete_kr'] = max_instance('kiosk_registration_4c7f',
            self.recent_encounters, since=target, complete=False)

    def test_instances(self):
        self.assertEqual(self.instances, {
            'target': 2,
            'complete_tos': 7,
            'complete_kr': 7,
            'incomplete_kr': None,
        })

    def test_need_to_create_new_td_for_today(self):
        self.assertTrue(need_to_create_new_td_for_today(self.instances))

    def test_need_to_create_new_kr_instance(self):
        self.assertFalse(need_to_create_new_kr_instance(self.instances))

    def test_kiosk_registration_link(self):
        self.assertEqual(kiosk_registration_link(REDCAP_RECORD, self.instances),
            f"{REDCAP_BASE_URL}redcap_v{PROJECT.redcap_version}/DataEntry/index.php?"
            f"pid={PROJECT_ID}&id={REDCAP_RECORD['record_id']}"
            f"&arm=encounter_arm_1&event_id={EVENT_ID}&page=kiosk_registration_4c7f"
            f"&instance={get_todays_repeat_instance()}"
        )


class TestLeadDawgs4(unittest.TestCase):
    """
    A test case where a PT's testing was never triggered but they have a
    complete TOS and a complete KR in the past week.
    """
    def setUp(self):
        self.recent_encounters = [
            {
                'redcap_repeat_instance': str(one_week_ago() + 1),
                'testing_determination_complete': '2',
                'testing_trigger': 'No',
                'test_order_survey_complete': '',
                'kiosk_registration_4c7f_complete': ''
            }, {
                'redcap_repeat_instance': str(one_week_ago() + 2),
                'testing_determination_complete': '',
                'testing_trigger': '',
                'test_order_survey_complete': '',
                'kiosk_registration_4c7f_complete': '2'
            }, {
                'redcap_repeat_instance': str(one_week_ago() + 3),
                'testing_determination_complete': '',
                'testing_trigger': '',
                'test_order_survey_complete': '2',
                'kiosk_registration_4c7f_complete': ''
            }
        ]
        self.instances = dict()
        self.instances['target'] = target = max_instance_testing_triggered(self.recent_encounters)
        self.instances['complete_tos'] = max_instance('test_order_survey',
            self.recent_encounters, since=target)
        self.instances['complete_kr'] = max_instance('kiosk_registration_4c7f',
            self.recent_encounters, since=target)
        self.instances['incomplete_kr'] = max_instance('kiosk_registration_4c7f',
            self.recent_encounters, since=target, complete=False)

    def test_instances(self):
        self.assertEqual(self.instances, {
            'target': None,
            'complete_tos': one_week_ago() + 3,
            'complete_kr': one_week_ago() + 2,
            'incomplete_kr': None,
        })

    def test_need_to_create_new_td_for_today(self):
        self.assertTrue(need_to_create_new_td_for_today(self.instances))

    def test_need_to_create_new_kr_instance(self):
        self.assertFalse(need_to_create_new_kr_instance(self.instances))

    def test_kiosk_registration_link(self):
        self.assertEqual(kiosk_registration_link(REDCAP_RECORD, self.instances),
            f"{REDCAP_BASE_URL}redcap_v{PROJECT.redcap_version}/DataEntry/index.php?"
            f"pid={PROJECT_ID}&id={REDCAP_RECORD['record_id']}"
            f"&arm=encounter_arm_1&event_id={EVENT_ID}&page=kiosk_registration_4c7f"
            f"&instance={get_todays_repeat_instance()}"
        )


class TestLeadDawgs5(unittest.TestCase):
    """
    A test case where a PT received a mail test kit and was selected again for
    kiosk testing within the same week.
    """
    def setUp(self):
        self.recent_encounters = [
            {
                'redcap_repeat_instance': str(one_week_ago() + 1),
                'testing_determination_complete': '2',
                'testing_trigger': 'Yes',
                'test_order_survey_complete': '2',
                'kiosk_registration_4c7f_complete': ''
            }, {
                'redcap_repeat_instance': str(one_week_ago() + 2),
                'testing_determination_complete': '2',
                'testing_trigger': 'Yes',
                'test_order_survey_complete': '',
                'kiosk_registration_4c7f_complete': ''
            },
        ]
        self.instances = dict()
        self.instances['target'] = target = max_instance_testing_triggered(self.recent_encounters)
        self.instances['complete_tos'] = max_instance('test_order_survey',
            self.recent_encounters, since=target)
        self.instances['complete_kr'] = max_instance('kiosk_registration_4c7f',
            self.recent_encounters, since=target)
        self.instances['incomplete_kr'] = max_instance('kiosk_registration_4c7f',
            self.recent_encounters, since=target, complete=False)

    def test_instances(self):
        self.assertEqual(self.instances, {
            'target': one_week_ago() + 2,
            'complete_tos': None,
            'complete_kr': None,
            'incomplete_kr': None,
        })

    def test_need_to_create_new_td_for_today(self):
        self.assertFalse(need_to_create_new_td_for_today(self.instances))

    def test_need_to_create_new_kr_instance(self):
        self.assertTrue(need_to_create_new_kr_instance(self.instances))

    def test_kiosk_registration_link(self):
        self.assertEqual(kiosk_registration_link(REDCAP_RECORD, self.instances),
            f"{REDCAP_BASE_URL}redcap_v{PROJECT.redcap_version}/DataEntry/index.php?"
            f"pid={PROJECT_ID}&id={REDCAP_RECORD['record_id']}"
            f"&arm=encounter_arm_1&event_id={EVENT_ID}&page=kiosk_registration_4c7f"
            f"&instance={one_week_ago() + 2}"
        )
