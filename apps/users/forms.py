import re

from django import forms
from django.contrib.auth import login
from django_redis import get_redis_connection
from django.db.models import Q

from users import constants
from verifications.constants import SMS_CODE_NUMS
from users.models import Users


class RegisterForm(forms.Form):
    """
    register
    """
    username = forms.CharField(label='用户名', max_length=20, min_length=5,
                               error_messages={"min_length": "用户名长度要大于5", "max_length": "用户名长度要小于20",
                                               "required": "用户名不能为空"}
                               )
    password = forms.CharField(label='密码', max_length=20, min_length=6,
                               error_messages={"min_length": "密码长度要大于6", "max_length": "密码长度要小于20",
                                               "required": "密码不能为空"}
                               )
    password_repeat = forms.CharField(label='确认密码', max_length=20, min_length=6,
                                      error_messages={"min_length": "密码长度要大于6", "max_length": "密码长度要小于20",
                                                      "required": "密码不能为空"}
                                      )
    mobile = forms.CharField(label='手机号', max_length=11, min_length=11,
                             error_messages={"min_length": "手机号长度有误", "max_length": "手机号长度有误",
                                             "required": "手机号不能为空"})

    sms_code = forms.CharField(label='短信验证码', max_length=SMS_CODE_NUMS, min_length=SMS_CODE_NUMS,
                               error_messages={"min_length": "短信验证码长度有误", "max_length": "短信验证码长度有误",
                                               "required": "短信验证码不能为空"})

    def clean_mobile(self):
        tel = self.cleaned_data.get('mobile')
        if not re.match(r"^1[3-9]\d{9}$", tel):
            raise forms.ValidationError("手机号码格式不正确")
        if Users.objects.filter(mobile=tel).exists():
            raise forms.ValidationError("手机号已注册，请重新输入")

        return tel

    def clean(self):
        cleaned_data = super().clean()
        passwd = cleaned_data.get('password')
        passwd_repeat = cleaned_data.get('password_repeat')
        if passwd != passwd_repeat:
            raise forms.ValidationError("两次密码不一致")
        tel = cleaned_data.get('mobile')
        sms_text = cleaned_data.get('sms_code')

        con_redis = get_redis_connection(alias='verify_codes')
        sms_fmt = 'sms_{}'.format(tel).encode('utf-8')
        real_sms = con_redis.get(sms_fmt)

        if (not real_sms) or (sms_text != real_sms.decode('utf-8')):
            raise forms.ValidationError('短信验证码错误')


class RetrieveForm(forms.Form):
    username = forms.CharField(label='用户名', max_length=20, min_length=5,
                               error_messages={"min_length": "用户名长度要大于5", "max_length": "用户名长度要小于20",
                                               "required": "用户名不能为空"}
                               )
    password = forms.CharField(label='密码', max_length=20, min_length=6,
                               error_messages={"min_length": "密码长度要大于6", "max_length": "密码长度要小于20",
                                               "required": "密码不能为空"}
                               )
    mobile = forms.CharField(label='手机号', max_length=11, min_length=11,
                             error_messages={"min_length": "手机号长度有误", "max_length": "手机号长度有误",
                                             "required": "手机号不能为空"})

    sms_code = forms.CharField(label='短信验证码', max_length=SMS_CODE_NUMS, min_length=SMS_CODE_NUMS,
                               error_messages={"min_length": "短信验证码长度有误", "max_length": "短信验证码长度有误",
                                               "required": "短信验证码不能为空"})
    def clean_mobile(self):
        mobile=self.cleaned_data.get('mobile')
        if not re.match('^1[3456789]\d{9}$',mobile):
            raise forms.ValidationError('手机号格式不正确')
        if not Users.objects.filter(mobile=mobile).exists():
            raise forms.ValidationError('手机号不存在,请输入已注册的手机号')
        return mobile

    def clean(self):
        cleaned_data=super().clean()
        username=cleaned_data.get('username')
        mobile=cleaned_data.get('mobile')
        sms_text=cleaned_data.get('sms_code')
        user=Users.objects.filter(username=username,mobile=mobile)
        if not user:
            raise forms.ValidationError('用户名或手机号错误,请重新输入!')

        redis_con=get_redis_connection('verify_codes')
        sms_origin=redis_con.get('sms_{}'.format(mobile).encode('utf8'))
        sms_code=sms_origin.decode('utf8') if sms_origin else None
        if (not sms_code) or (sms_text.upper() != sms_code):
            raise forms.ValidationError('短信验证码错误,请重新输入!')


class LoginForm(forms.Form):
    '''
    1.接收前端request参数
    2.校验用户名
    3.校验密码
    4.实现登录
    '''
    user_account = forms.CharField()
    password = forms.CharField(label='密码', max_length=20, min_length=6,
                               error_messages={"min_length": "密码长度要大于6", "max_length": "密码长度要小于20",
                                               "required": "密码不能为空"})
    remember_me = forms.BooleanField(required=False)

    def __init__(self,*args,**kwargs):
        self.request=kwargs.pop('request',None)
        super().__init__(*args,**kwargs)

    def clean_user_account(self):
        cleaned_data=self.cleaned_data
        user_info=cleaned_data.get('user_account')
        if not user_info:
            raise forms.ValidationError('用户账号不能为空')
        if (not re.match(r'^1[3-9]\d{9}$',user_info)) and (len(user_info) <5 or len(user_info) >20):
            raise forms.ValidationError('用户账号格式不正确,请重新输入')
        return user_info

    def clean(self):
        cleaned_data=super().clean()
        user_info=cleaned_data.get('user_account')
        passwd=cleaned_data.get('password')
        hold_login=cleaned_data.get('remember_me')

        user_queryset=Users.objects.filter(Q(mobile=user_info)|Q(username=user_info))
        if user_queryset:
            user=user_queryset.first()
            if user.check_password(passwd):
                if hold_login:
                    self.request.session.set_expiry(None)
                    login(self.request,user)
                else:
                    self.request.session.set_expiry(constants.USER_SESSION_EXPIRES)
                    login(self.request,user)
            else:
                raise forms.ValidationError('密码不正确,请重新输入')

        else:
            raise forms.ValidationError('用户账号不存在,请重新输入')



























