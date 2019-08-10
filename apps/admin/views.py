import json
import logging
from datetime import datetime

from collections import OrderedDict
from urllib.parse import urlencode

from django.core.paginator import Paginator, EmptyPage
from django.db.models import Count
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views import View
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.models import Group, Permission

import qiniu

from admin import constants
from admin import forms
from admin.forms import CoursesPubForm
from course.models import Course, Teacher, CourseCategory
from news import models
from utils.json_fun import to_json_data
from utils.res_code import Code, error_map
from scripts import paginator_script
from utils.fastdfs.fdfs import FDFS_Client
from utils.secrets import qiniu_secret_info
from doc.models import Doc
from users.models import Users

logger = logging.getLogger('django')


class IndexView(LoginRequiredMixin, View):
    """
    create admin index view
    /admin/
    """

    def get(self, request):
        return render(request, 'admin/index/index.html')


class TagsManageView(PermissionRequiredMixin, View):
    """
    create tags manage view
    /admin/tags/
    """

    permission_required = ('news.add_tag', 'news.view_tag')

    def handle_no_permission(self):
        if self.request.method.lower() != 'get':
            return to_json_data(errno=Code.ROLEERR, errmsg='没有操作权限')
        else:
            return super(TagsManageView, self).handle_no_permission()

    def get(self, request):
        tags = models.Tag.objects.values('id', 'name').annotate(num_news=Count('news')).filter(
            is_delete=False).order_by('-num_news', 'update_time')
        return render(request, 'admin/news/tags_manage.html', locals())

    def post(self, request):
        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, error_map=[Code.PARAMERR])
        dict_data = json.loads(json_data.decode('utf8'))
        tag_name = dict_data.get('name')
        if tag_name and tag_name.replace(' ', ''):
            tag_name = tag_name.replace(' ', '')
            tag_tuple = models.Tag.objects.get_or_create(name=tag_name)
            tag_instance, tag_boolean = tag_tuple
            data = {
                'id': tag_instance.id,
                'name': tag_instance.name,
            }
            return to_json_data(data=data, errmsg='标签创建成功!') if tag_tuple[-1] else to_json_data(errno=Code.DATAEXIST,
                                                                                                errmsg='标签名已存在!')

        else:
            return to_json_data(errno=Code.PARAMERR, errmsg='标签名为空!')


class TagEditView(PermissionRequiredMixin, View):
    """
    create tag edit view
    /admin/<int:tag_id>/
    """
    permission_required = ('news.change_tag', 'news.delete_tag')

    def handle_no_permission(self):
        return to_json_data(errno=Code.ROLEERR, errmsg='没有操作权限')

    def put(self, request, tag_id):
        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=[Code.PARAMERR])
        dict_data = json.loads(json_data.decode('utf8'))
        tag_name = dict_data.get('name')
        tag = models.Tag.objects.only('id').filter(is_delete=False, id=tag_id).first()
        if tag:
            if tag_name and tag_name.replace(' ', ''):
                tag_name = tag_name.replace(' ', '')
                print(tag_name)
                if not models.Tag.objects.only('id').filter(name=tag_name).first():
                    tag.name = tag_name
                    tag.save(update_fields=['name'])
                    return to_json_data(errmsg='标签更新成功!')
                else:
                    return to_json_data(errno=Code.DATAEXIST, errmsg='标签名已存在!')
            else:
                return to_json_data(errmsg='输入的标签名为空!')

        else:
            return to_json_data(errno=Code.PARAMERR, errmsg='需要更新的标签不存在!')

    def delete(self, request, tag_id):
        tag = models.Tag.objects.only('id').filter(id=tag_id).first()
        if tag:
            tag.is_delete = True
            tag.save(update_fields=['is_delete'])
            return to_json_data(errmsg='标签删除成功')
        else:
            return to_json_data(errno=Code.PARAMERR, errmsg='需要删除的标签不存在')


class HotNewsManageView(PermissionRequiredMixin, View):
    permission_required = ('news.view_hotnews',)
    raise_exception = True

    def get(self, request):
        hot_news = models.HotNews.objects.select_related('news__tag').only('news__title', 'news__tag__name',
                                                                           'priority').filter(is_delete=False).order_by(
            'priority', '-news__clicks')[0:constants.SHOW_HOTNEWS_COUNT]

        return render(request, 'admin/news/news_hot.html', locals())


