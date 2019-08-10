import logging

from django.http import Http404
from django.shortcuts import render
from django.views import View

from course import models

logger = logging.getLogger('django')


def course_list(request):
    """
    create course_list view
    /courses/
    """
    courses = models.Course.objects.only('title', 'cover_url', 'teacher__positional_title').filter(is_delete=False)
    cn_page='course'
    return render(request, 'course/course.html', locals())


class CourseDetailView(View):
    """
    create course detail view
    /courses/<int:course_id>/
    """
    def get(self, request, course_id):
        try:
            course = models.Course.objects.only('title', 'cover_url', 'video_url', 'profile', 'outline',
                                                'teacher__name', 'teacher__avatar_url', 'teacher__positional_title',
                                                'teacher__profile').get(is_delete=False, id=course_id)
            return render(request, 'course/course_detail.html', locals())
        except models.Course.DoesNotExist as e:
            logger.info('当前课程出现如下异常：\n{}'.format(e))
            raise Http404('此课程不存在')
