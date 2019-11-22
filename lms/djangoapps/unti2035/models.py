# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.conf import settings
import requests
import re
from require import require

from django.db import models
from django.utils.translation import ugettext as _
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.core.exceptions import PermissionDenied
from openedx.core.djangoapps.xmodule_django.models import CourseKeyField
from opaque_keys.edx.keys import CourseKey
from social_django.models import UserSocialAuth


ERROR_MESSAGE = {
    400: 'Not enough parammeters in request',
    401: 'User is not authorized',
    403: 'User does not have access to the specified organization',
    404: 'User/course/organization does not exist',
    424: 'Error while enroll/unenroll user to course',
    500: 'Internal Server Error'
}

import logging
log = logging.getLogger(__name__)


class Uninersity2035Id(models.Model):
    class Meta:
        app_label = "unti2035"

    course_id = CourseKeyField(max_length=255, db_index=True, unique=True, verbose_name='Course ID')
    unti2035_id = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return "Course: {}".format(self.course_id)

class University2035Block():
    course_unti2035_id = 0
    unti2035_id = 0

    def __init__(self):
       self.enrolled = False
       self.has_access = False

    def get_course_id(self, course_id):
        if not self.course_unti2035_id:
            try:
                course = Uninersity2035Id.objects.get(course_id=course_id)
            except:
                try:
                    course_key = CourseKey.from_string(course_id)
                    course = Uninersity2035Id.objects.get(course_id=course_key)
                except:
                    log.error('Course {} not in University 2035'.format(course_id))

            try:
                self.course_unti2035_id = course.unti2035_id
            except:
                log.error('There is no {} in University 2035'.format(course_id))

        return self.course_unti2035_id

    def get_user_id(self, user):
        if not self.unti2035_id:
            try:
                user_auth_provider = UserSocialAuth.objects.get(user=user)
                prov = user_auth_provider.provider
                if prov == "university2035":
                    self.unti2035_id = user_auth_provider.extra_data['unti_id']
            except:
                log.error('User {} is not register on University 2035'.format(user.username))

        return self.unti2035_id

    @classmethod
    def can_enroll(self, user, course_id):
        course_unti2035_id = University2035Block().get_course_id(course_id)
        unti2035_id = University2035Block().get_user_id(user)

        data = {
            'unti_id': unti2035_id,
            'external_course_id': course_unti2035_id,
            'platform_id': settings.SOCIAL_AUTH_UNIVERSITY2035_KEY
        }

        resp = requests.get(
            u'{}/cat-enroll/api/v1/course/enroll/check/'.format(settings.API_UNTI_URL),
            params = data,
            headers = {'Authorization': 'Token {}'.format(settings.SOCIAL_AUTH_UNIVERSITY2035_API_KEY)}
        )

        if resp.status_code not in ERROR_MESSAGE:
            try:
                return {
                    'can_enroll': resp.json().get('can_enroll'),
                    'enroll_ticket': resp.json().get('enrol_ticket')
                }
            except:
                pass
        else:
            return HttpResponseBadRequest(_(ERROR_MESSAGE[resp.status_code]))


    @classmethod
    def enroll(self, user, course_id):
        spec_data = University2035Block().can_enroll(user, course_id)
        try:
            require(spec_data['can_enroll'])
        except:
            return False

        block = University2035Block()
        unti2035_id = block.get_user_id(user)
        course_unti2035_id = block.get_course_id(course_id)

        data = {
            'unti_id': unti2035_id,
            'external_course_id': course_unti2035_id,
            'platform_id': settings.SOCIAL_AUTH_UNIVERSITY2035_KEY,
            'enrol_ticket': spec_data['enroll_ticket']
        }

        resp = requests.post(
            u'{}/cat-enroll/api/v1/course/enroll/'.format(settings.API_UNTI_URL),
            data = data,
            headers = {
                'Authorization': 'Token {}'.format(settings.SOCIAL_AUTH_UNIVERSITY2035_API_KEY)
            }
        )

        _read_status_code(resp.status_code)


    @classmethod
    def unenroll(self, user, course_id):
        u = University2035Block()
        unti2035_id = u.get_user_id(user)
        course_unti2035_id = u.get_course_id(course_id)

        enrolled = u.check_status_enroll(unti2035_id, course_unti2035_id)
        if not enrolled:
            return False

        data = {
            'unti_id': unti2035_id,
            'external_course_id': course_unti2035_id,
            'platform_id': settings.SOCIAL_AUTH_UNIVERSITY2035_KEY
        }

        resp = requests.delete(
            u'{}/cat-enroll/api/v1/course/enroll/'.format(settings.API_UNTI_URL),
            data = data,
            headers = {
                'Authorization': 'Token {}'.format(settings.SOCIAL_AUTH_UNIVERSITY2035_API_KEY)
            }
        )

        _read_status_code(resp.status_code)


    def check_status_enroll(self, unti2035_id, course_unti2035_id):
        enrolled = False

        data = {
            'unti_id': unti2035_id,
            'external_course_id': course_unti2035_id,
            'platform_id': settings.SOCIAL_AUTH_UNIVERSITY2035_KEY
        }

        resp = requests.get(
            u'{}/cat-enroll/api/v1/course/enroll/'.format(settings.API_UNTI_URL),
            params = data,
            headers = {
                'Authorization': 'Token {}'.format(settings.SOCIAL_AUTH_UNIVERSITY2035_API_KEY)
            }
        )

        _read_status_code(resp.status_code)
        enrolled = resp.json().get('enrolled')
        return enrolled


def require(assertion):
    """
    Raises PermissionDenied if assertion is not true.
    """
    if not assertion:
        raise PermissionDenied


def _read_status_code(status):
    if status // 100 == 2:
        return True
    else:
        log.error("{}".format(_(ERROR_MESSAGE[status])))