class HotNewsEditView(PermissionRequiredMixin, View):
    """
    create hotnews edit view
    /hotnews/<int:hotnews_id>/
    """
    permission_required = ('news.change_hotnews', 'news.delete_hotnews')
    raise_exception = True

    def handle_no_permission(self):
        if self.request.method.lower() != 'get':
            return to_json_data(errno=Code.ROLEERR, errmsg='没有操作权限')

    def delete(self, request, hotnews_id):
        hotnews = models.HotNews.objects.only('id').filter(id=hotnews_id).first()
        if hotnews_id:
            hotnews.is_delete = True
            hotnews.save(update_fields=['is_delete'])
            return to_json_data(errmsg='热门文章删除成功!')
        else:
            return to_json_data(errno=Code.PARAMERR, errmsg='需要删除的热门文章不存在!')

    def put(self, request, hotnews_id):
        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=[Code.PARAMERR])
        dict_data = json.loads(json_data.decode('utf8'))
        try:
            priority = int(dict_data.get('priority'))
            priority_list = [i for i, _ in models.HotNews.PRI_CHOICES]
            if priority not in priority_list:
                return to_json_data(errno=Code.PARAMERR, errmsg='不存在此优先级,重新输入!')

        except Exception as e:
            logger.info('优先级设置异常:{}'.format(e))
            return to_json_data(errno=Code.PARAMERR, errmsg='热门文章优先级设置错误!')

        hotnews = models.HotNews.objects.only('id').filter(id=hotnews_id).first()
        if not hotnews:
            return to_json_data(errno=Code.PARAMERR, errmsg='需要更新的热门文章不存在!')
        if hotnews.priority == priority:
            return to_json_data(errno=Code.PARAMERR, errmsg='优先级未改变!')

        hotnews.priority = priority
        hotnews.save(update_fields=['priority'])
        return to_json_data(errmsg='优先级修改成功!')


class HotNewsAddView(PermissionRequiredMixin, View):
    """
    create hotnews add view
    /admin/hotnes/add
    """
    permission_required = ('news.add_hotnews', 'news.view_hotnews')
    raise_exception = True

    def handle_no_permission(self):
        if self.request.method.lower() != 'get':
            return to_json_data(errno=Code.ROLEERR, errmsg='没有操作权限')
        else:
            return super(HotNewsAddView, self).handle_no_permission()

    def get(self, request):
        tags = models.Tag.objects.values('id', 'name').annotate(num_news=Count('news')).filter(
            is_delete=False).order_by('-num_news', 'update_time')
        priority_dict = OrderedDict(models.HotNews.PRI_CHOICES)
        return render(request, 'admin/news/news_hot_add.html', locals())

    def post(self, request):
        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=[Code.PARAMERR])
        dict_data = json.loads(json_data.decode('utf8'))
        try:
            news_id = int(dict_data.get('news_id'))
        except Exception as e:
            logger.info(errno=Code.PARAMERR, errmsg='参数错误')
        if not models.News.objects.filter(id=news_id).exists():
            return to_json_data(errno=Code.PARAMERR, errmsg='文章不存在')
        try:
            priority = int(dict_data.get('priority'))
            priority_list = [i for i, _ in models.HotNews.PRI_CHOICES]
            if priority not in priority_list:
                return to_json_data(errno=Code.PARAMERR, errmsg='热门文章的优先级设置错误')
        except Exception as e:
            logger.info('热门文章优先级异常：\n{}'.format(e))
            return to_json_data(errno=Code.PARAMERR, errmsg='热门文章的优先级设置错误')
        hotnews_tuple = models.HotNews.objects.get_or_create(news_id=news_id)
        hotnews, is_create = hotnews_tuple
        hotnews.priority = priority
        hotnews.save(update_fields=['priority'])
        return to_json_data(errmsg='热门文章创建成功')


class NewsByTagIdView(PermissionRequiredMixin, View):
    permission_required = ('news.view_news', 'news.add_hotnews')

    def get(self, request, tag_id):
        newses = models.News.objects.values('id', 'title').filter(is_delete=False, tag_id=tag_id)
        news_list = [i for i in newses]
        return to_json_data(data={'news': news_list})


