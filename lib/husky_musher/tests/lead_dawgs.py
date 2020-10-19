import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.redcap import *


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
