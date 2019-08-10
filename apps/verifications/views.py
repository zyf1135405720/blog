import logging
import json
import string

import random

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View
from django_redis import get_redis_connection

from utils.captcha.captcha import captcha
from utils.yuntongxun.sms import CCP
from utils.json_fun import to_json_data
from utils.res_code import Code, error_map
from verifications import constants
from users.models import Users
from verifications.forms import CheckImgCodeForm,CheckImgCodeForm1

logger = logging.getLogger('django')

#生成图片验证码
class ImageCode(View):
    '''
    send image_code
    /image_codes/<uuid:image_code_id>/

    1.创建对应类视图
    2.从前端获参数:验证码对应的uuid与后台生成的验证码形成键值对存入redis
    3.校验参数
    4.生成图片验证码文本信息以及二进制的图片信息
    5.将前端传入的唯一image_code_id与图片文本信息写入reids
    6.将生成的图片返回到前端
    '''

    def get(self, request, image_code_id):
        text, image = captcha.generate_captcha()  # 生成的是元组
        img_key = 'img_{}'.format(image_code_id).encode('utf-8')
        con_redis = get_redis_connection(alias='verify_codes')
        con_redis.setex(img_key, constants.IMAGE_CODE_REDIS_EXPIRES, text)

        logger.info("Image code: {a:->60}".format(a=text))
        return HttpResponse(content=image, content_type='image/jpg')

#验证用户名
class CheckUsernameView(View):
    '''
    check username
    /usernames/(?P<username>\w{5,20})/

    1.创建类视图
    2.检验参数
    3.查询数据
    '''

    def get(self, request, username):
        data = {
            'username': username,
            'count': Users.objects.filter(username=username).count()
        }
        return to_json_data(data=data)

#验证手机号
class CheckMobileView(View):
    '''
    check mobile
    /mobiles/(?P<mobile>1[3-9]\d{9})/

    1.创建类视图
    2.检验参数
    3.查询数据
    '''

    def get(self, request, mobile):
        data = {
            'mobile': mobile,
            'count': Users.objects.filter(mobile=mobile).count(),
        }
        return to_json_data(data=data)

#发送验证码
class SmsCodesView(View):
    '''
    send sms_code
    /sms_codes/

    1.定义类视图
    2.获取前端json数据
    3.校验参数
    4.发送验证码
    5.将验证码60s标记与验证码文本存入redis
    6.返回json数据到前端
    '''
    # def post(self, request):
    #     #2.获取前端json数据
    #     json_data = request.body
    #     if not json_data:
    #         return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])
    #     #3.校验参数
    #     dict_data = json.loads(json_data.decode('utf8'))
    #     form = CheckImgCodeForm(data=dict_data)
    #     if form.is_valid():
    #         mobile = form.cleaned_data.get('mobile')
    #         # sms_num = ''.join([random.choice(string.digits) for _ in range(constants.SMS_CODE_NUMS)])
    #         sms_num = '%06d' % random.randint(0, 999999)
    #         con_redis = get_redis_connection(alias='verify_codes')
    #         pl = con_redis.pipeline()
    #         sms_flag_fmt = 'sms_flag_{}'.format(mobile)
    #         sms_text_fmt = 'sms_{}'.format(mobile)
    #         #4.发送验证码(之前需要把60s发送标记和验证码写入redis)
    #         try:
    #             pl.setex(sms_flag_fmt.encode('utf8'), constants.SEND_SMS_CODE_INTERVAL, 1)
    #             pl.setex(sms_text_fmt, constants.SMS_CODE_REDIS_EXPIRES, sms_num)
    #             pl.execute()
    #         except Exception as e:
    #             logger.debug('redis 执行出现异常:{}'.format(e))
    #             return to_json_data(errno=Code.UNKOWNERR, errmsg=error_map[Code.UNKOWNERR])
    #         logger.info('短信验证码:{a:->60}'.format(a=sms_num))
    #
    #         return to_json_data(errno=Code.OK, errmsg='短信发送成功')
    #     else:
    #         err_msg_list=[]
    #         for item in form.errors.get_json_data().values():
    #             err_msg_list.append(item[0].get('message'))
    #
    #         err_msg_str='/'.join(err_msg_list)
    #         #6.返回json数据到前端
    #         return to_json_data(errno=Code.PARAMERR,errmsg=err_msg_str)

    def post(self,request):
        json_data=request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR,errmsg=error_map[Code.PARAMERR])
        dict_data=json.loads(json_data.decode('utf8'))
        form=CheckImgCodeForm(data=dict_data)
        if form.is_valid():
            mobile=form.cleaned_data.get('mobile')
            sms_code='%06d'%random.randint(0,999999)
            redis_con=get_redis_connection('verify_codes')
            pl=redis_con.pipeline()
            try:
                pl.setex('sms_flag_{}'.format(mobile).encode('utf8'),constants.SEND_SMS_CODE_INTERVAL,1)
                pl.setex('sms_{}'.format(mobile).encode('utf8'),constants.SMS_CODE_REDIS_EXPIRES,sms_code)
                pl.execute()
            except Exception as e:
                logger.debug('redis执行异常:{}'.format(e))
                return to_json_data(errno=Code.UNKOWNERR, errmsg=error_map[Code.UNKOWNERR])

            try:
                result = CCP().send_template_sms(mobile,
                                                 [sms_code, constants.SMS_CODE_YUNTX_EXPIRES],
                                                 constants.SMS_CODE_TEMP_ID)
            except Exception as e:
                logger.error("发送验证码短信[异常][ mobile: %s, message: %s ]" % (mobile, e))
                return to_json_data(errno=Code.SMSERROR, errmsg=error_map[Code.SMSERROR])
            else:
                if result == 0:
                    logger.info("发送验证码短信[正常][ mobile: %s sms_code: %s]" % (mobile, sms_code))
                    return to_json_data(errno=Code.OK, errmsg="短信验证码发送成功")
                else:
                    logger.warning("发送验证码短信[失败][ mobile: %s ]" % mobile)
                    return to_json_data(errno=Code.SMSFAIL, errmsg=error_map[Code.SMSFAIL])


            logger.info('{a:->60}'.format(a=sms_code))
            return to_json_data(errno=Code.OK, errmsg='短信发送成功')
        else:
            err_msg_list=[]
            for item in form.errors.get_json_data().values():
                err_msg_list.append(item[0].get('message'))

            err_msg_str='/'.join(err_msg_list)
            #6.返回json数据到前端
            return to_json_data(errno=Code.PARAMERR,errmsg=err_msg_str)