class NewsManageView(PermissionRequiredMixin, View):
    """
    create news manage view
    /admin/news/
    """
    permission_required = ('news.add_news', 'news.view_news')
    raise_exception = True

    def get(self, request):

        # 查询所需字段
        tags = models.Tag.objects.only('id', 'name').filter(is_delete=False)
        newses = models.News.objects.only('id', 'title', 'author__username', 'update_time', 'tag__name').select_related(
            'tag', 'author').filter(is_delete=False)

        # 获取开始结束时间
        try:
            start_time = request.GET.get('start_time')
            start_time = datetime.strptime(start_time, '%Y/%m/%d') if start_time else ''
            end_time = request.GET.get('end_time')
            end_time = datetime.strptime(end_time, '%Y/%m/%d') if end_time else ''
        except Exception as e:
            logger.info('时间获取有误:{}'.format(e))
            start_time = end_time = ''

        # 根据时间过滤
        if start_time and not end_time:
            newses = newses.filter(update_time__lte=start_time)
        if end_time and not start_time:
            newses = newses.filter(update_time__gte=end_time)
        if start_time and end_time:
            newses = newses.filter(update_time__range=(start_time, end_time))

        # 根据title过滤
        title = request.GET.get('title', '')
        if title:
            newses = newses.filter(title__icontains=(title))

        # 根据作者名过滤
        author_name = request.GET.get('author_name', '')
        if author_name:
            newses = newses.filter(author__username__icontains=(author_name))

        # 根据tag_id过滤
        try:
            tag_id = int(request.GET.get('tag_id', 0))
        except Exception as e:
            logger.info('标签参数错误:{}'.format(e))
            tag_id = 0
        newses = newses.filter(tag_id=tag_id, is_delete=False) or newses.filter(is_delete=False)

        # 获取当前页码
        try:
            page = int(request.GET.get('page', 1))
        except Exception as e:
            logger.info('当前页获取错误:{}'.format(e))
            page = 1
        paginator = Paginator(newses, constants.PER_PAGE_NEWS_COUNT)

        # 获取当前页数据
        try:
            news_info = paginator.page(page)
        except EmptyPage:
            logger.info('用户访问页数大于总页数')
            news_info = paginator.page(paginator.num_pages)

        paginator_data = paginator_script.get_paginator_data(paginator, news_info)
        start_time = start_time.strftime('%Y/%m/%d') if start_time else ''
        end_time = end_time.strftime('%Y/%m/%d') if end_time else ''

        context = {
            'news_info': news_info,
            'tags': tags,
            'paginator': paginator,
            'start_time': start_time,
            'end_time': end_time,
            'title': title,
            'author_name': author_name,
            'tag_id': tag_id,
            'other_param': urlencode({
                'start_time': start_time,
                'end_time': end_time,
                'title': title,
                'author_name': author_name,
                'tag_id': tag_id,
            })
        }

        context.update(paginator_data)

        return render(request, 'admin/news/news_manage.html', context=context)


class NewsEditView(PermissionRequiredMixin, View):
    """
    create news manage view
    /admin/news/<int:news_id>/
    """
    permission_required = ('news.change_news', 'news.delete_news')
    raise_exception = True

    def get(self, request, news_id):
        """
        获取待编辑的文章
        """
        news = models.News.objects.filter(is_delete=False, id=news_id).first()
        if news:
            tags = models.Tag.objects.only('id', 'name').filter(is_delete=False)
            context = {
                'tags': tags,
                'news': news
            }
            return render(request, 'admin/news/news_pub.html', context=context)
        else:
            raise Http404('需要更新的文章不存在！')

    def delete(self, request, news_id):
        """
        删除文章
        """
        news = models.News.objects.only('id').filter(id=news_id).first()
        if news:
            news.is_delete = True
            news.save(update_fields=['is_delete'])
            return to_json_data(errmsg="文章删除成功")
        else:
            return to_json_data(errno=Code.PARAMERR, errmsg="需要删除的文章不存在")

    def put(self, request, news_id):
        """
        更新文章
        """
        news = models.News.objects.filter(is_delete=False, id=news_id).first()
        if not news:
            return to_json_data(errno=Code.NODATA, errmsg='需要更新的文章不存在')

        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])
        # 将json转化为dict
        dict_data = json.loads(json_data.decode('utf8'))

        form = forms.NewsPubForm(data=dict_data)
        if form.is_valid():
            news.title = form.cleaned_data.get('title')
            news.digest = form.cleaned_data.get('digest')
            news.content = form.cleaned_data.get('content')
            news.image_url = form.cleaned_data.get('image_url')
            news.tag = form.cleaned_data.get('tag')
            news.save()
            return to_json_data(errmsg='文章更新成功')
        else:
            # 定义一个错误信息列表
            err_msg_list = []
            for item in form.errors.get_json_data().values():
                err_msg_list.append(item[0].get('message'))
            err_msg_str = '/'.join(err_msg_list)  # 拼接错误信息为一个字符串

            return to_json_data(errno=Code.PARAMERR, errmsg=err_msg_str)


class NewsPubView(PermissionRequiredMixin, View):
    """
    create news pub view
    /admin/news/pub/
    """
    permission_required = ('news.add_news', 'news.view_news')
    raise_exception = True

    def get(self, request):
        tags = models.Tag.objects.only('id', 'name').filter(is_delete=False)
        return render(request, 'admin/news/news_pub.html', locals())

    def post(self, request):
        json_dict = request.body
        if not json_dict:
            return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])

        dict_data = json.loads(json_dict.decode('utf8'))
        form = forms.NewsPubForm(data=dict_data)
        if form.is_valid():
            news_instance = form.save(commit=False)
            news_instance.author_id = request.user.id
            news_instance.save()
            return to_json_data(errmsg='文章发布成功')
        else:
            # 定义一个错误信息列表
            err_msg_list = []
            for item in form.errors.get_json_data().values():
                err_msg_list.append(item[0].get('message'))
            err_msg_str = '/'.join(err_msg_list)  # 拼接错误信息为一个字符串

            return to_json_data(errno=Code.PARAMERR, errmsg=err_msg_str)


