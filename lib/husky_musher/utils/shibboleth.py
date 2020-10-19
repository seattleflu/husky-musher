from os import environ
from typing import Dict


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