class SmsCodesView1(View):
    '''
    send sms_code
    /sms_codes/

    1.定义类视图
    2.获取前端json数据
    3.校验参数
    4.发送验证码
    5.将验证码60s标记与验证码文本存入redis
    6.返回json数据到前端
    '''
    # def post(self, request):
    #     #2.获取前端json数据
    #     json_data = request.body
    #     if not json_data:
    #         return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])
    #     #3.校验参数
    #     dict_data = json.loads(json_data.decode('utf8'))
    #     form = CheckImgCodeForm(data=dict_data)
    #     if form.is_valid():
    #         mobile = form.cleaned_data.get('mobile')
    #         # sms_num = ''.join([random.choice(string.digits) for _ in range(constants.SMS_CODE_NUMS)])
    #         sms_num = '%06d' % random.randint(0, 999999)
    #         con_redis = get_redis_connection(alias='verify_codes')
    #         pl = con_redis.pipeline()
    #         sms_flag_fmt = 'sms_flag_{}'.format(mobile)
    #         sms_text_fmt = 'sms_{}'.format(mobile)
    #         #4.发送验证码(之前需要把60s发送标记和验证码写入redis)
    #         try:
    #             pl.setex(sms_flag_fmt.encode('utf8'), constants.SEND_SMS_CODE_INTERVAL, 1)
    #             pl.setex(sms_text_fmt, constants.SMS_CODE_REDIS_EXPIRES, sms_num)
    #             pl.execute()
    #         except Exception as e:
    #             logger.debug('redis 执行出现异常:{}'.format(e))
    #             return to_json_data(errno=Code.UNKOWNERR, errmsg=error_map[Code.UNKOWNERR])
    #         logger.info('短信验证码:{a:->60}'.format(a=sms_num))
    #
    #         return to_json_data(errno=Code.OK, errmsg='短信发送成功')
    #     else:
    #         err_msg_list=[]
    #         for item in form.errors.get_json_data().values():
    #             err_msg_list.append(item[0].get('message'))
    #
    #         err_msg_str='/'.join(err_msg_list)
    #         #6.返回json数据到前端
    #         return to_json_data(errno=Code.PARAMERR,errmsg=err_msg_str)

    def post(self,request):
        json_data=request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR,errmsg=error_map[Code.PARAMERR])
        dict_data=json.loads(json_data.decode('utf8'))
        form=CheckImgCodeForm1(data=dict_data)
        if form.is_valid():
            mobile=form.cleaned_data.get('mobile')
            sms_code='%06d'%random.randint(0,999999)
            redis_con=get_redis_connection('verify_codes')
            pl=redis_con.pipeline()
            try:
                pl.setex('sms_flag_{}'.format(mobile).encode('utf8'),constants.SEND_SMS_CODE_INTERVAL,1)
                pl.setex('sms_{}'.format(mobile).encode('utf8'),constants.SMS_CODE_REDIS_EXPIRES,sms_code)
                pl.execute()
            except Exception as e:
                logger.debug('redis执行异常:{}'.format(e))
                return to_json_data(errno=Code.UNKOWNERR, errmsg=error_map[Code.UNKOWNERR])
            logger.info('{a:->60}'.format(a=sms_code))
            return to_json_data(errno=Code.OK, errmsg='短信发送成功')
        else:
            err_msg_list=[]
            for item in form.errors.get_json_data().values():
                err_msg_list.append(item[0].get('message'))

            err_msg_str='/'.join(err_msg_list)
            #6.返回json数据到前端
            return to_json_data(errno=Code.PARAMERR,errmsg=err_msg_str)


