class NewsUploadImage(PermissionRequiredMixin, View):
    """
    create newsuploadimage view
    post：/admin/news/images/
    1.获取前端发送的文件
    2.判断是否有文件，是否为指定类型
    3.异常处理：取出图片扩展名，不存在指定为jpg
    4.异常处理：以二进制上传文件，指定上传文件类型
    5.否则：判断文件是否上传成功
    （1）上传响应属性Status不为Upload successed.则为上传失败
    （2）上传成功：取出文件名，与FASTDFS指定域名进行拼接
    （3）返回前端文件url
    """
    permission_required = ('news.add_news',)

    def post(self, request):
        image_file = request.FILES.get('image_file')
        if not image_file:
            logger.info('从前端获取图片失败')
            return to_json_data(errno=Code.NODATA, errmsg=error_map[Code.NODATA])
        if image_file.content_type not in ('image/jpg', 'image/jpeg', 'image/gif', 'image/png'):
            return to_json_data(errno=Code.DATAERR, errmsg=error_map[Code.DATAERR])
        try:
            image_ext_name = image_file.name.split('.')[-1]
        except Exception as e:
            logger.info('图片扩展名异常:{}'.format(e))
            image_ext_name = 'jpg'

        try:
            upload_res = FDFS_Client.upload_by_buffer(image_file.read(), file_ext_name=image_ext_name)
        except Exception as e:
            logger.error('图片上传出现异常:{}'.format(e))
            return to_json_data(errno=Code.UNKOWNERR, errmsg='图片上传异常')
        else:
            if upload_res.get('Status') != 'Upload successed.':
                logger.info('图片上传到FastDFS服务器失败')
                return to_json_data(Code.UNKOWNERR, errmsg='图片上传到服务器失败')

            else:
                image_name = upload_res.get('Remote file_id')
                image_url = settings.FASTDFS_SERVER_DOMAIN + image_name
                return to_json_data(data={'image_url': image_url}, errmsg='图片上传成功')


class UploadToken(View):
    """
    create uploadqiniu view
    /admin/token/
    """

    def get(self, request):
        access_key = qiniu_secret_info.QI_NIU_ACCESS_KEY
        secret_key = qiniu_secret_info.QI_NIU_SECRET_KEY
        bucket_name = qiniu_secret_info.QI_NIU_BUCKET_NAME
        # 构建鉴权对象
        q = qiniu.Auth(access_key, secret_key)
        token = q.upload_token(bucket_name)

        return JsonResponse({"uptoken": token})


class MarkDownUploadImage(View):

    def post(self, request):
        image_file = request.FILES.get('editormd-image-file')
        if not image_file:
            logger.info('从前端获取图片失败')
            return JsonResponse({'success': 0, 'message': '从前端获取图片失败'})
        if image_file.content_type not in ('image/jpg', 'image/jpeg', 'image/gif', 'image/png'):
            return JsonResponse({'success': 0, 'message': '不能上传非图片文件'})
        try:
            image_ext_name = image_file.name.split('.')[-1]
        except Exception as e:
            logger.info('图片扩展名异常:{}'.format(e))
            image_ext_name = 'jpg'

        try:
            upload_res = FDFS_Client.upload_by_buffer(image_file.read(), file_ext_name=image_ext_name)
        except Exception as e:
            logger.error('图片上传出现异常:{}'.format(e))
            return JsonResponse({'success': 0, 'message': '图片上传异常'})
        else:
            if upload_res.get('Status') != 'Upload successed.':
                logger.info('图片上传到FastDFS服务器失败')
                return JsonResponse({'success': 0, 'message': '图片上传服务器失败'})

            else:
                image_name = upload_res.get('Remote file_id')
                image_url = settings.FASTDFS_SERVER_DOMAIN + image_name
                return JsonResponse({'success': 1, 'message': '图片上传成功', 'url': image_url})


class BannerManageView(PermissionRequiredMixin, View):
    permission_required = ('news.view_banner',)
    raise_exception = True

    def get(self, request):
        priority_dict = OrderedDict(models.Banner.PRI_CHOICES)
        banners = models.Banner.objects.only('image_url', 'priority').filter(is_delete=False)
        return render(request, 'admin/news/news_banner.html', locals())


class BannerEditView(PermissionRequiredMixin, View):
    permission_required = ('news.delete_banner', 'news.change_banner')
    raise_exception = True

    def delete(self, request, banner_id):
        banner = models.Banner.objects.only('id').filter(id=banner_id).first()
        if banner:
            banner.is_delete = True
            banner.save(update_fields=['is_delete'])
            return to_json_data(errmsg='轮播图删除成功')

        else:
            return to_json_data(errno=Code.PARAMERR, errmsg='需要删除的轮播图不存在')

    def put(self, request, banner_id):
        banner = models.Banner.objects.only('id').filter(id=banner_id).first()
        if not banner:
            return to_json_data(errno=Code.PARAMERR, errmsg='需要更新的轮播图不存在')

        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])

        dict_data = json.loads(json_data.decode('utf8'))
        try:
            priority = int(dict_data.get('priority'))
            priority_list = [i for i, _ in models.Banner.PRI_CHOICES]
            if priority not in priority_list:
                return to_json_data(errno=Code.PARAMERR, errmsg='轮播图的优先级设置错误')
        except Exception as e:
            logger.info('轮播图优先级异常：\n{}'.format(e))
            return to_json_data(errno=Code.PARAMERR, errmsg='轮播图的优先级设置错误')

        image_url = dict_data.get('image_url')
        if not image_url:
            return to_json_data(errno=Code.PARAMERR, errmsg='轮播图url为空')

        banner.image_url = image_url
        banner.priority = priority
        banner.save(update_fields=['image_url', 'priority'])

        return to_json_data(errmsg='轮播图更新成功')


