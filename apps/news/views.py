import json
import logging

from django.core import paginator
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render
from django.views import View
from django.http import HttpResponseNotFound
from django.conf import settings

from news import models, constants
from utils.json_fun import to_json_data
from utils.res_code import Code,error_map
from haystack.views import SearchView as _SearchView

logger=logging.getLogger('django')


class IndexView(View):
    '''
    create news index view
    '''
    def get(self,request):
        tags=models.Tag.objects.only('id','name').filter(is_delete=False)
        hot_news=models.HotNews.objects.select_related('news').only('news__title', 'news__image_url').filter(is_delete=False).order_by('priority', '-news__clicks')[0:constants.SHOW_HOTNEWS_COUNT]
        cn_page='index'
        return render(request,'news/index.html',locals())


class NewsListView(View):
    '''
    create news list view
    /news/
    1.获取前端传来的tag_id和page,并且捕获异常,记录error日志
    2.联合查询select_related(tag,author),只要('title', 'digest', 'image_url', 'update_time', 'tag__name', 'author__username')
    3.链式调用,过滤逻辑删除,tag_id不存在
    4.分页(对象列表,每一页的数据)
    5.生成当前页,并捕获异常,纪录info日志
    6.序列化输出
    7.返回数据给前端:data={total_pages,news}
    '''
    def get(self,request):
        #1.获取前端传参数
        try:
            tag_id=int(request.GET.get('tag_id',0))
        except Exception as e:
            logger.error('标签错误:\n{}'.format(e))
            tag_id=0
        try:
            page=int(request.GET.get('page',1))
        except Exception as e:
            logger.error('当前页数错误:\n{}'.format(e))
            page=1
        #2.联合查询
        news_queryset=models.News.objects.select_related('tag','author').only('id','title', 'digest', 'image_url', 'update_time', 'tag__name', 'author__username')
        #3.链式调用
        news=news_queryset.filter(is_delete=False,tag_id=tag_id) or news_queryset.filter(is_delete=False)
        #4.分页
        paginator=Paginator(news,per_page=constants.PER_PAGE_NEWS_COUNT)
        #5.生成当前页
        try:
            news_info=paginator.page(page)
        except EmptyPage:
            logger.info('用户访问的页数大于总页数')
            news_info=paginator.page(paginator.num_pages)
        #6.序列化输出
        news_info_list=[]
        for n in news_info:
            news_info_list.append({
                'id':n.id,
                'title':n.title,
                'digest':n.digest,
                'image_url': n.image_url,
                'tag_name': n.tag.name,
                'author': n.author.username,
                'update_time':n.update_time.strftime('%Y年%m月%d日 %H:%M')
            })
        data={
            'total_pages': paginator.num_pages,
            'news': news_info_list
        }

        return to_json_data(data=data)


class NewsBanner(View):
    '''
    create news banner view
    /news/banners/
    1.关联查询
    2.序列化输出
    3.返回数据给前端
    '''

    def get(self,request):
        banners=models.Banner.objects.select_related('news').only('news__image_url','news_id','news__title').filter(is_delete=False)[0:constants.SHOW_BANNER_COUNT]
        banners_info_list=[]
        for b in banners:
            banners_info_list.append({
                'image_url': b.image_url,
                'news_id': b.news.id,
                'news_title': b.news.title,
            })
        data={
            'banners':banners_info_list
        }
        return to_json_data(data=data)


class NewsDetailView(View):
    '''
    create news detail view
    /news/<int:news_id>
    1.联合查询新闻
    2.联合查询新闻评论
    3.序列化输出:comments_list.append(comm.to_dict_data())
    4.渲染页面
    5.如果新闻不存在,返回HttpResponseNotFound
    '''
    def get(self,request,news_id):
        news=models.News.objects.select_related('tag','author').only('title', 'content', 'update_time', 'tag__name', 'author__username').filter(is_delete=False,id=news_id).first()
        if news:
            comments=models.Comments.objects.select_related('author','parent').only('content','author__username','update_time','parent__content','parent__author__username','parent__update_time').filter(is_delete=False,news_id=news_id)
            comments_list=[]
            for comm in comments:
                comments_list.append(comm.to_dict_data())
            comments_num=len(comments_list)
            return render(request,'news/news_detail.html',locals())
        else:
            return HttpResponseNotFound('<h1>Page not found</h1>')


class NewsCommentView(View):
    '''
    create news comments view
    /news/<int:news_id>/comments/
    1.判断用户是否登录,错误返回错误信息
    2.判断新闻id是否存在,错误返回错误信息
    3.从前端获取参数,数据不存在返回错误信息
    4.判断评论内容是否为空,错误返回错误信息
    5.判断异常:判断是否有父评论,再判断是否为对应的news_id,返回错误信息,异常处理,记录日志,返回错误
    6.写入到数据库,判断父评论是否有,可以为空,但是不能为空字符串,返回数据给前端
    '''

    def post(self,request,news_id):
        if not request.user.is_authenticated:
            return to_json_data(errno=Code.SESSIONERR,errmsg=error_map[Code.SESSIONERR])
        if not models.News.objects.only('id').filter(is_delete=False,id=news_id).exists():
            return to_json_data(errno=Code.PARAMERR,errmsg='新闻不存在')

        json_data=request.body
        if not json_data:
            to_json_data(errno=Code.PARAMERR,errmsg=error_map[Code.PARAMERR])
        dict_data=json.loads(json_data.decode('utf8'))
        content=dict_data.get('content')
        if not dict_data.get('content'):
            return to_json_data(errno=Code.PARAMERR,errmsg='评论内容为空')

        parent_id=dict_data.get('parent_id')
        try:
            if parent_id:
                parent_id=int(parent_id)
                if not models.Comments.objects.only('id').filter(is_delete=False,news_id=news_id,id=parent_id):
                    return to_json_data(errno=Code.PARAMERR,errmsg=error_map[Code.PARAMERR])
        except Exception as e:
            logger.info('前端传来的parent_id异常:\n{}'.format(e))
            return to_json_data(errno=Code.PARAMERR,errmsg='未知异常')

        new_content=models.Comments()
        new_content.content=content
        new_content.author=request.user
        new_content.news_id=news_id
        new_content.parent_id=parent_id if parent_id else None
        new_content.save()

        return to_json_data(data=new_content.to_dict_data())


class SearchView(_SearchView):
    '''
    create news search view
    /search/
    1.指定模版文件
    2.接收前台传入的关键字参数,判断是否查询热门新闻还是查询指定新闻
    3.查询数据,进行分页
    4.异常处理:确定显示页数,判断是否为整型,是否超过最大页数
    5.模版渲染
    6.指定了参数指定搜索
    '''

    template='news/search.html'

    def create_response(self):

        kw=self.request.GET.get('q','')
        if not kw:
            show_all=True
            hot_news=models.HotNews.objects.select_related('news').only('news__title','news__image_url','news__id').filter(is_delete=False).order_by('priority','-news__clicks')
            paginator=Paginator(hot_news,settings.HAYSTACK_SEARCH_RESULTS_PER_PAGE)
            try:
                page=paginator.page(int(self.request.GET.get('page',1)))
            except PageNotAnInteger:
                page=paginator.page(1)
            except EmptyPage:
                page=paginator.page(paginator.num_pages)
            cn_page = 'search'
            return render(self.request,self.template,locals())

        else:
            show_all=False
            qs=super(SearchView,self).create_response()#隐藏了q与page
            return qs


















