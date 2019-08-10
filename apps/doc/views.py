import requests, logging

from django.shortcuts import render
from django.views import View
from django.http import Http404, FileResponse
from django.conf import settings
from django.utils.encoding import escape_uri_path

from doc.models import Doc

logger = logging.getLogger('django')


def doc_index(request):
    '''
    create doc_index view
    /docs/
    '''
    docs = Doc.objects.defer('update_time', 'create_time', 'author', 'is_delete').filter(is_delete=False)
    cn_page='doc'
    return render(request, 'doc/docDownload.html', locals())


class DocDownload(View):
    '''
    create doc download view
    /docs/<int:doc_id>/
    1.获取前端传来的参数，获取到文件下载地址
    2.如果存在，构造下载地址，不存在返回错误信息
    3.异常处理，记录日志
    4.处理文档数据类型
    5.为下载的文件命名
    '''

    def get(self, request, doc_id):
        doc = Doc.objects.only('file_url').filter(is_delete=False, id=doc_id).first()
        if doc:
            doc_url = doc.file_url
            # download_url = settings.SITE_DOMAIN_PORT + doc_url
            doc_name = doc.title
            try:
                # res=FileResponse(open(doc.file_url,'rb'))存在问题!
                res = FileResponse(requests.get(doc_url,stream=True))
            except Exception as e:
                logger.info('获取文档出现异常\n{}'.format(e))
                raise Http404('文档下载异常')
            doc_type = doc_url.split('.')[-1]
            if not doc_type:
                raise Http404('文档url异常!')
            else:
                doc_type = doc_type.lower()
            if doc_type == "pdf":
                res["Content-type"] = "application/pdf"
            elif doc_type == "zip":
                res["Content-type"] = "application/zip"
            elif doc_type == "doc":
                res["Content-type"] = "application/msword"
            elif doc_type == "xls":
                res["Content-type"] = "application/vnd.ms-excel"
            elif doc_type == "docx":
                res["Content-type"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            elif doc_type == "ppt":
                res["Content-type"] = "application/vnd.ms-powerpoint"
            elif doc_type == "pptx":
                res["Content-type"] = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

            else:
                raise Http404('文档格式不正确!')

            # doc_filename=escape_uri_path(doc_url.split('/')[-1])
            # res["Content-Disposition"]= "attachment; filename*=UTF-8''{}".format(doc_filename)
            d_url=doc_name+'.'+doc_type
            down_url=escape_uri_path(d_url)
            res["Content-Disposition"]= "attachment; filename*=UTF-8''{}".format(down_url)
            return res

        else:
            raise Http404('文档不存在!')