class BannerAddView(PermissionRequiredMixin, View):
    """
    create banner view
    /admin/banners/
    """
    permission_required = ('news.delete_banner', 'news.change_banner', 'news.view_banner')
    raise_exception = True

    def get(self, request):
        tags = models.Tag.objects.values('name', 'id').annotate(num_news=Count('news')).filter(
            is_delete=False).order_by('-num_news', 'update_time')
        priority_dict = OrderedDict(models.Banner.PRI_CHOICES)
        return render(request, 'admin/news/news_banner_add.html', locals())

    def post(self, request):
        json_dict = request.body
        if not json_dict:
            return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])

        dict_data = json.loads(json_dict.decode('utf8'))

        try:
            news_id = int(dict_data.get('news_id'))
        except Exception as e:
            logger.info('前端传过来的文章id参数异常：\n{}'.format(e))
            return to_json_data(errno=Code.PARAMERR, errmsg='参数错误')
        if not models.News.objects.filter(id=news_id).exists():
            return to_json_data(errno=Code.PARAMERR, errmsg='文章不存在')

        try:
            priority = int(dict_data.get('priority'))
            priority_list = [i for i, _ in models.Banner.PRI_CHOICES]
            if priority not in priority_list:
                return to_json_data(errno=Code.PARAMERR, errmsg='轮播图优先级设置错误')
        except Exception as e:
            logger.info('轮播图优先级异常：\n{}'.format(e))
            return to_json_data(errno=Code.PARAMERR, errmsg='轮播图的优先级设置错误')
        image_url = dict_data.get('image_url')
        if not image_url:
            return to_json_data(errno=Code.PARAMERR, errmsg='轮播图url为空')

        ban_tup = models.Banner.objects.get_or_create(news_id=news_id)

        banner, is_created = ban_tup

        banner.image_url = image_url
        banner.priority = priority
        banner.save(update_fields=['image_url', 'priority'])
        return to_json_data(errmsg='轮播图创建成功')


class DocsManageView(PermissionRequiredMixin, View):
    """
    route: /admin/docs/
    """
    permission_required = ('doc.view_doc', 'doc.add_doc')
    raise_exception = True

    def get(self, request):
        docs = Doc.objects.only('title', 'create_time').filter(is_delete=False)
        return render(request, 'admin/doc/docs_manage.html', locals())


class DocsEditView(PermissionRequiredMixin, View):
    """
    route: /admin/docs/<int:doc_id>/
    """
    permission_required = ('doc.change_doc', 'doc.delete_doc')
    raise_exception = True

    def get(self, request, doc_id):
        """
        """
        doc = Doc.objects.filter(is_delete=False, id=doc_id).first()
        if doc:
            tags = Doc.objects.only('id', 'name').filter(is_delete=False)
            context = {
                'doc': doc
            }
            return render(request, 'admin/doc/docs_pub.html', context=context)
        else:
            raise Http404('需要更新的文章不存在！')

    def delete(self, request, doc_id):
        doc = Doc.objects.filter(is_delete=False, id=doc_id).first()
        if doc:
            doc.is_delete = True
            doc.save(update_fields=['is_delete'])
            return to_json_data(errmsg="文档删除成功")
        else:
            return to_json_data(errno=Code.PARAMERR, errmsg="需要删除的文档不存在")

    def put(self, request, doc_id):
        doc = Doc.objects.filter(is_delete=False, id=doc_id).first()
        if not doc:
            return to_json_data(errno=Code.NODATA, errmsg='需要更新的文档不存在')

        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])
        # 将json转化为dict
        dict_data = json.loads(json_data.decode('utf8'))

        form = forms.DocsPubForm(data=dict_data)
        if form.is_valid():
            doc.title = form.cleaned_data.get('title')
            doc.desc = form.cleaned_data.get('desc')
            doc.file_url = form.cleaned_data.get('file_url')
            doc.image_url = form.cleaned_data.get('image_url')
            doc.save()
            return to_json_data(errmsg='文档更新成功')
        else:
            # 定义一个错误信息列表
            err_msg_list = []
            for item in form.errors.get_json_data().values():
                err_msg_list.append(item[0].get('message'))
            err_msg_str = '/'.join(err_msg_list)  # 拼接错误信息为一个字符串

            return to_json_data(errno=Code.PARAMERR, errmsg=err_msg_str)


class DocsPubView(PermissionRequiredMixin, View):
    """
    route: /admin/news/pub/
    """
    permission_required = ('doc.add_doc', 'news.view_doc')
    raise_exception = True

    def get(self, request):

        return render(request, 'admin/doc/docs_pub.html', locals())

    def post(self, request):
        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])
        # 将json转化为dict
        dict_data = json.loads(json_data.decode('utf8'))

        form = forms.DocsPubForm(data=dict_data)
        if form.is_valid():
            docs_instance = form.save(commit=False)
            docs_instance.author_id = request.user.id
            docs_instance.save()
            return to_json_data(errmsg='文档创建成功')
        else:
            # 定义一个错误信息列表
            err_msg_list = []
            for item in form.errors.get_json_data().values():
                err_msg_list.append(item[0].get('message'))
            err_msg_str = '/'.join(err_msg_list)  # 拼接错误信息为一个字符串

            return to_json_data(errno=Code.PARAMERR, errmsg=err_msg_str)


class DocsUploadFile(PermissionRequiredMixin, View):
    """route: /admin/docs/files/
    """
    permission_required = ('doc.add_doc',)

    def post(self, request):
        text_file = request.FILES.get('text_file')
        if not text_file:
            logger.info('从前端获取文件失败')
            return to_json_data(errno=Code.NODATA, errmsg='从前端获取文件失败')

        if text_file.content_type not in ('application/octet-stream', 'application/pdf',
                                          'application/zip', 'text/plain', 'application/x-rar', 'application/msword',
                                          'application/vnd.ms-excel'):
            return to_json_data(errno=Code.DATAERR, errmsg='不能上传非文本文件')

        try:
            text_ext_name = text_file.name.split('.')[-1]
        except Exception as e:
            logger.info('文件拓展名异常：{}'.format(e))
            text_ext_name = 'pdf'

        try:
            upload_res = FDFS_Client.upload_by_buffer(text_file.read(), file_ext_name=text_ext_name)
        except Exception as e:
            logger.error('文件上传出现异常：{}'.format(e))
            return to_json_data(errno=Code.UNKOWNERR, errmsg='文件上传异常')
        else:
            if upload_res.get('Status') != 'Upload successed.':
                logger.info('文件上传到FastDFS服务器失败')
                return to_json_data(Code.UNKOWNERR, errmsg='文件上传到服务器失败')
            else:
                text_name = upload_res.get('Remote file_id')
                text_url = settings.FASTDFS_SERVER_DOMAIN + text_name
                return to_json_data(data={'text_file': text_url}, errmsg='文件上传成功')


class CoursesManageView(PermissionRequiredMixin, View):
    """
    route: /admin/courses/
    """
    permission_required = ('course.add_course', 'course.view_course')
    raise_exception = True

    def get(self, request):
        courses = Course.objects.select_related('category', 'teacher').only('title', 'category__name',
                                                                            'teacher__name').filter(is_delete=False)
        return render(request, 'admin/course/courses_manage.html', locals())


class CoursesEditView(PermissionRequiredMixin, View):
    """
    route: /admin/courses/<int:course_id>/
    """
    permission_required = ('course.change_course', 'course.delete_course')
    raise_exception = True

    def get(self, request, course_id):
        course = Course.objects.filter(id=course_id, is_delete=False).first()
        if course:
            teachers = Teacher.objects.only('name').filter(is_delete=False)
            categories = CourseCategory.objects.only('name').filter(is_delete=False)
            return render(request, 'admin/course/courses_pub.html', locals())

        else:
            raise Http404('需要更新的课程不存在')

    def delete(self, request, course_id):
        course = Course.objects.filter(id=course_id).first()
        if course:
            course.is_delete = True
            course.save(update_fields=['is_delete'])
            return to_json_data(errmsg='课程删除成功')
        else:
            return to_json_data(errno=Code.PARAMERR, errmsg='需要删除的课程不存在')

    def put(self, request, course_id):
        course = Course.objects.filter(is_delete=False, id=course_id).first()
        if not course:
            return to_json_data(errno=Code.NODATA, errmsg='需要更新的课程不存在')
        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])
        # 将json转化为dict
        dict_data = json.loads(json_data.decode('utf8'))
        form = CoursesPubForm(data=dict_data)
        if form.is_valid():
            for attr, value in form.cleaned_data.items():
                setattr(course, attr, value)
            course.save()
            return to_json_data(errmsg='课程更新成功')
        else:
            # 定义一个错误信息列表
            err_msg_list = []
            for item in form.errors.get_json_data().values():
                err_msg_list.append(item[0].get('message'))
            err_msg_str = '/'.join(err_msg_list)  # 拼接错误信息为一个字符串

            return to_json_data(errno=Code.PARAMERR, errmsg=err_msg_str)


class CoursesPubView(PermissionRequiredMixin, View):
    """
    route: /admin/courses/pub/
    """
    permission_required = ('course.add_course', 'course.view_course')
    raise_exception = True

    def get(self, request):
        teachers = Teacher.objects.only('name').filter(is_delete=False)
        categories = CourseCategory.objects.only('name').filter(is_delete=False)
        return render(request, 'admin/course/courses_pub.html', locals())

    def post(self, request):
        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])
        dict_data = json.loads(json_data.decode('utf8'))

        form = forms.CoursesPubForm(data=dict_data)
        if form.is_valid():
            courses_instance = form.save()
            return to_json_data(errmsg='课程发布成功')

        else:
            # 定义一个错误信息列表
            err_msg_list = []
            for item in form.errors.get_json_data().values():
                err_msg_list.append(item[0].get('message'))
            err_msg_str = '/'.join(err_msg_list)  # 拼接错误信息为一个字符串

            return to_json_data(errno=Code.PARAMERR, errmsg=err_msg_str)


class GroupsManageView(PermissionRequiredMixin, View):
    """
    route: /admin/groups/
    """
    permission_required = ('auth.add_group', 'auth.view_group')
    raise_exception = True

    def handle_no_permission(self):
        if self.request.method.lower() != 'get':
            return to_json_data(errno=Code.ROLEERR, errmsg='没有操作权限')
        else:
            return super(GroupsManageView, self).handle_no_permission()

    def get(self, request):

        groups = Group.objects.values('id', 'name').annotate(num_users=Count('user')). \
            order_by('-num_users', 'id')
        return render(request, 'admin/user/groups_manage.html', locals())


class GroupsEditView(PermissionRequiredMixin, View):
    """
    route: /admin/groups/<int:group_id>/
    """
    permission_required = ('auth.change_group', 'auth.delete_group')
    raise_exception = True

    def handle_no_permission(self):
        if self.request.method.lower() != 'get':
            return to_json_data(errno=Code.ROLEERR, errmsg='没有操作权限')
        else:
            return super(GroupsEditView, self).handle_no_permission()

    def get(self, request, group_id):
        """
        """
        group = Group.objects.filter(id=group_id).first()
        if group:
            permissions = Permission.objects.only('id').all()
            return render(request, 'admin/user/groups_add.html', locals())
        else:
            raise Http404('需要更新的组不存在！')

    def delete(self, request, group_id):
        group = Group.objects.filter(id=group_id).first()
        if group:
            group.permissions.clear()  # 清空权限
            group.delete()
            return to_json_data(errmsg="用户组删除成功")
        else:
            return to_json_data(errno=Code.PARAMERR, errmsg="需要删除的用户组不存在")

    def put(self, request, group_id):
        group = Group.objects.filter(id=group_id).first()
        if not group:
            return to_json_data(errno=Code.NODATA, errmsg='需要更新的用户组不存在')

        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])
        # 将json转化为dict
        dict_data = json.loads(json_data.decode('utf8'))

        # 取出组名，进行判断
        group_name = dict_data.get('name', '').strip()
        if not group_name:
            return to_json_data(errno=Code.PARAMERR, errmsg='组名为空')

        if group_name != group.name and Group.objects.filter(name=group_name).exists():
            return to_json_data(errno=Code.DATAEXIST, errmsg='组名已存在')

        # 取出权限
        group_permissions = dict_data.get('group_permissions')
        if not group_permissions:
            return to_json_data(errno=Code.PARAMERR, errmsg='权限参数为空')

        try:
            permissions_set = set(int(i) for i in group_permissions)
        except Exception as e:
            logger.info('传的权限参数异常：\n{}'.format(e))
            return to_json_data(errno=Code.PARAMERR, errmsg='权限参数异常')

        all_permissions_set = set(i.id for i in Permission.objects.only('id'))
        if not permissions_set.issubset(all_permissions_set):
            return to_json_data(errno=Code.PARAMERR, errmsg='有不存在的权限参数')

        existed_permissions_set = set(i.id for i in group.permissions.all())
        if group_name == group.name and permissions_set == existed_permissions_set:
            return to_json_data(errno=Code.DATAEXIST, errmsg='用户组信息未修改')
        # 设置权限
        for perm_id in permissions_set:
            p = Permission.objects.get(id=perm_id)
            group.permissions.add(p)
        group.name = group_name
        group.save()
        return to_json_data(errmsg='组更新成功！')


class GroupsAddView(PermissionRequiredMixin, View):
    """
    route: /admin/groups/add/
    """
    permission_required = ('auth.add_group', 'auth.view_group')
    raise_exception = True

    def handle_no_permission(self):
        if self.request.method.lower() != 'get':
            return to_json_data(errno=Code.ROLEERR, errmsg='没有操作权限')
        else:
            return super(GroupsAddView, self).handle_no_permission()

    def get(self, request):
        permissions = Permission.objects.only('id').all()

        return render(request, 'admin/user/groups_add.html', locals())

    def post(self, request):
        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])
        dict_data = json.loads(json_data.decode('utf8'))

        # 取出组名，进行判断
        group_name = dict_data.get('name', '').strip()
        if not group_name:
            return to_json_data(errno=Code.PARAMERR, errmsg='组名为空')

        one_group, is_created = Group.objects.get_or_create(name=group_name)
        if not is_created:
            return to_json_data(errno=Code.DATAEXIST, errmsg='组名已存在')

        # 取出权限
        group_permissions = dict_data.get('group_permissions')
        if not group_permissions:
            return to_json_data(errno=Code.PARAMERR, errmsg='权限参数为空')

        try:
            permissions_set = set(int(i) for i in group_permissions)
        except Exception as e:
            logger.info('传的权限参数异常：\n{}'.format(e))
            return to_json_data(errno=Code.PARAMERR, errmsg='权限参数异常')

        all_permissions_set = set(i.id for i in Permission.objects.only('id'))
        if not permissions_set.issubset(all_permissions_set):
            return to_json_data(errno=Code.PARAMERR, errmsg='有不存在的权限参数')

        # 设置权限
        for perm_id in permissions_set:
            p = Permission.objects.get(id=perm_id)
            one_group.permissions.add(p)

        one_group.save()
        return to_json_data(errmsg='组创建成功！')


class UsersManageView(PermissionRequiredMixin, View):
    """
    route: /admin/users/
    """
    permission_required = ('users.add_users', 'users.view_users')
    raise_exception = True

    def handle_no_permission(self):
        if self.request.method.lower() != 'get':
            return to_json_data(errno=Code.ROLEERR, errmsg='没有操作权限')
        else:
            return super(UsersManageView, self).handle_no_permission()

    def get(self,request):
        users=Users.objects.only('username','is_superuser','is_staff').filter(is_active=True)
        return render(request,'admin/user/users_manage.html',locals())

class UsersEditView(PermissionRequiredMixin, View):
    """
    route: /admin/users/<int:user_id>/
    """
    permission_required = ('users.change_users', 'users.delete_users')
    raise_exception = True

    def handle_no_permission(self):
        if self.request.method.lower() != 'get':
            return to_json_data(errno=Code.ROLEERR, errmsg='没有操作权限')
        else:
            return super(UsersEditView, self).handle_no_permission()

    def get(self, request, user_id):
        user_instance = Users.objects.filter(id=user_id).first()
        if user_instance:
            groups = Group.objects.only('name').all()
            return render(request, 'admin/user/users_edit.html', locals())
        else:
            raise Http404('需要更新的用户不存在！')

    def delete(self, request, user_id):
        # user_instance = Users.objects.filter(id=user_id).first()
        # if user_instance:
        #     user_instance.groups.clear()  # 清除用户组
        #     user_instance.user_permissions.clear()  # 清除用户权限
        #     user_instance.is_active = False  # 设置为不激活状态
        #     user_instance.save()
        #     return to_json_data(errmsg="用户删除成功")
        # else:
        #     return to_json_data(errno=Code.PARAMERR, errmsg="需要删除的用户不存在")
        user_instance=Users.objects.filter(id=user_id).first()
        if user_instance:
            user_instance.groups.clear()
            user_instance.user_permissions.clear()
            user_instance.is_active=False
            user_instance.save()
            return to_json_data(errmsg='用户删除成功')

        else:
            return to_json_data(errno=Code.PARAMERR,errmsg='需要删除的用户不存在')




    def put(self, request, user_id):
        user_instance = Users.objects.filter(id=user_id).first()
        if not user_instance:
            return to_json_data(errno=Code.NODATA, errmsg='需要更新的用户不存在')

        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])
        # 将json转化为dict
        dict_data = json.loads(json_data.decode('utf8'))

        # 取出参数，进行判断

        try:
            groups = dict_data.get('groups')
            is_staff = int(dict_data.get('is_staff'))
            is_superuser = int(dict_data.get('is_superuser'))
            is_active = int(dict_data.get('is_active'))
            permissions=(is_staff,is_superuser,is_active)
            if not all([p in(0,1) for p in permissions]):
                return to_json_data(errno=Code.PARAMERR, errmsg='参数错误')
        except Exception as e:
            logger.info('从前端获取参数出现异常：\n{}'.format(e))
            return to_json_data(errno=Code.PARAMERR, errmsg='参数错误')
        try:
            groups_set=set(int(i) for i in groups) if groups else set()
        except Exception as e:
            logger.info('传的用户组参数异常：\n{}'.format(e))
            return to_json_data(errno=Code.PARAMERR, errmsg='用户组参数异常')
        all_groups_set=(i.id for i in Group.objects.only('id'))
        if not groups_set.issubset(all_groups_set):
            return to_json_data(errno=Code.PARAMERR, errmsg='有不存在的用户组参数')
        gs=Group.objects.filter(id__in=groups_set)
        user_instance.groups.clear()
        user_instance.groups.set(gs)
        user_instance.save()
        return to_json_data(errmsg='用户信息更新成功！')


















